"""E5: brief-aware coverage, the proposed fix (report section 11).

    uv run python -m envelope_shift.analysis.e5_brief_coverage pairs OUT
    uv run python -m envelope_shift.analysis.e5_brief_coverage sweep LAYOUTS OUT
    uv run python -m envelope_shift.analysis.e5_brief_coverage bestofn LAYOUTS OUT

Three variants of coverage are scored side by side on the same layouts:

    published   the published formula against the room type's inventory (sections 3-5)
    tolerate    the brief's program types are no longer extraneous
    require     the brief's program types are required inventory lines

and one quantity that is not a metric at all but the thing a reward should track:

    fulfilment  the share of the brief's program types (Atypicality.declared_extraneous)
                present in the layout, by exact type name

`pairs` scores the four hand-authored E2 pairs (no model output; e5_pairs.csv).
`sweep` scores every parsed row of a pooled layouts.jsonl: per-arm T5 means
(e5_t5.csv), the Spearman correlation of each variant with fulfilment over the T5 rows
(e5_t5_correlation.csv), and, as a check that the fix is a no-op where no brief declares a
program, the largest difference from published coverage on T0-T4 (e5_identity.csv).
`bestofn` repeats E2b's selection (highest coverage, first sample on a tie) under each
variant and reports the fulfilment of what gets selected (e5_bestofn.csv).
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from ..arm import arm_label
from ..envelopes import load_all
from ..experiments.e2_pairs import PAIRS
from ..metrics.coverage import coverage, coverage_brief
from ..schema import Envelope, Layout
from ._common import spearman, write_csv

VARIANTS = ("published", "tolerate", "require")
TIERS_WITHOUT_PROGRAM = ("T0", "T1", "T2", "T3", "T4")


def program(env: Envelope) -> list[str]:
    return list(env.atypicality.declared_extraneous or [])


def fulfilment(env: Envelope, entities) -> float | None:
    """Share of the brief's program types present; None where the brief declares none."""
    prog = program(env)
    if not prog:
        return None
    present = {e.type for e in entities}
    return sum(t in present for t in prog) / len(prog)


def scores(env: Envelope, entities) -> dict[str, float]:
    return {
        "published": coverage(env, entities).score,
        "tolerate": coverage_brief(env, entities, mode="tolerate").score,
        "require": coverage_brief(env, entities, mode="require").score,
    }


def _mean(xs) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


# --------------------------------------------------------------------------- pairs

PAIR_FIELDS = ["envelope_id", "layout", "fulfilment", *VARIANTS]


def pair_rows() -> list[dict]:
    rows = []
    for pair in PAIRS:
        for name, entities in (("conventional", pair.conventional), ("unconventional", pair.unconventional)):
            rows.append({"envelope_id": pair.envelope_id, "layout": name,
                         "fulfilment": fulfilment(pair.env, entities), **scores(pair.env, entities)})
    return rows


# --------------------------------------------------------------------------- sweep

def load(path: Path) -> list[dict]:
    """Parsed rows of a layouts.jsonl as {env, entities, arm, sample}, in file order."""
    envs = {e.id: e for e in load_all()}
    out = []
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        layout = Layout.model_validate({k: rec[k] for k in Layout.model_fields if k in rec})
        if not layout.parse_ok:
            continue
        out.append({"env": envs[rec["envelope_id"]], "entities": layout.entities,
                    "arm": arm_label(layout.model, rec.get("include_inventory", True)),
                    "sample": rec.get("sample", 0)})
    return out


T5_FIELDS = ["model", "n_rows", "fulfilment", *VARIANTS]
CORR_FIELDS = ["variant", "n_rows", "spearman_vs_fulfilment"]
IDENTITY_FIELDS = ["tier", "n_rows", "max_abs_diff_tolerate", "max_abs_diff_require"]


def sweep_tables(rows: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    t5 = [dict(r, f=fulfilment(r["env"], r["entities"]), **scores(r["env"], r["entities"]))
          for r in rows if r["env"].atypicality.tier.value == "T5"]
    by_arm: dict[str, list[dict]] = defaultdict(list)
    for r in t5:
        by_arm[r["arm"]].append(r)
    per_arm = [{"model": arm, "n_rows": len(rs), "fulfilment": _mean(r["f"] for r in rs),
                **{v: _mean(r[v] for r in rs) for v in VARIANTS}}
               for arm, rs in sorted(by_arm.items())]
    corr = [{"variant": v, "n_rows": len(t5),
             "spearman_vs_fulfilment": spearman([r[v] for r in t5], [r["f"] for r in t5])}
            for v in VARIANTS]
    identity = []
    for tier in TIERS_WITHOUT_PROGRAM:
        rs = [r for r in rows if r["env"].atypicality.tier.value == tier]
        diffs = {m: 0.0 for m in ("tolerate", "require")}
        for r in rs:
            s = scores(r["env"], r["entities"])
            for m in diffs:
                diffs[m] = max(diffs[m], abs(s[m] - s["published"]))
        identity.append({"tier": tier, "n_rows": len(rs), "max_abs_diff_tolerate": diffs["tolerate"],
                         "max_abs_diff_require": diffs["require"]})
    return per_arm, corr, identity


# --------------------------------------------------------------------------- best-of-N

BESTOFN_FIELDS = ["model", "envelope_id", "selected_by", "n", "selected_sample", "selected_coverage",
                  "selected_fulfilment", "pool_mean_fulfilment"]


def bestofn_rows(rows: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        if program(r["env"]):
            groups[(r["arm"], r["env"].id)].append(dict(r, f=fulfilment(r["env"], r["entities"]),
                                                        **scores(r["env"], r["entities"])))
    out: list[dict] = []
    for (arm, env_id), pool in sorted(groups.items()):
        if len(pool) < 2:
            continue
        pool.sort(key=lambda r: r["sample"])
        for v in VARIANTS:
            best = max(pool, key=lambda r: r[v])  # max() keeps the first on a tie
            out.append({"model": arm, "envelope_id": env_id, "selected_by": v, "n": len(pool),
                        "selected_sample": best["sample"], "selected_coverage": best[v],
                        "selected_fulfilment": best["f"], "pool_mean_fulfilment": _mean(r["f"] for r in pool)})
    for arm in sorted({r["model"] for r in out}):
        for v in VARIANTS:
            rs = [r for r in out if r["model"] == arm and r["selected_by"] == v]
            out.append({"model": arm, "envelope_id": "ALL", "selected_by": v, "n": sum(r["n"] for r in rs),
                        "selected_sample": "", "selected_coverage": _mean(r["selected_coverage"] for r in rs),
                        "selected_fulfilment": _mean(r["selected_fulfilment"] for r in rs),
                        "pool_mean_fulfilment": _mean(r["pool_mean_fulfilment"] for r in rs)})
    return out


# --------------------------------------------------------------------------- cli

def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("pairs")
    s.add_argument("out_dir")
    for name in ("sweep", "bestofn"):
        s = sub.add_parser(name)
        s.add_argument("layouts")
        s.add_argument("out_dir")
    args = p.parse_args(argv)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if args.cmd == "pairs":
        rows = pair_rows()
        write_csv(out / "e5_pairs.csv", PAIR_FIELDS, rows)
        for r in rows:
            print(f"  {r['envelope_id']:<26} {r['layout']:<15} fulfil {r['fulfilment']:.2f}  "
                  + "  ".join(f"{v} {r[v]:6.1f}" for v in VARIANTS))
    elif args.cmd == "sweep":
        per_arm, corr, identity = sweep_tables(load(Path(args.layouts)))
        write_csv(out / "e5_t5.csv", T5_FIELDS, per_arm)
        write_csv(out / "e5_t5_correlation.csv", CORR_FIELDS, corr)
        write_csv(out / "e5_identity.csv", IDENTITY_FIELDS, identity)
        for r in per_arm + corr + identity:
            print("  " + "  ".join(f"{k}={v:.4g}" if isinstance(v, float) else f"{k}={v}" for k, v in r.items()))
    else:
        rows = bestofn_rows(load(Path(args.layouts)))
        write_csv(out / "e5_bestofn.csv", BESTOFN_FIELDS, rows)
        for r in rows:
            if r["envelope_id"] == "ALL":
                print(f"  {r['model']:<12} by {r['selected_by']:<9} selected fulfilment "
                      f"{r['selected_fulfilment']:.3f}  pool {r['pool_mean_fulfilment']:.3f}")


if __name__ == "__main__":
    main()

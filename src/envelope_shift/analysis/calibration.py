"""A3 calibration: rescore a layouts.jsonl under DEFAULT and STRICT parameters.

    uv run python -m envelope_shift.analysis.calibration results/layouts.jsonl
    uv run python -m envelope_shift.analysis.calibration results/layouts.jsonl --per-room
    uv run python -m envelope_shift.analysis.calibration results/layouts.jsonl --out-dir DIR

Prints the T0 means of coverage / navigability / overlap_clearance under each
registered parameter set (params.PARAM_SETS) next to the published
LLM baseline band, so the reader can see how much of the calibration gap the
unpublished parameters account for. Layouts are rescored from the persisted
raw entities; no model is queried. No metric formula is touched here: the
same three functions run twice with different Params.

--out-dir writes the committed derived tables section 4 cites:
calibration_t0_default.csv, calibration_t0_strict.csv (per room and arm),
calibration_t0_delta.csv (strict minus default) and calibration_t0_summary.md
(arm means against the published band, with an off_scale count of the rows whose
navigability left its declared range). Every row order is sorted explicitly.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import mean

from ..arm import arm_label
from ..envelopes import load_all
from ..metrics import coverage, navigability, overlap_clearance
from ..params import DEFAULT, PARAM_SETS, Params
from ..schema import Envelope, Layout
from ._common import write_csv

# Published LLM-baseline T0 band (Higharc GBM post): coverage / navigability /
# overlap-clearance means. The three numbers the calibration is measured against.
PUBLISHED_BAND: dict[str, float] = {
    "coverage": 76.4,
    "navigability": 45.7,
    "overlap_clearance": 7.4,
}
PUBLISHED_LABEL = "Higharc's best frontier text LLM (Claude Opus 4.6)"
METRICS: tuple[str, ...] = ("coverage", "navigability", "overlap_clearance")


def load_arms(path: Path, tier: str | None = "T0") -> list[tuple[Envelope, Layout, str]]:
    """Parsed (envelope, layout, arm) triples from a sweep's layouts.jsonl.

    `arm` is the model label `run.py score` writes: a model prompted WITHOUT the
    expected inventory is a different arm of the experiment and carries the
    `-noinv` suffix. Without the suffix the two arms of the same model collide
    in one bucket and every per-model mean is a blend of them.

    Unparseable layouts (parse_ok false) are dropped: they carry no entities
    and would score 0 on every axis, which is a generation failure rather
    than a calibration signal. `tier=None` keeps every tier.
    """
    envs = {e.id: e for e in load_all()}
    out: list[tuple[Envelope, Layout, str]] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            env = envs[rec["envelope_id"]]
            if tier is not None and env.atypicality.tier.value != tier:
                continue
            layout = Layout.model_validate({k: rec[k] for k in Layout.model_fields if k in rec})
            if not layout.parse_ok:
                continue
            arm = arm_label(layout.model, rec.get("include_inventory", True))
            out.append((env, layout, arm))
    return out


def load_layouts(path: Path, tier: str | None = "T0") -> list[tuple[Envelope, Layout]]:
    """`load_arms` without the arm label, for the printed summary."""
    return [(env, layout) for env, layout, _ in load_arms(path, tier)]


def score_three(env: Envelope, layout: Layout, params: Params) -> dict[str, float]:
    """The three published metrics only (the experience axis is not calibrated)."""
    return {
        "coverage": coverage(env, layout.entities, params).score,
        "navigability": navigability(env, layout.entities, params).score,
        "overlap_clearance": overlap_clearance(env, layout.entities, params).score,
    }


def rescore(
    pairs: list[tuple[Envelope, Layout]],
    param_sets: dict[str, Params] | None = None,
) -> dict[str, list[dict]]:
    """name -> per-layout rows [{envelope_id, model, sample-less, <metrics>}]."""
    sets = param_sets or PARAM_SETS
    out: dict[str, list[dict]] = {}
    for name, params in sets.items():
        rows = []
        for env, layout in pairs:
            row = {"envelope_id": env.id, "room_type": env.room_type.value, "model": layout.model}
            row.update(score_three(env, layout, params))
            rows.append(row)
        out[name] = rows
    return out


def summarize(rescored: dict[str, list[dict]]) -> list[dict]:
    """One row per parameter set with metric means and n, then the published band."""
    table: list[dict] = []
    for name, rows in rescored.items():
        row: dict = {"params": name, "n": len(rows)}
        for m in METRICS:
            row[m] = mean(r[m] for r in rows) if rows else float("nan")
        table.append(row)
    table.append({"params": PUBLISHED_LABEL, "n": None, **PUBLISHED_BAND})
    return table


def format_table(table: list[dict]) -> str:
    head = "| params | n | " + " | ".join(METRICS) + " |"
    sep = "|---|---:|" + "---:|" * len(METRICS)
    lines = [head, sep]
    for row in table:
        n = "" if row["n"] is None else str(row["n"])
        vals = " | ".join(f"{row[m]:.1f}" for m in METRICS)
        lines.append(f"| {row['params']} | {n} | {vals} |")
    return "\n".join(lines)


def format_per_room(rescored: dict[str, list[dict]]) -> str:
    names = list(rescored)
    head = "| envelope | " + " | ".join(f"{m} {n}" for m in METRICS for n in names) + " |"
    sep = "|---|" + "---:|" * (len(METRICS) * len(names))
    lines = [head, sep]
    by_env: dict[str, dict[str, dict]] = {}
    for name, rows in rescored.items():
        for r in rows:
            by_env.setdefault(r["envelope_id"], {})[name] = r
    for env_id, per in by_env.items():
        cells = [f"{per[n][m]:.1f}" if n in per else "" for m in METRICS for n in names]
        lines.append(f"| {env_id} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


# --- committed derived tables (report/data/) ---------------------------------
#
# Row order is sorted on (arm, envelope_id) and column order is a literal list, so
# these regenerate byte-identically from the same layouts.jsonl on any machine.
# Nothing below writes a path, a date or a machine-dependent value into a cell.

PER_ROOM_FIELDS = ["arm", "envelope_id", "room_type"] + list(METRICS)
DELTA_FIELDS = ["arm", "envelope_id", "room_type"] + [f"{m}_delta" for m in METRICS]
ALL_ARMS = "all arms"

# Navigability's own declared range (metrics/navigability.py docstring: "Nav =
# 100 * (SR - 0.35 * DF), range -35..100"). A score outside it is not a hard
# room, it is a degenerate detour factor: when a door's interior point lands ON
# a target footprint the straight line nearly vanishes and the ratio is
# unbounded. Navigability used to floor that distance at a tiny epsilon, which
# let the score leave the scale entirely; that clamp has been removed and each
# pair's detour is now capped by nav_detour_cap in params.py.
#
# Bounding the metric is navigability's job, not this table's — no formula
# changes here, by the same rule params.py states. But a mean that
# silently pools such a score is this table's job, because `arm_summary` is
# where the pooling happens: without the count column below, STRICT's "all
# arms" navigability reads -2187433.1 with nothing on the row to say why, and
# a section citing it would be citing an artefact as a result.
NAV_RANGE = (-35.0, 100.0)


def out_of_range(rows: list[dict]) -> int:
    """How many rows carry a navigability outside the metric's declared range."""
    lo, hi = NAV_RANGE
    return sum(1 for r in rows if not lo <= r["navigability"] <= hi)


def per_room_rows(arms: list[tuple[Envelope, Layout, str]], params: Params) -> list[dict]:
    """One row per (arm, room) scored under `params`, sorted."""
    rows = [
        {"arm": arm, "envelope_id": env.id, "room_type": env.room_type.value,
         **score_three(env, layout, params)}
        for env, layout, arm in arms
    ]
    return sorted(rows, key=lambda r: (r["arm"], r["envelope_id"]))


def delta_rows(default: list[dict], strict: list[dict]) -> list[dict]:
    """STRICT minus DEFAULT, per room. Coverage's column is the C2 result."""
    by_key = {(r["arm"], r["envelope_id"]): r for r in default}
    out = []
    for s_row in strict:
        d_row = by_key[(s_row["arm"], s_row["envelope_id"])]
        out.append(
            {"arm": s_row["arm"], "envelope_id": s_row["envelope_id"],
             "room_type": s_row["room_type"],
             **{f"{m}_delta": s_row[m] - d_row[m] for m in METRICS}}
        )
    return sorted(out, key=lambda r: (r["arm"], r["envelope_id"]))


def arm_summary(
    arms: list[tuple[Envelope, Layout, str]],
    param_sets: dict[str, Params] | None = None,
) -> list[dict]:
    """Per (parameter set, arm) means, an all-arms mean, then the published band.

    `off_scale` counts the rows behind each mean whose navigability fell outside
    NAV_RANGE, so a contaminated mean is legible as one from the table alone.
    """
    sets = param_sets or PARAM_SETS
    table: list[dict] = []
    for name in sorted(sets):
        rows = per_room_rows(arms, sets[name])
        for arm in sorted({r["arm"] for r in rows}) + [ALL_ARMS]:
            sel = rows if arm == ALL_ARMS else [r for r in rows if r["arm"] == arm]
            table.append({"params": name, "arm": arm, "n": len(sel),
                          **{m: mean(r[m] for r in sel) if sel else float("nan") for m in METRICS},
                          "off_scale": out_of_range(sel)})
    table.append({"params": PUBLISHED_LABEL, "arm": "", "n": None, **PUBLISHED_BAND,
                  "off_scale": 0})
    return table


def format_arm_summary(table: list[dict]) -> str:
    head = "| params | arm | n | " + " | ".join(METRICS) + " | off_scale |"
    lines = [head, "|---|---|---:|" + "---:|" * len(METRICS) + "---:|"]
    for row in table:
        n = "" if row["n"] is None else str(row["n"])
        vals = " | ".join(f"{row[m]:.1f}" for m in METRICS)
        off = "" if row["n"] is None else str(row["off_scale"])
        lines.append(f"| {row['params']} | {row['arm']} | {n} | {vals} | {off} |")
    return "\n".join(lines) + "\n"


def write_tables(arms: list[tuple[Envelope, Layout, str]], out_dir: Path, tier: str = "T0") -> list[Path]:
    """The four calibration tables, into `out_dir`. Returns them sorted by name."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"calibration_{tier.lower()}"
    per_set = {name: per_room_rows(arms, PARAM_SETS[name]) for name in sorted(PARAM_SETS)}
    written = []
    for name, rows in per_set.items():
        path = out_dir / f"{stem}_{name}.csv"
        write_csv(path, PER_ROOM_FIELDS, rows)
        written.append(path)
    delta = out_dir / f"{stem}_delta.csv"
    write_csv(delta, DELTA_FIELDS, delta_rows(per_set["default"], per_set["strict"]))
    written.append(delta)
    summary = out_dir / f"{stem}_summary.md"
    summary.write_text(format_arm_summary(arm_summary(arms)))
    written.append(summary)
    return sorted(written)


def format_param_diff(sets: dict[str, Params]) -> str:
    """Which fields each non-default set changes, so the table is self-describing."""
    lines = []
    for name, params in sets.items():
        if params is DEFAULT:
            continue
        for field, dflt, val in DEFAULT.diff(params):
            lines.append(f"  {name}: {field} {dflt} -> {val}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="envelope-shift calibration")
    p.add_argument("layouts", help="layouts.jsonl written by `envelope-shift sweep`")
    p.add_argument("--tier", default="T0", help="tier to summarize (default T0); 'all' for every tier")
    p.add_argument("--per-room", action="store_true", help="also print per-envelope scores")
    p.add_argument("--out-dir", help="also write the derived calibration tables here")
    args = p.parse_args(argv)

    tier = None if args.tier == "all" else args.tier
    arms = load_arms(Path(args.layouts), tier)
    if not arms:
        print(f"no parseable {args.tier} layouts in {args.layouts}", file=sys.stderr)
        raise SystemExit(1)
    pairs = [(env, layout) for env, layout, _ in arms]
    if args.out_dir:
        for path in write_tables(arms, Path(args.out_dir), args.tier):
            print(f"wrote {path}")
        print()
    rescored = rescore(pairs)
    print(f"{args.tier} means over {len(pairs)} layouts from {args.layouts}\n")
    print(format_table(summarize(rescored)))
    print("\nparameter sets differ from default in:")
    print(format_param_diff(PARAM_SETS) or "  (none)")
    if args.per_room:
        print()
        print(format_per_room(rescored))


if __name__ == "__main__":
    main()

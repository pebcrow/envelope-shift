"""T5 coverage, decomposed by identity: what the drop from ~100 is made of.

    uv run python -m envelope_shift.analysis.t5_decomposition results/all/layouts.jsonl out/

Coverage is 100/N * (sum of line scores - 0.5 * E), N the inventory's line count and E the
number of extraneous TYPES (metrics/coverage.py), clamped at the floor. So for every row the
clamp did not touch

    100 - coverage = 100/N * (N - sum of line scores)     missing lines
                   + 50/N * E                             extraneous types, in three buckets:
        declared  the envelope's own declared_extraneous: the program its brief implies
        synonym   named in analysis/synonyms.toml as a synonym of a declared or inventory type
        other     neither

This module RE-SCORES every raw T5 layout with the tree's own coverage() rather than reading a
stored score, so the parts are the scorer's own arithmetic. Rows are the parsed, inventory-
supplied T5 rows of the pooled corpus; a row where the floor clamp engaged breaks the identity
(the clamp cuts the penalty short) and is excluded from the means and counted in n_clamped.

Writes t5_decomposition.csv (one row per arm), t5_by_envelope.csv (one row per T5 envelope x
arm, the concrete extraneous types and the bucket each fell in, clamped rows included), and
t5_common_rooms.csv: the same per-arm means restricted to the T5 rooms where EVERY arm has an
unclamped parsed row, so no arm's mean is carried by a room another arm lacks. Each arm's
excluded rooms are named with the reason: clamped, or parse_failure (an inventory-supplied T5
call whose response did not parse).
"""

from __future__ import annotations

import argparse
import tomllib
from dataclasses import dataclass
from pathlib import Path

from ..arm import NOINV_SUFFIX, arm_label
from ..envelopes import load_all
from ..inventory import inventory_for
from ..metrics.coverage import coverage
from ..schema import Entity, Envelope
from ._common import load_rows, write_csv

REPO = Path(__file__).resolve().parents[3]
SYNONYMS = REPO / "analysis" / "synonyms.toml"

PARTS = ("missing", "extraneous_declared", "extraneous_synonym", "extraneous_other")
FIELDS = ["model", "n_rows", "n_clamped", "coverage_mean", *PARTS]
COMMON_FIELDS = ["model", "n_rooms", "coverage_mean", *PARTS, "excluded"]
ENVELOPE_FIELDS = ["envelope_id", "model", "coverage", "clamped", "missing",
                   "extraneous_declared", "extraneous_synonym", "extraneous_other"]

# The clamp is engaged when the unclamped arithmetic and the scorer's score differ.
CLAMP_TOL = 1e-9


def load_synonyms(path: Path = SYNONYMS) -> dict[str, str]:
    return {str(k): str(v) for k, v in (tomllib.loads(path.read_text()).get("synonyms") or {}).items()}


@dataclass(frozen=True)
class RowDecomposition:
    envelope_id: str
    model: str
    coverage: float
    clamped: bool
    missing_lines: tuple[str, ...]
    parts: dict[str, float]                       # PARTS -> points of the 100-point gap
    declared: tuple[str, ...]                     # extraneous types, by bucket
    synonym: tuple[tuple[str, str], ...]          # (emitted type, the type it names)
    other: tuple[str, ...]


def bucket_types(env: Envelope, extraneous: tuple[str, ...], synonyms: dict[str, str]):
    """Sort the scorer's extraneous types into (declared, synonym pairs, other).

    A mapping to itself, or to a type outside this room's declared_extraneous + inventory
    types, is refused: a synonym map may not absolve a type into nothing.
    """
    declared_set = set(env.atypicality.declared_extraneous or [])
    named = declared_set | inventory_for(env.room_type).expected_types()
    declared: list[str] = []
    synonym: list[tuple[str, str]] = []
    other: list[str] = []
    for t in extraneous:
        target = synonyms.get(t)
        if target is not None and (target == t or target not in named):
            raise ValueError(f"synonyms.toml maps {t!r} to {target!r}, which is neither a declared "
                             f"extraneous type nor an inventory type of {env.id}")
        if t in declared_set:
            declared.append(t)
        elif target is not None:
            synonym.append((t, target))
        else:
            other.append(t)
    return tuple(declared), tuple(synonym), tuple(other)


def decompose_row(env: Envelope, row: dict, synonyms: dict[str, str]) -> RowDecomposition:
    res = coverage(env, [Entity(**e) for e in row.get("entities") or []])
    n = inventory_for(env.room_type).n
    line_sum = sum(res.item_scores.values()) + sum(res.group_scores.values())
    declared, synonym, other = bucket_types(env, res.extraneous_types, synonyms)
    per_type = 50.0 / n
    parts = {
        "missing": 100.0 * (n - line_sum) / n,
        "extraneous_declared": per_type * len(declared),
        "extraneous_synonym": per_type * len(synonym),
        "extraneous_other": per_type * len(other),
    }
    unclamped = 100.0 * (line_sum - 0.5 * len(res.extraneous_types)) / n
    return RowDecomposition(
        envelope_id=env.id, model=str(row["model"]), coverage=res.score,
        clamped=abs(unclamped - res.score) > CLAMP_TOL, missing_lines=res.missing,
        parts=parts, declared=declared, synonym=synonym, other=other,
    )


def _t5_supplied(layouts: list[dict]):
    """(envelope, arm label, row) for every inventory-supplied T5 row, parsed or not."""
    envs = {e.id: e for e in load_all()}
    for r in layouts:
        env = envs.get(r.get("envelope_id"))
        label = arm_label(str(r.get("model") or ""), bool(r.get("include_inventory", True)))
        if env is None or env.atypicality.tier.value != "T5" or label.endswith(NOINV_SUFFIX):
            continue
        yield env, label, r


def t5_rows(layouts: list[dict], synonyms: dict[str, str]) -> list[RowDecomposition]:
    """Every parsed, inventory-supplied T5 layout, re-scored and decomposed."""
    return [decompose_row(env, {**r, "model": label}, synonyms)
            for env, label, r in _t5_supplied(layouts) if r.get("parse_ok")]


def parse_failures(layouts: list[dict]) -> set[tuple[str, str]]:
    """(envelope_id, arm) of every inventory-supplied T5 call whose response did not parse."""
    return {(env.id, label) for env, label, r in _t5_supplied(layouts) if not r.get("parse_ok")}


def summarize(rows: list[RowDecomposition]) -> list[dict]:
    """One row per arm: means over its unclamped rows, and how many rows the clamp took out.

    An arm with no unclamped row has no mean to publish, so it is left out of the table.
    """
    out = []
    for model in sorted({r.model for r in rows}):
        mine = [r for r in rows if r.model == model]
        kept = [r for r in mine if not r.clamped]
        if not kept:
            continue
        rec = {"model": model, "n_rows": len(kept), "n_clamped": len(mine) - len(kept),
               "coverage_mean": sum(r.coverage for r in kept) / len(kept)}
        for p in PARTS:
            rec[p] = sum(r.parts[p] for r in kept) / len(kept)
        out.append(rec)
    return out


def common_rooms(rows: list[RowDecomposition], failed: set[tuple[str, str]]) -> list[dict]:
    """Per arm, the summarize() means over the rooms every arm has an unclamped row for.

    `excluded` names each room outside that set that the arm attempted, as room:reason, where
    the reason is clamped or parse_failure; a room the arm has an unclamped row for is not
    excluded from it, but is still left out of its mean when another arm lacks it.
    """
    models = sorted({r.model for r in rows} | {m for _, m in failed})
    usable = {m: {r.envelope_id for r in rows if r.model == m and not r.clamped} for m in models}
    common = set.intersection(*usable.values()) if usable else set()
    out = []
    for model in models:
        kept = [r for r in rows if r.model == model and r.envelope_id in common]
        if not kept:
            continue
        reasons = {e: "parse_failure" for e, m in failed if m == model}
        reasons |= {r.envelope_id: "clamped" for r in rows if r.model == model and r.clamped}
        rec = {"model": model, "n_rooms": len({r.envelope_id for r in kept}),
               "coverage_mean": sum(r.coverage for r in kept) / len(kept)}
        for p in PARTS:
            rec[p] = sum(r.parts[p] for r in kept) / len(kept)
        rec["excluded"] = ";".join(f"{e}:{why}" for e, why in sorted(reasons.items()) if e not in common)
        out.append(rec)
    return out


def by_envelope(rows: list[RowDecomposition]) -> list[dict]:
    return [
        {"envelope_id": r.envelope_id, "model": r.model, "coverage": r.coverage,
         "clamped": int(r.clamped), "missing": ";".join(r.missing_lines),
         "extraneous_declared": ";".join(r.declared),
         "extraneous_synonym": ";".join(f"{t}>{target}" for t, target in r.synonym),
         "extraneous_other": ";".join(r.other)}
        for r in sorted(rows, key=lambda r: (r.envelope_id, r.model))
    ]


def run(layouts: Path, out_dir: Path, synonyms_path: Path = SYNONYMS) -> tuple[list[dict], list[dict]]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = load_rows(layouts)
    rows = t5_rows(raw, load_synonyms(synonyms_path))
    per_arm, per_envelope = summarize(rows), by_envelope(rows)
    write_csv(out_dir / "t5_decomposition.csv", FIELDS, per_arm)
    write_csv(out_dir / "t5_by_envelope.csv", ENVELOPE_FIELDS, per_envelope)
    write_csv(out_dir / "t5_common_rooms.csv", COMMON_FIELDS, common_rooms(rows, parse_failures(raw)))
    return per_arm, per_envelope


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("layouts", help="layouts.jsonl of the pooled corpus")
    p.add_argument("out_dir", help="directory for the three CSVs")
    p.add_argument("--synonyms", default=str(SYNONYMS), help="the committed synonym map")
    args = p.parse_args(argv)
    per_arm, per_envelope = run(Path(args.layouts), Path(args.out_dir), Path(args.synonyms))
    print(f"T5: {len(per_arm)} arms, {len(per_envelope)} envelope x arm rows -> {args.out_dir}")
    for r in per_arm:
        print(f"  {r['model']:<10} n={r['n_rows']} clamped={r['n_clamped']}  coverage {r['coverage_mean']:6.2f}"
              + "".join(f"  {p.removeprefix('extraneous_')} {r[p]:5.2f}" for p in PARTS))


if __name__ == "__main__":
    main()

"""R1: coverage saturates when the inventory is handed to the model.

    uv run python -m envelope_shift.analysis.e1_saturation results/all/scores.jsonl out/

`e1_degradation.csv` carries per tier x arm means, which is the right shape for
the ladder but the wrong shape for the headline: the saturation result is an
aggregate over every parsed layout, pooled across tiers and models. This writes
that aggregate so the report can cite a cell instead of a paragraph.

Two arms, split on the model label: `run.py score` suffixes `-noinv` onto the
model name whenever the expected-inventory table was withheld from the prompt,
which is the only split that is recorded on every row of the wave-2 run.

`pct_exactly_100` is rounded to the nearest whole point, the precision the
report quotes it at; the exact fraction is `n_exactly_100 / n_parsed`.
"""

from __future__ import annotations

from pathlib import Path

from ..arm import NOINV_SUFFIX
from ._common import base_parser, load_rows, write_csv

# Column order is load-bearing, not cosmetic: two three-digit integers in adjacent columns
# read as one thousands-grouped number ("144,134") to anything that scans the raw CSV for
# values, including the report contract's number-tracing check. Keep `n_rows` away from
# `n_parsed`, and `n_exactly_100` away from any other bare count.
FIELDS = ["arm", "n_parsed", "coverage_mean", "coverage_min", "coverage_max",
          "n_exactly_100", "pct_exactly_100", "n_rows"]


def withheld(row: dict) -> bool:
    """True when the expected-inventory table was kept out of the prompt."""
    return str(row["model"]).endswith(NOINV_SUFFIX)


def summarize(rows: list[dict]) -> list[dict]:
    out = []
    for arm, keep in (("inventory_supplied", False), ("inventory_withheld", True)):
        sel = [r for r in rows if withheld(r) is keep]
        parsed = [r for r in sel if r.get("parse_ok")]
        cov = [float(r["coverage"]) for r in parsed]
        if not cov:
            continue
        exact = [c for c in cov if c == 100.0]
        out.append({
            "arm": arm,
            "n_rows": len(sel),
            "n_parsed": len(parsed),
            "coverage_mean": sum(cov) / len(cov),
            "coverage_min": min(cov),
            "coverage_max": max(cov),
            "n_exactly_100": len(exact),
            "pct_exactly_100": float(round(100.0 * len(exact) / len(cov))),
        })
    return out


def run(scores: Path, out_dir: Path) -> list[dict]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize(load_rows(scores))
    write_csv(out_dir / "e1_saturation.csv", FIELDS, summary)
    return summary


def main(argv: list[str] | None = None) -> None:
    args = base_parser(__doc__).parse_args(argv)
    summary = run(Path(args.scores), Path(args.out_dir))
    print(f"E1 saturation: {len(summary)} arms -> {args.out_dir}/e1_saturation.csv")
    for r in summary:
        print(f"  {r['arm']:<20} n={r['n_parsed']}/{r['n_rows']}  mean {r['coverage_mean']:6.2f}"
              f"  range {r['coverage_min']:.1f}-{r['coverage_max']:.1f}"
              f"  exactly 100.0: {r['n_exactly_100']} ({r['pct_exactly_100']:.0f}%)")


if __name__ == "__main__":
    main()

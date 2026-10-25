"""E1: do the three published metrics degrade across tiers, and unevenly?

    uv run python -m envelope_shift.analysis.e1_degradation results/scores.jsonl out/

Per tier x model: mean and bootstrap 95% CI of coverage, navigability and
overlap_clearance over parsed layouts, plus the parse-failure rate. Each tier also gets an ALL_ARMS rollup row pooling every arm, because the
ladder's headline signal -- the JSON parse-failure rate -- is a per-tier rate
over all arms and the report has to be able to cite it as a cell. The rollup is
written to the csv and held out of the plot (it is not an arm, and pooling the
inventory-supplied and inventory-withheld arms makes its metric means a mixture,
readable only as the parse-failure column).

The parse-failure rate is PARSE failures / rows: a model reply that did not parse.
A transport failure (the call never returned; `failure_kind == "transport"`) is
no observation of the model and is never in the numerator; it is reported in its
own `n_transport` column, so it is neither counted as a model failure nor dropped.
A failed row with no failure_kind is refused rather than guessed at. Writes e1_degradation.csv and
e1_degradation.png (metric vs tier, one line per model, CI as a wash).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..failure import PARSE, TRANSPORT
from ._common import (
    INK2,
    MUTED,
    PUBLISHED,
    SURFACE,
    TIERS,
    base_parser,
    bootstrap_ci,
    legend,
    load_rows,
    model_colors,
    new_figure,
    plt,
    style_axes,
    write_csv,
)

FIELDS = ["tier", "model", "n_rows", "n_parsed", "n_parse_fail", "n_transport", "parse_fail_rate"] + [
    f"{m}_{s}" for m in PUBLISHED for s in ("mean", "lo", "hi")
]

# Label of the per-tier rollup row. Mirrors calibration_t0_summary.md's own
# "all arms" row so the two tables read the same way.
ALL_ARMS = "all arms"


def _failure_kind(row: dict) -> str:
    kind = row.get("failure_kind")
    if kind not in (PARSE, TRANSPORT):
        raise ValueError(
            f"failed row {row.get('envelope_id')}/{row.get('model')} has failure_kind {kind!r}; "
            "run `envelope-shift backfill-failure-kinds` on the sweep's layouts.jsonl"
        )
    return kind


def _cell(tier: str, model: str, sel: list[dict]) -> dict:
    parsed = [r for r in sel if r["parse_ok"]]
    kinds = [_failure_kind(r) for r in sel if not r["parse_ok"]]
    n_parse_fail = kinds.count(PARSE)
    rec = {
        "tier": tier,
        "model": model,
        "n_rows": len(sel),
        "n_parsed": len(parsed),
        "n_parse_fail": n_parse_fail,
        "n_transport": kinds.count(TRANSPORT),
        "parse_fail_rate": n_parse_fail / len(sel),
    }
    for m in PUBLISHED:
        mean, lo, hi = bootstrap_ci([r[m] for r in parsed])
        rec.update({f"{m}_mean": mean, f"{m}_lo": lo, f"{m}_hi": hi})
    return rec


def summarize(rows: list[dict]) -> list[dict]:
    models = sorted({r["model"] for r in rows})
    tiers = [t for t in TIERS if any(r["tier"] == t for r in rows)]
    out = []
    for tier in tiers:
        in_tier = [r for r in rows if r["tier"] == tier]
        for model in models:
            sel = [r for r in in_tier if r["model"] == model]
            if sel:
                out.append(_cell(tier, model, sel))
        out.append(_cell(tier, ALL_ARMS, in_tier))
    return out


def plot(summary: list[dict], path: Path) -> None:
    summary = [r for r in summary if r["model"] != ALL_ARMS]   # a mixture, not an arm
    models = sorted({r["model"] for r in summary})
    tiers = [t for t in TIERS if any(r["tier"] == t for r in summary)]
    colors = model_colors(models)
    fig, axes = new_figure(3)
    x = np.arange(len(tiers))
    for ax, metric in zip(axes, PUBLISHED):
        style_axes(ax)
        for model in models:
            by_tier = {r["tier"]: r for r in summary if r["model"] == model}
            y = np.array([by_tier[t][f"{metric}_mean"] if t in by_tier else np.nan for t in tiers])
            lo = np.array([by_tier[t][f"{metric}_lo"] if t in by_tier else np.nan for t in tiers])
            hi = np.array([by_tier[t][f"{metric}_hi"] if t in by_tier else np.nan for t in tiers])
            c = colors[model]
            ax.fill_between(x, lo, hi, color=c, alpha=0.10, linewidth=0)
            ax.plot(x, y, color=c, linewidth=2, solid_joinstyle="round", solid_capstyle="round",
                    marker="o", markersize=6, markeredgecolor=SURFACE, markeredgewidth=1.5, label=model)
        ax.set_xticks(x, tiers)
        ax.set_title(metric.replace("_", " "), fontsize=10, loc="left")
        ax.set_xlabel("tier", fontsize=8)
    axes[0].set_ylabel("score (parsed layouts, mean and 95% bootstrap CI)", fontsize=8)
    legend(axes[0], loc="best")
    fig.text(0.01, 0.005, "E1 degradation across the atypicality ladder", color=MUTED, fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def run(scores: Path, out_dir: Path) -> list[dict]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = load_rows(scores)
    summary = summarize(rows)
    write_csv(out_dir / "e1_degradation.csv", FIELDS, summary)
    plot(summary, out_dir / "e1_degradation.png")
    return summary


def main(argv: list[str] | None = None) -> None:
    args = base_parser(__doc__).parse_args(argv)
    summary = run(Path(args.scores), Path(args.out_dir))
    print(f"E1: {len(summary)} tier x model cells -> {args.out_dir}/e1_degradation.{{csv,png}}")
    for r in summary:
        cells = "  ".join(f"{m[:3]} {r[f'{m}_mean']:6.1f} [{r[f'{m}_lo']:5.1f},{r[f'{m}_hi']:5.1f}]" for m in PUBLISHED)
        print(f"  {r['tier']} {r['model']:<24} n={r['n_parsed']}/{r['n_rows']}  {cells}  parse-fail {r['parse_fail_rate']:.0%}  transport {r['n_transport']}")


if __name__ == "__main__":
    main()

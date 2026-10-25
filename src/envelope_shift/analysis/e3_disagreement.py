"""E3: where do coverage, navigability and overlap/clearance disagree?

    uv run python -m envelope_shift.analysis.e3_disagreement results/scores.jsonl out/

A row disagrees sharply when coverage >= 90 and navigability < 50, or
coverage >= 90 and overlap_clearance >= 10: the inventory is complete yet
the room does not work. Writes e3_disagreement.csv, e3_render_ids.txt (the
envelope ids worth rendering) and e3_disagreement.png (both scatterplots,
flagged rows highlighted).
"""

from __future__ import annotations

from pathlib import Path

from ._common import (
    GRID,
    INK2,
    MUTED,
    SERIES,
    SURFACE,
    base_parser,
    load_rows,
    new_figure,
    plt,
    style_axes,
    write_csv,
)

COV_MIN = 90.0
NAV_MAX = 50.0
OC_MIN = 10.0
FIELDS = ["envelope_id", "room_type", "tier", "model", "sample", "coverage", "navigability", "overlap_clearance", "reason"]


def reason(r: dict) -> str | None:
    if not r.get("parse_ok"):
        return None
    if r["coverage"] < COV_MIN:
        return None
    tags = []
    if r["navigability"] < NAV_MAX:
        tags.append("nav<50")
    if r["overlap_clearance"] >= OC_MIN:
        tags.append("oc>=10")
    return "cov>=90 & " + " & ".join(tags) if tags else None


def find(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        why = reason(r)
        if why:
            out.append({k: r[k] for k in FIELDS if k != "reason"} | {"reason": why})
    return out


def plot(rows: list[dict], flagged: list[dict], path: Path) -> None:
    parsed = [r for r in rows if r.get("parse_ok")]
    key = {(r["envelope_id"], r["model"], r["sample"]) for r in flagged}
    is_flag = [(r["envelope_id"], r["model"], r["sample"]) in key for r in parsed]
    fig, axes = new_figure(2)
    for ax, metric, ylabel, band in zip(
        axes,
        ["navigability", "overlap_clearance"],
        ["navigability", "overlap / clearance"],
        [(-5, NAV_MAX), (OC_MIN, 105)],
    ):
        style_axes(ax)
        ax.grid(True, axis="x", color=GRID, linewidth=1)
        ax.axvspan(COV_MIN, 105, ymin=0, ymax=1, color=GRID, alpha=0.5, linewidth=0)
        ax.axhspan(*band, color=GRID, alpha=0.5, linewidth=0)
        xs = [r["coverage"] for r in parsed]
        ys = [r[metric] for r in parsed]
        ok_x = [x for x, f in zip(xs, is_flag) if not f]
        ok_y = [y for y, f in zip(ys, is_flag) if not f]
        fl_x = [x for x, f in zip(xs, is_flag) if f]
        fl_y = [y for y, f in zip(ys, is_flag) if f]
        ax.scatter(ok_x, ok_y, s=36, color=MUTED, edgecolors=SURFACE, linewidths=1.5, label="agree", zorder=2)
        ax.scatter(fl_x, fl_y, s=48, color=SERIES[0], edgecolors=SURFACE, linewidths=1.5, label="disagree", zorder=3)
        ax.set_xlabel("coverage", fontsize=8)
        ax.set_ylabel(ylabel, fontsize=8)
        ax.set_xlim(-5, 105)
        ax.set_title(f"coverage vs {ylabel}", fontsize=10, loc="left")
    handles, labels = axes[0].get_legend_handles_labels()
    leg = fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False, fontsize=8, bbox_to_anchor=(0.5, 0.02))
    for t in leg.get_texts():
        t.set_color(INK2)
    fig.text(0.01, 0.005, "E3 metric disagreement; shaded: coverage>=90 with nav<50 or oc>=10", color=MUTED, fontsize=7)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def run(scores: Path, out_dir: Path) -> list[dict]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = load_rows(scores)
    flagged = find(rows)
    write_csv(out_dir / "e3_disagreement.csv", FIELDS, flagged)
    ids = sorted({r["envelope_id"] for r in flagged})
    (out_dir / "e3_render_ids.txt").write_text("".join(i + "\n" for i in ids))
    plot(rows, flagged, out_dir / "e3_disagreement.png")
    return flagged


def main(argv: list[str] | None = None) -> None:
    args = base_parser(__doc__).parse_args(argv)
    flagged = run(Path(args.scores), Path(args.out_dir))
    ids = sorted({r["envelope_id"] for r in flagged})
    print(f"E3: {len(flagged)} disagreeing rows over {len(ids)} envelopes -> {args.out_dir}/e3_disagreement.{{csv,png}}")
    for r in flagged:
        print(f"  {r['envelope_id']:<28} {r['model']:<24} s{r['sample']} cov {r['coverage']:5.1f} "
              f"nav {r['navigability']:5.1f} oc {r['overlap_clearance']:5.1f}  {r['reason']}")
    if ids:
        print("  render:", " ".join(ids))


if __name__ == "__main__":
    main()

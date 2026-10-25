"""E4: does the exploratory experience axis correlate with the three published metrics?

    uv run python -m envelope_shift.analysis.e4_correlation results/scores.jsonl out/

Spearman rho (average ranks, numpy) of every numeric exp_* column against
coverage, navigability and overlap_clearance over parsed rows. Writes
e4_correlation.csv and e4_correlation.png (a diverging heatmap) and prints
a one-line verdict: "adds little" if every |rho| exceeds 0.7, otherwise
"adds information".
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from matplotlib.colors import LinearSegmentedColormap

from ._common import (
    DIVERGING,
    INK,
    INK2,
    MUTED,
    PUBLISHED,
    SURFACE,
    base_parser,
    load_rows,
    new_figure,
    plt,
    spearman,
    write_csv,
)

THRESHOLD = 0.7
FIELDS = ["exp_column", "n"] + [f"{m}_rho" for m in PUBLISHED]


def exp_columns(rows: list[dict]) -> list[str]:
    cols: list[str] = []
    for r in rows:
        for k, v in r.items():
            if k.startswith("exp_") and isinstance(v, (int, float)) and not isinstance(v, bool) and k not in cols:
                cols.append(k)
    return cols


def correlate(rows: list[dict]) -> list[dict]:
    parsed = [r for r in rows if r.get("parse_ok")]
    out = []
    for col in exp_columns(parsed):
        sel = [r for r in parsed if col in r and r[col] is not None]
        rec = {"exp_column": col, "n": len(sel)}
        for m in PUBLISHED:
            rec[f"{m}_rho"] = spearman([r[col] for r in sel], [r[m] for r in sel])
        out.append(rec)
    return out


def verdict(table: list[dict]) -> str:
    rhos = [r[f"{m}_rho"] for r in table for m in PUBLISHED]
    finite = [x for x in rhos if not math.isnan(x)]
    if not finite:
        return "undetermined (no finite rho)"
    return "adds little" if all(abs(x) > THRESHOLD for x in finite) else "adds information"


def plot(table: list[dict], path: Path) -> None:
    cmap = LinearSegmentedColormap.from_list("diverging", list(DIVERGING)).with_extremes(bad=SURFACE)
    cols = [r["exp_column"].removeprefix("exp_") for r in table]
    mat = np.array([[r[f"{m}_rho"] for m in PUBLISHED] for r in table], dtype=float)
    fig, (ax,) = new_figure(1, width=5.5, height=1.2 + 0.45 * max(len(cols), 1))
    ax.set_facecolor(SURFACE)
    # pcolormesh with a surface-colored edge gives the 2px gap between cells.
    masked = np.ma.masked_invalid(mat)
    mesh = ax.pcolormesh(masked, cmap=cmap, vmin=-1, vmax=1, edgecolors=SURFACE, linewidth=2)
    ax.set_xticks(np.arange(len(PUBLISHED)) + 0.5, [m.replace("_", " ") for m in PUBLISHED], fontsize=8)
    ax.set_yticks(np.arange(len(cols)) + 0.5, cols, fontsize=8)
    ax.tick_params(length=0, labelcolor=INK2)
    for side in ax.spines.values():
        side.set_visible(False)
    ax.invert_yaxis()
    for i in range(len(cols)):
        for j in range(len(PUBLISHED)):
            v = mat[i, j]
            if math.isnan(v):
                ax.text(j + 0.5, i + 0.5, "n/a", ha="center", va="center", fontsize=8, color=MUTED)
            else:
                ink = SURFACE if abs(v) > 0.6 else INK
                ax.text(j + 0.5, i + 0.5, f"{v:+.2f}", ha="center", va="center", fontsize=8, color=ink)
    cb = fig.colorbar(mesh, ax=ax, fraction=0.05, pad=0.03)
    cb.outline.set_visible(False)
    cb.ax.tick_params(labelsize=7, colors=MUTED, labelcolor=INK2, length=0)
    cb.set_label("Spearman rho", fontsize=8, color=INK2)
    ax.set_title(f"experience axis vs published metrics: {verdict(table)}", fontsize=10, loc="left", color=INK)
    fig.text(0.01, 0.005, "E4 exploratory; rows with parse_ok only", color=MUTED, fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def run(scores: Path, out_dir: Path) -> list[dict]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    table = correlate(load_rows(scores))
    write_csv(out_dir / "e4_correlation.csv", FIELDS, table)
    plot(table, out_dir / "e4_correlation.png")
    return table


def main(argv: list[str] | None = None) -> None:
    args = base_parser(__doc__).parse_args(argv)
    table = run(Path(args.scores), Path(args.out_dir))
    print(f"E4: {len(table)} exp_* columns -> {args.out_dir}/e4_correlation.{{csv,png}}")
    for r in table:
        cells = "  ".join(f"{m[:3]} {r[f'{m}_rho']:+.2f}" for m in PUBLISHED)
        print(f"  {r['exp_column']:<24} n={r['n']:<4} {cells}")
    print(f"verdict: experience axis {verdict(table)} (threshold |rho| > {THRESHOLD})")


if __name__ == "__main__":
    main()

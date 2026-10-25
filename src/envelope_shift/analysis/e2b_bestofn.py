"""E2b: does best-of-N by coverage collapse entity-type diversity?

    uv run python -m envelope_shift.analysis.e2b_bestofn results/scores.jsonl out/ [--layouts results/layouts.jsonl]

Rows with sample >= 0 are grouped by (model, envelope_id); groups with fewer
than two parsed samples are skipped. In each group the layout with the
highest coverage is "selected" (one step of coverage-as-reward, SPEC A2).
Selected vs pool is compared on unique entity-type count and Shannon entropy
of entity types, read from the layouts.jsonl beside scores.jsonl. Per group
the pool value is the per-layout mean; per model an "ALL" row compares the
aggregate type distribution of the selected set against the whole pool.

The selected set is one layout per room, the pool every layout, so the selected
set would carry fewer types and less entropy than the pool at ANY selection
rule. The ALL row therefore also carries a same-size baseline: RAND_DRAWS
random selections of one parsed sample per room (numpy default_rng(RAND_SEED)),
and the mean, 5th and 95th percentile of their aggregate type entropy, plus the
fraction of draws at or below the selected set's entropy.

The selection takes the FIRST sample on a coverage tie, and ties are common. The ALL row
therefore also carries the selection under RANDOM tie-breaking: the same RAND_DRAWS draws
and RAND_SEED, each drawing one of a room's top-coverage samples uniformly, with the mean,
5th and 95th percentile of the aggregate type entropy (tb_entropy_*) and tb_frac_rand_le,
the share of random one-per-room selections at or below tb_entropy_mean.
Writes e2b_bestofn.csv and e2b_bestofn.png.
"""

from __future__ import annotations

import math
from collections import Counter
from pathlib import Path

import numpy as np

from ._common import (
    INK2,
    MUTED,
    SERIES,
    SURFACE,
    base_parser,
    legend,
    load_rows,
    new_figure,
    plt,
    shannon_entropy,
    style_axes,
    write_csv,
)

FIELDS = [
    "model", "envelope_id", "n", "best_sample", "best_coverage", "pool_mean_coverage",
    "sel_unique", "pool_mean_unique", "sel_entropy", "pool_mean_entropy",
    "pool_agg_unique", "pool_agg_entropy",
    "rand_draws", "rand_seed", "rand_entropy_mean", "rand_entropy_p05", "rand_entropy_p95",
    "rand_frac_le_sel",
    "tb_entropy_mean", "tb_entropy_p05", "tb_entropy_p95", "tb_frac_rand_le",
]
RAND_DRAWS = 2000
RAND_SEED = 0


def random_baseline(rooms: list[list[list[str]]], sel_entropy: float,
                    draws: int = RAND_DRAWS, seed: int = RAND_SEED,
                    tied: list[list[int]] | None = None) -> dict:
    """Aggregate type entropy of `draws` random one-sample-per-room selections.

    `rooms` holds, per room in a fixed order, the type lists of its parsed samples in sample
    order; the draw picks one index per room, so the baseline has the selected set's size.
    `tied`, when given, holds per room the indices of its top-coverage samples; the tb_* columns
    are then the best-of-N selection with a uniformly random pick among them (same seed and
    draw count, its own generator), and tb_frac_rand_le the share of random draws at or below
    its mean.
    """
    rng = np.random.default_rng(seed)
    hs = np.empty(draws)
    for i in range(draws):
        c: Counter = Counter()
        for samples in rooms:
            c.update(samples[int(rng.integers(len(samples)))])
        hs[i] = shannon_entropy(c.values())
    out = {
        "rand_draws": draws, "rand_seed": seed, "rand_entropy_mean": float(hs.mean()),
        "rand_entropy_p05": float(np.percentile(hs, 5)), "rand_entropy_p95": float(np.percentile(hs, 95)),
        "rand_frac_le_sel": float(np.mean(hs <= sel_entropy + 1e-12)),
    }
    if tied is not None:
        rng = np.random.default_rng(seed)
        tb = np.empty(draws)
        for i in range(draws):
            c = Counter()
            for samples, top in zip(rooms, tied):
                c.update(samples[top[int(rng.integers(len(top)))]])
            tb[i] = shannon_entropy(c.values())
        out.update({
            "tb_entropy_mean": float(tb.mean()), "tb_entropy_p05": float(np.percentile(tb, 5)),
            "tb_entropy_p95": float(np.percentile(tb, 95)),
            "tb_frac_rand_le": float(np.mean(hs <= tb.mean() + 1e-12)),
        })
    return out


def entity_types(layouts: list[dict]) -> dict[tuple[str, str, int], list[str]]:
    return {
        (r["envelope_id"], r["model"], int(r.get("sample", 0))): [e["type"] for e in r.get("entities", [])]
        for r in layouts
    }


def _diversity(types: list[str]) -> tuple[int, float]:
    c = Counter(types)
    return len(c), shannon_entropy(c.values())


def compare(rows: list[dict], layouts: list[dict]) -> list[dict]:
    types = entity_types(layouts)
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        if r.get("parse_ok") and r.get("sample", 0) >= 0:
            groups.setdefault((r["model"], r["envelope_id"]), []).append(r)

    out: list[dict] = []
    agg: dict[str, tuple[Counter, Counter]] = {}  # model -> (selected types, pool types)
    rooms: dict[str, list[list[list[str]]]] = {}  # model -> per room, each sample's types
    tied: dict[str, list[list[int]]] = {}  # model -> per room, indices of the top-coverage samples
    for (model, env_id), grp in sorted(groups.items()):
        if len(grp) < 2:
            continue
        grp = sorted(grp, key=lambda r: r["sample"])
        best = max(grp, key=lambda r: r["coverage"])  # first max wins ties
        per = [_diversity(types.get((env_id, model, r["sample"]), [])) for r in grp]
        pool_types = [t for r in grp for t in types.get((env_id, model, r["sample"]), [])]
        sel_types = types.get((env_id, model, best["sample"]), [])
        sel_u, sel_h = _diversity(sel_types)
        pool_u, pool_h = _diversity(pool_types)
        out.append({
            "model": model, "envelope_id": env_id, "n": len(grp),
            "best_sample": best["sample"], "best_coverage": best["coverage"],
            "pool_mean_coverage": float(np.mean([r["coverage"] for r in grp])),
            "sel_unique": sel_u, "pool_mean_unique": float(np.mean([u for u, _ in per])),
            "sel_entropy": sel_h, "pool_mean_entropy": float(np.mean([h for _, h in per])),
            "pool_agg_unique": pool_u, "pool_agg_entropy": pool_h,
        })
        s, p = agg.setdefault(model, (Counter(), Counter()))
        s.update(sel_types)
        p.update(pool_types)
        rooms.setdefault(model, []).append([types.get((env_id, model, r["sample"]), []) for r in grp])
        tied.setdefault(model, []).append([i for i, r in enumerate(grp) if r["coverage"] == best["coverage"]])

    for model, (s, p) in sorted(agg.items()):
        rows_m = [r for r in out if r["model"] == model]
        out.append({
            "model": model, "envelope_id": "ALL", "n": sum(r["n"] for r in rows_m),
            "best_sample": "", "best_coverage": float(np.mean([r["best_coverage"] for r in rows_m])),
            "pool_mean_coverage": float(np.mean([r["pool_mean_coverage"] for r in rows_m])),
            "sel_unique": len(s), "pool_mean_unique": float(np.mean([r["pool_mean_unique"] for r in rows_m])),
            "sel_entropy": shannon_entropy(s.values()),
            "pool_mean_entropy": float(np.mean([r["pool_mean_entropy"] for r in rows_m])),
            "pool_agg_unique": len(p), "pool_agg_entropy": shannon_entropy(p.values()),
            **random_baseline(rooms[model], shannon_entropy(s.values()), tied=tied[model]),
        })
    return out


def plot(table: list[dict], path: Path) -> None:
    per_group = [r for r in table if r["envelope_id"] != "ALL"]
    labels = [f"{r['envelope_id']}\n{r['model']}" for r in per_group]
    y = np.arange(len(per_group))
    fig, axes = new_figure(2, width=4.8, height=1.4 + 0.42 * max(len(per_group), 1))
    for ax, sel_key, pool_key, title in zip(
        axes,
        ["sel_unique", "sel_entropy"],
        ["pool_mean_unique", "pool_mean_entropy"],
        ["unique entity types", "entity-type entropy (bits)"],
    ):
        style_axes(ax)
        ax.grid(True, axis="x", color="#e1e0d9", linewidth=1)
        ax.grid(False, axis="y")
        sel = [r[sel_key] for r in per_group]
        pool = [r[pool_key] for r in per_group]
        for yi, a, b in zip(y, pool, sel):
            ax.plot([a, b], [yi, yi], color=MUTED, linewidth=1, zorder=1)
        ax.scatter(pool, y, s=48, color=MUTED, edgecolors=SURFACE, linewidths=1.5, label="pool (per-layout mean)", zorder=2)
        ax.scatter(sel, y, s=48, color=SERIES[0], edgecolors=SURFACE, linewidths=1.5, label="best-of-N by coverage", zorder=3)
        ax.set_yticks(y, labels, fontsize=7)
        ax.invert_yaxis()
        ax.set_title(title, fontsize=10, loc="left")
    handles, labels = axes[0].get_legend_handles_labels()
    leg = fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False, fontsize=8, bbox_to_anchor=(0.5, 0.02))
    for t in leg.get_texts():
        t.set_color(INK2)
    fig.text(0.01, 0.005, "E2b best-of-N by coverage vs the sample pool", color=MUTED, fontsize=7)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def run(scores: Path, out_dir: Path, layouts: Path | None = None) -> list[dict]:
    scores = Path(scores)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    layouts = Path(layouts) if layouts else scores.with_name("layouts.jsonl")
    table = compare(load_rows(scores), load_rows(layouts))
    write_csv(out_dir / "e2b_bestofn.csv", FIELDS, table)
    plot(table, out_dir / "e2b_bestofn.png")
    return table


def main(argv: list[str] | None = None) -> None:
    p = base_parser(__doc__)
    p.add_argument("--layouts", help="layouts.jsonl with entity types (default: beside scores.jsonl)")
    args = p.parse_args(argv)
    table = run(Path(args.scores), Path(args.out_dir), args.layouts)
    groups = [r for r in table if r["envelope_id"] != "ALL"]
    print(f"E2b: {len(groups)} (model, envelope) groups with N>=2 -> {args.out_dir}/e2b_bestofn.{{csv,png}}")
    for r in table:
        if r["envelope_id"] == "ALL":
            tag, pool_u, pool_h = "ALL (aggregate types)", r["pool_agg_unique"], r["pool_agg_entropy"]
            print(f"  {r['model']:<24} random one-per-room entropy {r['rand_entropy_mean']:.2f} "
                  f"(p05 {r['rand_entropy_p05']:.2f}, p95 {r['rand_entropy_p95']:.2f}; "
                  f"{r['rand_frac_le_sel']:.3f} of draws <= selected); random tie-break "
                  f"{r['tb_entropy_mean']:.2f} ({r['tb_frac_rand_le']:.3f} of random draws <= it)")
        else:
            tag, pool_u, pool_h = r["envelope_id"], r["pool_mean_unique"], r["pool_mean_entropy"]
        print(f"  {r['model']:<24} {tag:<28} N={r['n']:<3} unique sel {r['sel_unique']:>4} vs pool "
              f"{pool_u:5.2f}   entropy sel {r['sel_entropy']:.2f} vs pool {pool_h:.2f}")
    if not groups:
        print("  no groups: run the sweep with --samples N (N >= 2) first")


if __name__ == "__main__":
    main()

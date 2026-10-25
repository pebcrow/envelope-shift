"""Shared I/O, statistics and plot chrome for the analysis scripts.

Each `e*_...py` module reads the scores.jsonl written by `run.py score`,
writes one CSV and one PNG into an output directory, and prints a short
summary. Only matplotlib and numpy are used; there is no pandas.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

PUBLISHED = ["coverage", "navigability", "overlap_clearance"]
TIERS = ["T0", "T1", "T2", "T3", "T4", "T5"]

# Chart chrome. Categorical slots are used in fixed order, never cycled. The first eight are the
# original palette and keep their colours; slots 9-14 were appended (when the pooled
# corpus reached nine arms) and are fixed too, so an arm's colour depends only on its position
# in the sorted arm list, never on the run. Fifteen arms still raise: facet instead.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948",
          "#00a3b8", "#8c5a2b", "#8f9a00", "#b03aa8", "#5b7083", "#7fb5f5"]
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
DIVERGING = ("#2a78d6", "#f0efec", "#e34948")  # blue <-> gray <-> red


def load_rows(path: Path) -> list[dict]:
    with Path(path).open() as f:
        return [json.loads(line) for line in f if line.strip()]


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with Path(path).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: _fmt(r.get(k)) for k in fieldnames})


def _fmt(v):
    if isinstance(v, float):
        return "" if math.isnan(v) else f"{v:.4f}"
    return v


def bootstrap_ci(values, n_boot: int = 2000, alpha: float = 0.05, seed: int = 0) -> tuple[float, float, float]:
    """Mean and percentile bootstrap CI. NaNs everywhere if there are no values."""
    x = np.asarray(values, dtype=float)
    if x.size == 0:
        return math.nan, math.nan, math.nan
    if x.size == 1:
        return float(x[0]), float(x[0]), float(x[0])
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, x.size, size=(n_boot, x.size))
    means = x[idx].mean(axis=1)
    lo, hi = np.percentile(means, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    m = float(x.mean())
    # The bootstrap distribution brackets the sample mean up to resampling noise;
    # clamp so reported bounds always bracket the reported mean.
    return m, min(float(lo), m), max(float(hi), m)


def rankdata(x) -> np.ndarray:
    """Average ranks (1-based), ties share the mean rank."""
    x = np.asarray(x, dtype=float)
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(x.size, dtype=float)
    ranks[order] = np.arange(1, x.size + 1)
    sx = x[order]
    i = 0
    while i < x.size:
        j = i
        while j + 1 < x.size and sx[j + 1] == sx[i]:
            j += 1
        if j > i:
            ranks[order[i : j + 1]] = (i + j + 2) / 2.0
        i = j + 1
    return ranks


def spearman(x, y) -> float:
    """Spearman rho as Pearson correlation of average ranks. NaN if undefined."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if x.size < 3 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return math.nan
    rx, ry = rankdata(x), rankdata(y)
    rx -= rx.mean()
    ry -= ry.mean()
    return float((rx * ry).sum() / math.sqrt((rx * rx).sum() * (ry * ry).sum()))


def shannon_entropy(counts) -> float:
    """Entropy in bits of a categorical distribution given as counts."""
    c = np.asarray(list(counts), dtype=float)
    c = c[c > 0]
    if c.size == 0:
        return 0.0
    p = c / c.sum()
    return float(-(p * np.log2(p)).sum())


def style_axes(ax) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
        ax.spines[side].set_linewidth(1)
    ax.tick_params(colors=MUTED, labelcolor=INK2, length=0)
    ax.grid(True, axis="y", color=GRID, linewidth=1, linestyle="-")
    ax.set_axisbelow(True)
    ax.title.set_color(INK)
    ax.xaxis.label.set_color(INK2)
    ax.yaxis.label.set_color(INK2)


def new_figure(ncols: int, width: float = 4.2, height: float = 3.6):
    fig, axes = plt.subplots(1, ncols, figsize=(width * ncols, height), squeeze=False)
    fig.patch.set_facecolor(SURFACE)
    return fig, list(axes[0])


def legend(ax, **kw) -> None:
    leg = ax.legend(frameon=False, labelcolor=INK2, fontsize=8, **kw)
    for t in leg.get_texts():
        t.set_color(INK2)


def model_colors(models: list[str]) -> dict[str, str]:
    if len(models) > len(SERIES):
        raise SystemExit(f"{len(models)} models exceed the {len(SERIES)} categorical slots; facet instead")
    return {m: SERIES[i] for i, m in enumerate(models)}


def base_parser(doc: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=doc)
    p.add_argument("scores", help="scores.jsonl written by `envelope-shift score`")
    p.add_argument("out_dir", help="directory for the CSV and PNG")
    return p

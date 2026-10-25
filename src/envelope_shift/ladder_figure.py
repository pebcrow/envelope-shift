"""The tier ladder as one figure and one animation: the same room getting stranger.

    uv run python -m envelope_shift.ladder_figure [out_dir]

Writes ``ladder.png`` (six panels side by side) and ``ladder.gif`` (the same six as frames)
into ``out_dir`` (default ``report/figures``).

Every panel is a PRIMARY BEDROOM, so the variable a reader sees change across the ladder is
the envelope and nothing else. Room type is otherwise confounded with tier: coverage scores
against a per-type inventory, so a kitchen panel beside a bedroom panel would show two things
changing at once. T0-T3 and T5 have a primary bedroom to spare; T4's gable attic is the
primary bedroom under a roof plane, which is the tier's whole point.

The panels are drawn EMPTY. This figure is about what the model is asked to furnish, not
about any particular layout, and an empty envelope is the one thing every arm shares.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon

import numpy as np

from .envelopes import load_all
from .figures import DOOR, ROOM, WALL, WINDOW
from .geometry import envelope_polygon, headroom_at, opening_segment
from .inventory import inventory_for

#: One primary bedroom per tier, in ladder order. Chosen for a coherent sequence, not for
#: results: none of these ids is singled out anywhere in the report.
LADDER: tuple[tuple[str, str], ...] = (
    ("t0_pbed_14x16",      "typical, rectangular"),
    ("t1_pbed_9x22",       "long and narrow, 9 ft wide"),
    ("t2_pbed_L",          "L-shaped"),
    ("t3_pbed_chamfer",    "45-degree chamfer"),
    ("t4_pbed_attic_gable", "gable attic, sloped ceiling"),
    ("t5_pbed_nursery",    "ordinary shape, unconventional program"),
)

#: Headroom below this cannot take a full-height wardrobe, so it is the band a layout has to
#: work around. Drawn only where the envelope actually declares a slope.
LOW_HEADROOM_FT = 6.0


def _shade_low_headroom(ax, env, room) -> bool:
    """Hatch the floor a full-height entity cannot stand on. True if anything was drawn.

    T4's whole point is a constraint that does not exist in plan: a gable attic is a plain
    rectangle on the floor and an impossible room above about knee height. Without this the
    T4 panel is indistinguishable from T0 and the ladder appears to stop getting harder.
    """
    ceil = getattr(env, "ceiling", None)
    if not ceil or not getattr(ceil, "slope_wall", None):
        return False
    minx, miny, maxx, maxy = room.bounds
    xs = np.linspace(minx, maxx, 90)
    ys = np.linspace(miny, maxy, 90)
    grid = np.zeros((len(ys), len(xs)))
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            grid[j, i] = (1.0 if room.covers(__import__("shapely.geometry", fromlist=["Point"])
                                             .Point(x, y))
                          and headroom_at(env, x, y) < LOW_HEADROOM_FT else 0.0)
    if not grid.any():
        return False
    ax.contourf(xs, ys, grid, levels=[0.5, 1.5], colors=["none"], hatches=["////"])
    ax.contour(xs, ys, grid, levels=[0.5], colors=["#b45309"], linewidths=1.2)
    return True


def _panel(ax, env, caption: str) -> None:
    room = envelope_polygon(env)
    ax.add_patch(MplPolygon(list(room.exterior.coords), closed=True, fc=ROOM, ec=WALL, lw=3))
    shaded = _shade_low_headroom(ax, env, room)
    for o in env.openings:
        seg = opening_segment(env, o)
        (x0, y0), (x1, y1) = seg.coords[0], seg.coords[-1]
        ax.plot([x0, x1], [y0, y1], color=DOOR if o.kind == "door" else WINDOW,
                lw=6, solid_capstyle="butt")
    minx, miny, maxx, maxy = room.bounds
    pad = 1.0
    ax.set_xlim(minx - pad, maxx + pad)
    ax.set_ylim(miny - pad, maxy + pad)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    tier = env.atypicality.tier.value
    ax.set_title(f"{tier} — {caption}", fontsize=9)

    # T5 is an ordinary rectangle whose difficulty is entirely in the program, so name the
    # thing the inventory does not expect. Otherwise the last frame reads as a step backwards.
    sub = None
    if shaded:
        sub = f"hatched: under {LOW_HEADROOM_FT:.0f} ft of headroom"
    elif tier == "T5":
        expected = set(inventory_for(env.room_type).targets)
        extra = [w for w in env.atypicality.note.replace(",", " ").split()
                 if w.isalpha() and len(w) > 4 and w.lower() not in expected]
        sub = ", ".join(env.atypicality.declared_extraneous)
        sub = (sub[:58] + "…") if len(sub) > 59 else sub
    if sub:
        ax.set_xlabel(sub, fontsize=7.5, color="#444", labelpad=4)


def main(out_dir: Path) -> int:
    envs = {e.id: e for e in load_all()}
    missing = [i for i, _ in LADDER if i not in envs]
    if missing:
        print(f"ladder_figure: unknown envelope id(s): {', '.join(missing)}", file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)

    # One strip, six panels. Shared axes would squash the 9x22 room; each panel keeps its own
    # scale and says so by drawing no axis, because this figure compares SHAPE, not size.
    fig, axes = plt.subplots(1, len(LADDER), figsize=(3.3 * len(LADDER), 3.9))
    for ax, (eid, caption) in zip(axes, LADDER):
        _panel(ax, envs[eid], caption)
    fig.suptitle("The tier ladder — one primary bedroom, six envelopes", fontsize=11)
    fig.tight_layout()
    strip = out_dir / "ladder.png"
    fig.savefig(strip, dpi=140)
    plt.close(fig)
    print(f"wrote {strip}")

    # The same six as GIF frames. Rendered at one size so the frames do not jitter.
    frames = []
    for eid, caption in LADDER:
        f, ax = plt.subplots(figsize=(4.4, 4.9))
        _panel(ax, envs[eid], caption)
        f.tight_layout()
        tmp = out_dir / f"_ladder_frame_{eid}.png"
        f.savefig(tmp, dpi=130)
        plt.close(f)
        frames.append(tmp)

    from PIL import Image
    imgs = [Image.open(p).convert("P", palette=Image.ADAPTIVE) for p in frames]
    gif = out_dir / "ladder.gif"
    # 1.4 s a frame is long enough to read the caption; the last frame holds longer so the
    # loop does not snap away from T5, which is the one a reader wants to sit with.
    durations = [1400] * (len(imgs) - 1) + [2600]
    imgs[0].save(gif, save_all=True, append_images=imgs[1:], duration=durations, loop=0,
                 optimize=True)
    for p in frames:
        p.unlink()
    print(f"wrote {gif} ({len(imgs)} frames)")
    return 0


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("report/figures")
    raise SystemExit(main(out))

"""Rendered layouts and result plots.

    uv run python -m envelope_shift.figures render results/layouts.jsonl out/
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon

from .envelopes import load_all
from .geometry import door_clearance, entity_footprint, envelope_polygon, opening_segment
from .metrics import coverage, navigability, overlap_clearance
from .schema import Entity, Envelope

ROOM = "#f4f1ea"
WALL = "#2b2b2b"
ENTITY = "#7a9cc6"
TARGET = "#c66f5a"
DOOR = "#3a7d44"
WINDOW = "#5aa7c6"


def render(env: Envelope, entities: list[Entity], ax=None, title: str | None = None):
    own = ax is None
    if own:
        fig, ax = plt.subplots(figsize=(6, 6))
    room = envelope_polygon(env)
    ax.add_patch(MplPolygon(list(room.exterior.coords), closed=True, fc=ROOM, ec=WALL, lw=3))

    for o in env.openings:
        seg = opening_segment(env, o)
        (x0, y0), (x1, y1) = seg.coords[0], seg.coords[-1]
        ax.plot([x0, x1], [y0, y1], color=DOOR if o.kind == "door" else WINDOW, lw=6, solid_capstyle="butt")
        if o.kind == "door":
            cl = door_clearance(env, o)
            ax.add_patch(MplPolygon(list(cl.exterior.coords), closed=True, fc="none", ec=DOOR, ls=":", lw=1))

    from .inventory import inventory_for

    targets = set(inventory_for(env.room_type).targets)
    for e in entities:
        fp = entity_footprint(env, e)
        ax.add_patch(
            MplPolygon(list(fp.exterior.coords), closed=True,
                       fc=TARGET if e.type in targets else ENTITY, ec=WALL, lw=1, alpha=0.85)
        )
        cx, cy = fp.centroid.x, fp.centroid.y
        ax.text(cx, cy, e.type.replace("_", "\n"), ha="center", va="center", fontsize=6, color="white")

    minx, miny, maxx, maxy = room.bounds
    pad = 1.0
    ax.set_xlim(minx - pad, maxx + pad)
    ax.set_ylim(miny - pad, maxy + pad)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    if title is None:
        cov = coverage(env, entities).score
        nav = navigability(env, entities).score
        oc = overlap_clearance(env, entities).score
        title = f"{env.id}\ncov {cov:.0f}  nav {nav:.0f}  oc {oc:.1f}"
    ax.set_title(title, fontsize=9)
    if own:
        fig.tight_layout()
        return fig
    return ax


def render_file(layouts_path: Path, out_dir: Path) -> int:
    envs = {e.id: e for e in load_all()}
    out_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for line in layouts_path.open():
        rec = json.loads(line)
        if not rec.get("parse_ok"):
            continue
        env = envs[rec["envelope_id"]]
        ents = [Entity.model_validate(e) for e in rec["entities"]]
        fig = render(env, ents)
        fig.savefig(out_dir / f"{rec['model']}__{env.id}__s{rec.get('sample', 0)}.png", dpi=120)
        plt.close(fig)
        n += 1
    return n


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "render":
        print(f"rendered {render_file(Path(sys.argv[2]), Path(sys.argv[3]))} layouts")
    else:
        print(__doc__)

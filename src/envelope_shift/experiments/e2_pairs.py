"""E2: does a valid, better-to-live-in T5 layout score below a conventional one?

For four T5 rooms, two hand-authored layouts each:

    conventional    matches the room type's inventory and nothing else
    unconventional  the room furnished for the program its note describes:
                    plausible, geometrically valid, and arguably better to
                    live in for the household it serves

Both layouts must be valid: overlap_clearance < 1 and every door-to-target
path found. The only intended difference between the two is what the
inventory recognizes. No model is involved; every entity below was placed by
hand and checked against the metrics.

    uv run python -m envelope_shift.experiments.e2_pairs [out_dir]

writes <out_dir>/e2_<envelope_id>.png (both layouts side by side) and
<out_dir>/e2_pairs.csv (the table below, one row per layout),
<out_dir>/e2_coverage_gap.csv (where each pair's coverage gap comes from), and
prints the four-metric table. out_dir defaults to report/figures/.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from shapely.geometry import Point as ShPoint

from ..analysis._common import write_csv
from ..envelopes import load_all
from ..geometry import free_floor, wall_frame
from ..inventory import inventory_for
from ..metrics import score_all
from ..metrics.coverage import coverage
from ..params import DEFAULT
from ..schema import Entity, Envelope

ENVS: dict[str, Envelope] = {e.id: e for e in load_all()}

# Where the unconventional aging-in-place bath keeps its 5 ft turning circle
# (center, diameter in feet). Checked geometrically, not scored: none of the
# three published metrics can see it.
TURNING_CIRCLE: dict[str, tuple[tuple[float, float], float]] = {
    "t5_pbath_aging_in_place": ((5.25, 6.5), 5.0),
}


def _placer(env: Envelope):
    """Author entities on a `rect(W, D)` envelope by the center coordinate
    along the supporting wall, so the layouts below read as plan dimensions.

    wall 0 bottom (y=0)   center given as x
    wall 1 right  (x=W)   center given as y
    wall 2 top    (y=D)   center given as x
    wall 3 left   (x=0)   center given as y

    `offset` is the gap between the wall face and the entity's back edge, so
    an island is placed from wall 0 with offset = its near y.
    """
    xs = [v[0] for v in env.vertices]
    ys = [v[1] for v in env.vertices]
    W, D = max(xs), max(ys)
    assert env.n_walls == 4 and min(xs) == 0 and min(ys) == 0, f"{env.id}: not a rect(W, D) envelope"
    lengths = [wall_frame(env, i)[3] for i in range(4)]

    def place(
        type: str, wall: int, center: float, width: float, depth: float, height: float,
        offset: float = 0.0, elevation: float = 0.0,
    ) -> Entity:
        along = {0: center, 1: center, 2: W - center, 3: D - center}[wall]
        return Entity(
            type=type, wall=wall, t=along / lengths[wall], offset=offset,
            width=width, depth=depth, height=height, elevation=elevation,
        )

    return place


# --- t5_kitchen_laundry: kitchen 14 x 18 -------------------------------------
# Doors: wall 0 at x=2.1 (bottom-left) and wall 3 at y=2.7 (left, low).
# Window: wall 2 centered at x=7, 5 ft wide. Sink goes under it.


def _kitchen_laundry_core(P) -> list[Entity]:
    """L-shaped work triangle shared by both layouts: top wall run with the
    sink under the window, right wall run with range and refrigerator, and
    a 4 x 3 island with 2.5-3.5 ft aisles on every side."""
    return [
        P("base_cabinet", 2, 12.25, 3.5, 2.0, 3.0),
        P("dishwasher", 2, 9.5, 2.0, 2.0, 3.0),
        P("sink", 2, 7.0, 3.0, 2.0, 3.0),
        P("base_cabinet", 2, 4.0, 3.0, 2.0, 3.0),
        P("base_cabinet", 2, 1.25, 2.5, 2.0, 3.0),
        P("range", 1, 14.75, 2.5, 2.2, 3.0),
        P("base_cabinet", 1, 12.25, 2.5, 2.0, 3.0),
        P("refrigerator", 1, 9.5, 3.0, 2.75, 6.0),
        P("upper_cabinet", 2, 2.25, 4.5, 1.0, 2.5, elevation=4.5),
        P("upper_cabinet", 2, 11.75, 4.5, 1.0, 2.5, elevation=4.5),
        P("island", 0, 6.5, 4.0, 3.0, 3.0, offset=9.75),
    ]


def kitchen_laundry_conventional() -> list[Entity]:
    P = _placer(ENVS["t5_kitchen_laundry"])
    return _kitchen_laundry_core(P) + [
        # Tall pantry on the left wall, above the low side door.
        P("pantry", 3, 14.5, 3.0, 2.0, 7.0),
    ]


def kitchen_laundry_unconventional() -> list[Entity]:
    """The pantry bay becomes the laundry: side-by-side washer and dryer on
    the left wall with an upper cabinet over them for detergent and linens.
    One wet zone, one drain stack, no trip to a basement with a basket."""
    P = _placer(ENVS["t5_kitchen_laundry"])
    return _kitchen_laundry_core(P) + [
        P("dryer", 3, 14.625, 2.75, 2.25, 3.2),
        P("washer", 3, 11.875, 2.75, 2.25, 3.2),
        P("upper_cabinet", 3, 13.25, 5.5, 1.0, 2.5, elevation=4.5),
    ]


# --- t5_sbed_worknook: secondary bedroom 12 x 15 -----------------------------
# Door: wall 0 at x=2.4. Windows: wall 2 at x=8.4 and x=3.6, 3 ft each.


def sbed_worknook_conventional() -> list[Entity]:
    P = _placer(ENVS["t5_sbed_worknook"])
    return [
        P("bed_queen", 2, 6.0, 5.0, 6.7, 2.5),
        P("nightstand", 2, 2.4, 2.0, 1.5, 2.2),
        P("nightstand", 2, 9.6, 2.0, 1.5, 2.2),
        P("dresser", 1, 4.5, 5.0, 1.7, 2.8),
        # A loose desk and chair are tolerated by the inventory.
        P("desk", 3, 5.75, 4.5, 2.0, 2.5),
        P("chair", 3, 5.75, 1.6, 1.5, 3.0, offset=2.0),
    ]


def sbed_worknook_unconventional() -> list[Entity]:
    """The left wall becomes a built-in work alcove: a 6 ft desk surface with
    shelving above it, and a window seat under the right-hand window. The bed
    moves to the right wall so the alcove has the full left wall and the seat
    has the window."""
    P = _placer(ENVS["t5_sbed_worknook"])
    return [
        P("built_in_desk", 3, 6.5, 6.0, 2.2, 2.5),
        P("built_in_shelving", 3, 6.5, 6.0, 1.0, 3.0, elevation=4.5),
        P("chair", 3, 6.5, 1.6, 1.5, 3.0, offset=2.2),
        P("bed_full", 1, 9.0, 4.5, 6.25, 2.5),
        P("nightstand", 1, 12.125, 1.75, 1.5, 2.2),
        P("dresser", 0, 8.5, 5.0, 1.7, 2.8),
        P("window_seat", 2, 8.4, 3.0, 1.5, 1.5),
    ]


# --- t5_pbath_aging_in_place: primary bath 11 x 13 ---------------------------
# Door: wall 0 at x=2.2, 3 ft wide (clearance 3 ft deep). Window: wall 2 at x=5.5.


def pbath_aging_conventional() -> list[Entity]:
    P = _placer(ENVS["t5_pbath_aging_in_place"])
    return [
        P("bathtub", 2, 2.5, 5.0, 2.5, 1.8),
        P("shower_stall", 2, 9.5, 3.0, 3.0, 7.0),
        P("toilet", 1, 5.25, 2.5, 2.5, 2.5),
        P("vanity", 3, 7.0, 6.0, 1.75, 2.9),
        P("linen_cabinet", 0, 8.0, 2.0, 1.5, 7.0),
    ]


def pbath_aging_unconventional() -> list[Entity]:
    """Aging in place: a 5 x 3 curbless roll-in shower with a fold-down bench
    and a grab bar, a toilet set 18 in off the side wall with grab bars on
    both adjacent walls, a wall-hung roll-under vanity, and a 5 ft turning
    circle kept clear in the middle of the room (see TURNING_CIRCLE).

    The shower is modeled as its floor zone (a sloped pan, no curb) so the
    wall-mounted bench and bars sit above it without an overlap.
    """
    P = _placer(ENVS["t5_pbath_aging_in_place"])
    return [
        P("roll_in_shower", 2, 8.5, 5.0, 3.0, 0.25),
        P("shower_bench", 1, 11.5, 2.5, 1.25, 0.2, elevation=1.5),
        P("grab_bar", 2, 8.0, 3.0, 0.25, 0.125, elevation=2.75),
        P("toilet", 1, 2.0, 2.5, 2.5, 2.5),
        P("grab_bar", 0, 9.5, 3.0, 0.25, 0.125, elevation=2.75),
        P("grab_bar", 1, 2.0, 3.0, 0.25, 0.125, elevation=2.75),
        P("vanity", 3, 7.25, 4.5, 1.75, 1.0, elevation=2.25),
    ]


# --- t5_pbed_nursery: primary bedroom 15 x 17 --------------------------------
# Door: wall 0 at x=2.25. Windows: wall 2 at x=11.25 and x=3.75, 3 ft each.


def pbed_nursery_conventional() -> list[Entity]:
    P = _placer(ENVS["t5_pbed_nursery"])
    return [
        P("bed_king", 2, 7.5, 6.5, 7.0, 2.5),
        P("nightstand", 2, 3.0, 2.0, 1.5, 2.2),
        P("nightstand", 2, 12.0, 2.0, 1.5, 2.2),
        P("dresser", 1, 6.5, 5.0, 1.7, 2.8),
        P("tv_console", 0, 10.5, 5.0, 1.5, 2.0),
        P("bench", 2, 7.5, 4.0, 1.5, 1.5, offset=7.25),
    ]


def pbed_nursery_unconventional() -> list[Entity]:
    """First year with an infant: the bed slides left so the corner under the
    right window holds a crib, a changing table and a glider, all within a
    few steps of the bed at 3 am. Nothing is in the way of the door."""
    P = _placer(ENVS["t5_pbed_nursery"])
    return [
        P("bed_queen", 2, 4.5, 5.0, 6.7, 2.5),
        P("nightstand", 2, 1.0, 1.5, 1.5, 2.2),
        P("nightstand", 2, 8.25, 2.0, 1.5, 2.2),
        P("changing_table", 2, 11.75, 3.5, 1.5, 3.0),
        P("crib", 1, 12.75, 4.5, 2.5, 3.0),
        P("glider", 1, 7.75, 2.5, 2.5, 3.2),
        P("dresser", 0, 10.5, 5.0, 1.7, 2.8),
    ]


@dataclass(frozen=True)
class Pair:
    envelope_id: str
    conventional: list[Entity]
    unconventional: list[Entity]

    @property
    def env(self) -> Envelope:
        return ENVS[self.envelope_id]

    def __iter__(self):
        return iter((self.envelope_id, self.conventional, self.unconventional))


PAIRS: list[Pair] = [
    Pair("t5_kitchen_laundry", kitchen_laundry_conventional(), kitchen_laundry_unconventional()),
    Pair("t5_sbed_worknook", sbed_worknook_conventional(), sbed_worknook_unconventional()),
    Pair("t5_pbath_aging_in_place", pbath_aging_conventional(), pbath_aging_unconventional()),
    Pair("t5_pbed_nursery", pbed_nursery_conventional(), pbed_nursery_unconventional()),
]


def is_valid(row: dict) -> bool:
    """The validity bar both layouts of a pair must clear."""
    return row["overlap_clearance"] < 1.0 and row["nav_success_rate"] == 1.0


def turning_circle_clear(env: Envelope, entities: list[Entity], center: tuple[float, float], diameter: float) -> bool:
    return free_floor(env, entities).contains(ShPoint(*center).buffer(diameter / 2.0))


def score_pairs() -> list[dict]:
    rows = []
    for pid, conv, unconv in PAIRS:
        env = ENVS[pid]
        for label, ents in (("conventional", conv), ("unconventional", unconv)):
            row = {"envelope_id": pid, "layout": label, "n_entities": len(ents)}
            row.update(score_all(env, ents))
            row["valid"] = is_valid(row)
            rows.append(row)
    return rows


# Columns of e2_pairs.csv — the committed derived table section 5 cites. Row order
# is PAIRS order then conventional-before-unconventional, which is how score_pairs()
# emits them; nothing here depends on dict insertion order.
CSV_FIELDS = [
    "envelope_id", "layout", "n_entities", "coverage", "navigability",
    "nav_success_rate", "overlap_clearance", "exp_isovist_area_mean", "valid",
    "turning_circle_ft", "turning_circle_clear",
]


def csv_rows(rows: list[dict]) -> list[dict]:
    """score_pairs() rows plus the geometric turning-circle check, as CSV rows.

    The turning circle is the one property of the unconventional aging-in-place
    bath that no published metric can see, so it has to be a cell in the table
    rather than a sentence in the prose.
    """
    out = []
    for r in rows:
        pid = r["envelope_id"]
        circle = TURNING_CIRCLE.get(pid)
        row = {k: r[k] for k in CSV_FIELDS if k in r}
        row["turning_circle_ft"] = "" if circle is None else f"{circle[1]:.1f}"
        if circle is None or r["layout"] != "unconventional":
            row["turning_circle_clear"] = ""
        else:
            pair = next(p for p in PAIRS if p.envelope_id == pid)
            row["turning_circle_clear"] = str(
                turning_circle_clear(pair.env, pair.unconventional, circle[0], circle[1])
            )
        row["valid"] = str(r["valid"])
        out.append(row)
    return out


def write_table(rows: list[dict], out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "e2_pairs.csv"
    write_csv(path, CSV_FIELDS, csv_rows(rows))
    return path


# Columns of e2_coverage_gap.csv. One row per source of lost coverage in a pair: an
# expected inventory line a layout does not satisfy, or an off-inventory type it holds.
GAP_FIELDS = [
    "envelope_id", "source", "name", "declared", "n_lines",
    "conventional_lost", "unconventional_lost", "gap_points",
]


def coverage_gap_rows() -> list[dict]:
    """Decompose each pair's coverage gap into its sources, in coverage points.

    Coverage is 100 * (sum of line scores - penalty * extraneous types) / N, so every
    point lost is attributable: (1 - score) * 100/N for an unsatisfied line, and
    penalty * 100/N for each off-inventory type. `gap_points` is what the
    unconventional layout loses on that source beyond the conventional one, so the
    rows of a pair sum to its coverage gap. `declared` is whether the envelope's own
    declared_extraneous names the type ("" for a missing line).
    """
    out = []
    for pid, conv, unconv in PAIRS:
        env = ENVS[pid]
        n = inventory_for(env.room_type).n
        declared = set(env.atypicality.declared_extraneous)
        res = {"conv": coverage(env, conv), "unconv": coverage(env, unconv)}

        def lost(key: str, source: str, name: str) -> float:
            r = res[key]
            if source == "extraneous":
                return DEFAULT.coverage_extraneous_penalty * 100.0 / n if name in r.extraneous_types else 0.0
            return (1.0 - {**r.item_scores, **r.group_scores}[name]) * 100.0 / n

        sources = [("missing_line", k) for k in {**res["conv"].item_scores, **res["conv"].group_scores}]
        sources += [("extraneous", t) for t in sorted(set(res["conv"].extraneous_types)
                                                      | set(res["unconv"].extraneous_types))]
        for source, name in sources:
            c, u = lost("conv", source, name), lost("unconv", source, name)
            if c == 0.0 and u == 0.0:
                continue
            out.append({
                "envelope_id": pid, "source": source, "name": name,
                "declared": "" if source == "missing_line" else str(name in declared),
                "n_lines": n, "conventional_lost": c, "unconventional_lost": u, "gap_points": u - c,
            })
    return out


def write_coverage_gap(out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "e2_coverage_gap.csv"
    write_csv(path, GAP_FIELDS, coverage_gap_rows())
    return path


def format_table(rows: list[dict]) -> str:
    cols = [
        ("envelope_id", "{:<26}"), ("layout", "{:<14}"), ("n_entities", "{:>3}"),
        ("coverage", "{:>8.1f}"), ("navigability", "{:>8.1f}"), ("overlap_clearance", "{:>8.2f}"),
        ("exp_isovist_area_mean", "{:>8.1f}"), ("valid", "{:>5}"),
    ]
    head = ["envelope", "layout", "n", "cov", "nav", "oc", "isovist", "valid"]
    widths = [26, 14, 3, 8, 8, 8, 8, 5]
    out = ["  ".join(h.ljust(w) if i < 2 else h.rjust(w) for i, (h, w) in enumerate(zip(head, widths)))]
    out.append("  ".join("-" * w for w in widths))
    for r in rows:
        out.append("  ".join(fmt.format(str(r[k]) if k == "valid" else r[k]) for k, fmt in cols))
    return "\n".join(out)


def render_pairs(out_dir: Path) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from ..figures import render

    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for pid, conv, unconv in PAIRS:
        env = ENVS[pid]
        fig, axes = plt.subplots(1, 2, figsize=(11, 6))
        for ax, label, ents in zip(axes, ("conventional", "unconventional"), (conv, unconv)):
            row = score_all(env, ents)
            render(env, ents, ax=ax, title=(
                f"{pid} - {label}\ncov {row['coverage']:.0f}  nav {row['navigability']:.0f}  "
                f"oc {row['overlap_clearance']:.1f}  isovist {row['exp_isovist_area_mean']:.0f} sqft"
            ))
        fig.suptitle(env.atypicality.note, fontsize=8)
        fig.tight_layout()
        path = out_dir / f"e2_{pid}.png"
        fig.savefig(path, dpi=130)
        plt.close(fig)
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    out_dir = Path(argv[0]) if argv else Path(__file__).resolve().parents[3] / "report" / "figures"
    rows = score_pairs()
    print(format_table(rows))
    print()
    higher = sum(
        1 for a, b in zip(rows[0::2], rows[1::2]) if a["coverage"] > b["coverage"]
    )
    print(f"conventional coverage strictly higher in {higher} of {len(PAIRS)} pairs; "
          f"all valid: {all(r['valid'] for r in rows)}")
    for pid, (center, diam) in TURNING_CIRCLE.items():
        pair = next(p for p in PAIRS if p.envelope_id == pid)
        ok = turning_circle_clear(pair.env, pair.unconventional, center, diam)
        print(f"{pid}: {diam:.0f} ft turning circle at {center} clear in unconventional layout: {ok}")
    print(f"wrote {write_table(rows, out_dir)}")
    print(f"wrote {write_coverage_gap(out_dir)}")
    for path in render_pairs(out_dir):
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

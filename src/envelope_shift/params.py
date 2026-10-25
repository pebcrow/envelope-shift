"""Every parameter the published work does not specify, in one place.

The report's "chosen parameters" table is generated from this module, so a
value cannot be used anywhere without also being disclosed. Change values
here, not in the metric code.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields


@dataclass(frozen=True)
class Params:
    # --- Coverage --------------------------------------------------------
    # Penalty per extraneous entity *type* (not per instance), in the same
    # units as an item score (0..1). Published formula names the penalty but
    # not its magnitude.
    coverage_extraneous_penalty: float = 0.5
    # Cap the total extraneous penalty so a room cannot go negative.
    coverage_clamp_min: float = 0.0

    # --- Navigability ------------------------------------------------------
    # Published: Nav = 100 * (SR - 0.35 * DF). The 0.35 is published.
    nav_detour_weight: float = 0.35
    # Grid resolution for A* over free floor, feet. 0.5 ft = 6 inches.
    nav_grid_ft: float = 0.5
    # Radius of the walking body used to erode free floor, feet.
    nav_body_radius_ft: float = 0.75
    # How far in front of a door the path starts.
    nav_door_inset_ft: float = 0.5
    # Reach distance: a target is "arrived at" when the path reaches a free
    # cell within this distance of the target footprint.
    nav_reach_ft: float = 1.0
    # Ceiling on ONE pair's detour factor (path length / straight line - 1). The
    # ratio is unbounded as the straight line shrinks, so a pair whose endpoints
    # nearly coincide (a door whose interior point lands on a target footprint)
    # could otherwise drag Nav arbitrarily far below its declared floor. Nav =
    # 100 * (SR - 0.35 * DF) has floor -100 * 0.35 * cap, so 1.0 is exactly the
    # -35 the metric declares; a pair whose straight line is exactly zero walked
    # nowhere and scores no detour. Below the cap this changes no score.
    nav_detour_cap: float = 1.0
    # Whether a pair counts as reached when the door's interior point lies inside
    # the target's footprint. Such a fixture stands in the doorway and blocks it,
    # so the default is False: the pair is unreached, not a zero-length success.
    nav_door_on_target_reached: bool = False

    # --- Overlap & clearance ----------------------------------------------
    # Published: OC = w1*EOF + w2*GOA + w3*DCI + w4*WBV, weights unspecified.
    oc_w_entity_overlap_fraction: float = 0.25
    oc_w_global_overlap_area: float = 0.25
    oc_w_door_clearance_intrusion: float = 0.25
    oc_w_wall_bounds_violation: float = 0.25
    # Tolerance for "touching" vs "overlapping", square feet.
    oc_overlap_eps_sqft: float = 0.01
    # Entities whose bottom is at or above this height do not block walking
    # (upper cabinets over a counter, wall shelves). Feet.
    walk_clear_elevation_ft: float = 4.0

    # --- Vertical (T4 only) ------------------------------------------------
    # Fraction of an entity's height that may exceed local headroom before it
    # counts as a violation. 0 = strict.
    vertical_tolerance: float = 0.0

    # --- Experience axis (exploratory, unvalidated) ------------------------
    exp_sample_grid_ft: float = 1.0
    exp_isovist_rays: int = 180
    exp_isovist_max_ft: float = 60.0

    def as_table(self) -> list[tuple[str, str]]:
        return [(f.name, repr(getattr(self, f.name))) for f in fields(self)]

    def diff(self, other: Params) -> list[tuple[str, str, str]]:
        """(name, self value, other value) for every field that differs."""
        return [
            (f.name, repr(getattr(self, f.name)), repr(getattr(other, f.name)))
            for f in fields(self)
            if getattr(self, f.name) != getattr(other, f.name)
        ]


DEFAULT = Params()

# The calibration variant (SPEC.md A3). The first T0 run scored coverage 100
# and navigability ~100 on every room against a published frontier-LLM band
# of 76.4 / 45.7; the suspects are thin inventories (inventory.py), generous
# reach/body parameters, and handing the model the inventory. STRICT tightens
# only the unpublished parameters that plausibly separate us from the
# published harness. No metric formula changes; the published constants
# (nav_detour_weight) are untouched. Every other field is DEFAULT's.
STRICT = Params(
    # An extraneous entity *type* costs a full inventory line rather than
    # half of one: the published formula subtracts the penalty inside the
    # same (1/N) mean as the item scores, and the neutral reading of "one
    # penalty per extra" is one unit, not half.
    coverage_extraneous_penalty=1.0,
    # A target is reached only when the path gets within 6 in of its
    # footprint, i.e. the walker actually stands at the sink or bed edge
    # rather than a foot away from it.
    nav_reach_ft=0.5,
    # 24 in body diameter is the residential code minimum for a passage
    # (IRC R311 hall width is 36 in; 24 in clear is the usual furniture
    # walkway floor). 1.0 ft radius = 24 in diameter; DEFAULT's 0.75 ft
    # allows 18 in gaps, which no one walks through with a laundry basket.
    nav_body_radius_ft=1.0,
)

# Registry consumed by `envelope-shift score --params` and analysis/.
PARAM_SETS: dict[str, Params] = {"default": DEFAULT, "strict": STRICT}

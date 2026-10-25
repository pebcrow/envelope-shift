"""Overlap & clearance: OC = w1*EOF + w2*GOA + w3*DCI + w4*WBV. Lower is better.

Reimplemented from the published term names; the definitions below are ours
and the weights are ours (equal by default, see params.py). Each term is a
fraction in [0, 1] and OC is reported as a percentage so it sits on the same
scale as the published numbers.

    EOF  Entity Overlap Fraction    entities overlapping any other / entities
    GOA  Global Overlap Area        sum of pairwise overlap area / room area
    DCI  Door Clearance Intrusion   intruded clearance area / total clearance area
    WBV  Wall Bounds Violation      entity area outside envelope / total entity area

A fifth term, headroom violation, is computed but kept *out* of OC so the
published three-metric comparison stays clean. It is only meaningful on T4
envelopes and is reported alongside.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from shapely.ops import unary_union

from ..geometry import (
    door_clearance, entity_footprint, entity_min_headroom, envelope_polygon, vertical_ranges_overlap,
)
from ..params import DEFAULT, Params
from ..schema import Entity, Envelope


@dataclass(frozen=True)
class OverlapResult:
    score: float
    entity_overlap_fraction: float
    global_overlap_area: float
    door_clearance_intrusion: float
    wall_bounds_violation: float
    headroom_violation_fraction: float

    def as_dict(self) -> dict:
        return {
            "overlap_clearance": self.score,
            "oc_eof": self.entity_overlap_fraction,
            "oc_goa": self.global_overlap_area,
            "oc_dci": self.door_clearance_intrusion,
            "oc_wbv": self.wall_bounds_violation,
            "headroom_violation_fraction": self.headroom_violation_fraction,
        }


def overlap_clearance(env: Envelope, entities: list[Entity], params: Params = DEFAULT) -> OverlapResult:
    if not entities:
        return OverlapResult(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    room = envelope_polygon(env)
    fps = [entity_footprint(env, e) for e in entities]
    eps = params.oc_overlap_eps_sqft

    overlapping: set[int] = set()
    overlap_area = 0.0
    for (i, a), (j, b) in combinations(enumerate(fps), 2):
        if not vertical_ranges_overlap(entities[i], entities[j]):
            continue  # an upper cabinet over a base cabinet is not a conflict
        inter = a.intersection(b).area
        if inter > eps:
            overlapping.update((i, j))
            overlap_area += inter
    eof = len(overlapping) / len(fps)
    goa = min(overlap_area / room.area, 1.0)

    clearances = [door_clearance(env, d) for d in env.doors]
    if clearances:
        clear_union = unary_union(clearances)
        floor_fps = [f for f, e in zip(fps, entities) if e.elevation < params.walk_clear_elevation_ft]
        intruded = unary_union(floor_fps).intersection(clear_union).area if floor_fps else 0.0
        dci = min(intruded / clear_union.area, 1.0) if clear_union.area > 0 else 0.0
    else:
        dci = 0.0

    total_area = sum(f.area for f in fps)
    outside = sum(f.difference(room).area for f in fps)
    wbv = min(outside / total_area, 1.0) if total_area > 0 else 0.0

    tol = params.vertical_tolerance
    n_head = sum(1 for e in entities if e.top * (1 - tol) > entity_min_headroom(env, e))
    headroom = n_head / len(entities)

    score = 100.0 * (
        params.oc_w_entity_overlap_fraction * eof
        + params.oc_w_global_overlap_area * goa
        + params.oc_w_door_clearance_intrusion * dci
        + params.oc_w_wall_bounds_violation * wbv
    )
    return OverlapResult(score, eof, goa, dci, wbv, headroom)

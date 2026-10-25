"""Spatial experience axis. EXPLORATORY AND UNVALIDATED.

This is a proposed fourth axis, not a measurement of anything a person has
been asked about. It has not been validated against human preference and
this project does not attempt that validation. Treat every number from this
module as advisory. It exists to ask one question: do the three published
validity metrics leave room for layouts that pass everything and are still
unpleasant, and can that gap be pointed at with geometry alone?

Measures, from the isovist literature (Benedikt 1979) and space syntax:

    isovist_area       visible floor area from a standing point
    isovist_perimeter  boundary length of the visible region
    drift              distance from the viewpoint to the isovist centroid;
                       large drift means the space "pulls" away from you
    daylight_proxy     total angle (radians) subtended by window openings
                       with unobstructed sightline, from the viewpoint

Reported over a grid of standing points on free floor (mean, std), and as a
profile along the walking path from the main door to the primary target.
The variance along that path is the measurable form of what architects call
compression and release.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from shapely.geometry import LineString, Point as ShPoint, Polygon
from shapely.prepared import prep

from ..geometry import door_interior_point, entity_footprint, envelope_polygon, free_floor, opening_segment
from ..inventory import inventory_for
from ..params import DEFAULT, Params
from ..schema import Entity, Envelope
from .navigability import _Grid


@dataclass(frozen=True)
class ExperienceResult:
    exploratory: bool = True
    isovist_area_mean: float = 0.0
    isovist_area_std: float = 0.0
    drift_mean: float = 0.0
    daylight_mean: float = 0.0
    path_area_profile: tuple[float, ...] = ()
    path_area_std: float = 0.0
    n_samples: int = 0

    def as_dict(self) -> dict:
        return {
            "exp_exploratory": True,
            "exp_isovist_area_mean": self.isovist_area_mean,
            "exp_isovist_area_std": self.isovist_area_std,
            "exp_drift_mean": self.drift_mean,
            "exp_daylight_mean": self.daylight_mean,
            "exp_path_area_std": self.path_area_std,
            "exp_n_samples": self.n_samples,
        }


def isovist(obstructed: Polygon, x: float, y: float, n_rays: int, max_ft: float) -> Polygon | None:
    """Visible polygon from (x, y) inside `obstructed` (free floor), by ray casting.

    Entities are treated as full-height occluders, which is wrong for a bed
    and right for a wardrobe. A height-aware version is future work.
    """
    origin = ShPoint(x, y)
    if not obstructed.contains(origin):
        return None
    boundary = obstructed.boundary
    pts = []
    for k in range(n_rays):
        a = 2 * math.pi * k / n_rays
        ray = LineString([(x, y), (x + max_ft * math.cos(a), y + max_ft * math.sin(a))])
        hit = ray.intersection(boundary)
        if hit.is_empty:
            pts.append((x + max_ft * math.cos(a), y + max_ft * math.sin(a)))
            continue
        # Nearest intersection along the ray.
        geoms = getattr(hit, "geoms", [hit])
        best = None
        best_d = float("inf")
        for g in geoms:
            for c in getattr(g, "coords", []):
                d = math.hypot(c[0] - x, c[1] - y)
                if d < best_d:
                    best, best_d = c, d
        pts.append(best)
    poly = Polygon(pts)
    return poly if poly.is_valid else poly.buffer(0)


def daylight_proxy(env: Envelope, free: Polygon, x: float, y: float, n: int = 9) -> float:
    """Sum over windows of the angle subtended by the visible portion of each."""
    total = 0.0
    origin = (x, y)
    for w in env.windows:
        seg = opening_segment(env, w)
        (ax, ay), (bx, by) = seg.coords[0], seg.coords[-1]
        visible = 0
        for k in range(n):
            s = (k + 0.5) / n
            px, py = ax + s * (bx - ax), ay + s * (by - ay)
            # Pull the sample slightly inward so the sightline ends inside free floor.
            sight = LineString([origin, (px, py)])
            if free.buffer(1e-6).covers(sight):
                visible += 1
        if visible:
            a0 = math.atan2(ay - y, ax - x)
            a1 = math.atan2(by - y, bx - x)
            span = abs((a1 - a0 + math.pi) % (2 * math.pi) - math.pi)
            total += span * visible / n
    return total


def experience(env: Envelope, entities: list[Entity], params: Params = DEFAULT) -> ExperienceResult:
    free = free_floor(env, entities, params.walk_clear_elevation_ft)
    if free.is_empty:
        return ExperienceResult()
    prepared = prep(free)
    minx, miny, maxx, maxy = free.bounds
    step = params.exp_sample_grid_ft
    xs = np.arange(minx + step / 2, maxx, step)
    ys = np.arange(miny + step / 2, maxy, step)

    areas, drifts, lights = [], [], []
    for x in xs:
        for y in ys:
            if not prepared.contains(ShPoint(x, y)):
                continue
            iso = isovist(free, float(x), float(y), params.exp_isovist_rays, params.exp_isovist_max_ft)
            if iso is None or iso.is_empty:
                continue
            areas.append(iso.area)
            c = iso.centroid
            drifts.append(math.hypot(c.x - x, c.y - y))
            lights.append(daylight_proxy(env, free, float(x), float(y)))

    # Profile along the door -> primary-target path, reusing the nav grid.
    profile: list[float] = []
    inv = inventory_for(env.room_type)
    targets = [e for e in entities if e.type in inv.targets]
    if env.doors and targets:
        grid = _Grid(env, entities, params)
        dx, dy = door_interior_point(env, env.doors[0], params.nav_door_inset_ft)
        start = grid.nearest_free(dx, dy, params.nav_body_radius_ft * 2 + params.nav_reach_ft)
        goals = grid.goal_cells(
            entity_footprint(env, targets[0]).buffer(params.nav_reach_ft + params.nav_body_radius_ft)
        )
        path = grid.astar(start, goals) if (start and goals) else None
        if path:
            for cell in path:
                px, py = grid.to_xy(*cell)
                iso = isovist(free, px, py, params.exp_isovist_rays, params.exp_isovist_max_ft)
                if iso is not None and not iso.is_empty:
                    profile.append(iso.area)

    return ExperienceResult(
        isovist_area_mean=float(np.mean(areas)) if areas else 0.0,
        isovist_area_std=float(np.std(areas)) if areas else 0.0,
        drift_mean=float(np.mean(drifts)) if drifts else 0.0,
        daylight_mean=float(np.mean(lights)) if lights else 0.0,
        path_area_profile=tuple(profile),
        path_area_std=float(np.std(profile)) if profile else 0.0,
        n_samples=len(areas),
    )

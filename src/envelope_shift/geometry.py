"""Exact polygon geometry for envelopes and wall-referenced entities.

Everything downstream (all four metrics, the renderer) goes through here so
there is one definition of "where is this entity" and "what is free floor".
No rasterization; shapely polygons throughout, matching the published
approach of exact polygon geometry for overlap and clearance.
"""

from __future__ import annotations

import math

import numpy as np
from shapely.geometry import LineString, Point as ShPoint, Polygon
from shapely.affinity import rotate
from shapely.ops import unary_union

from .schema import Entity, Envelope, Opening


def envelope_polygon(env: Envelope) -> Polygon:
    poly = Polygon(env.vertices)
    if not poly.is_valid:
        raise ValueError(f"envelope {env.id} is not a valid simple polygon")
    return poly


def is_ccw(env: Envelope) -> bool:
    return Polygon(env.vertices).exterior.is_ccw


def wall_frame(env: Envelope, i: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """Return (start, unit_along, unit_inward_normal, length) for wall i.

    The inward normal points into the room regardless of vertex winding.
    """
    a, b = env.wall(i)
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = b - a
    length = float(np.hypot(*d))
    if length == 0:
        raise ValueError(f"wall {i} of {env.id} has zero length")
    u = d / length
    # Left-hand normal is inward for CCW polygons; flip for CW.
    n = np.array([-u[1], u[0]]) if is_ccw(env) else np.array([u[1], -u[0]])
    return a, u, n, length


def wall_point(env: Envelope, i: int, t: float, offset: float = 0.0) -> np.ndarray:
    a, u, n, length = wall_frame(env, i)
    return a + u * (t * length) + n * offset


def entity_footprint(env: Envelope, e: Entity) -> Polygon:
    """Plan-view rectangle of an entity in world coordinates.

    Anchor is the midpoint of the entity's back edge, `offset` feet in from the
    supporting wall face. Width runs along the wall, depth runs inward.
    Rotation is applied about the anchor.
    """
    a, u, n, length = wall_frame(env, e.wall)
    anchor = a + u * (e.t * length) + n * e.offset
    half_w = e.width / 2.0
    corners = [
        anchor - u * half_w,
        anchor + u * half_w,
        anchor + u * half_w + n * e.depth,
        anchor - u * half_w + n * e.depth,
    ]
    poly = Polygon([tuple(c) for c in corners])
    if e.rotation:
        poly = rotate(poly, e.rotation, origin=(anchor[0], anchor[1]))
    return poly


def opening_segment(env: Envelope, o: Opening) -> LineString:
    a, u, n, length = wall_frame(env, o.wall)
    c = a + u * (o.t * length)
    half = o.width / 2.0
    return LineString([tuple(c - u * half), tuple(c + u * half)])


def door_clearance(env: Envelope, o: Opening) -> Polygon:
    """Rectangle in front of a door that should stay free.

    The published Door Clearance Intrusion term is not specified beyond its
    name. We use a rectangle the width of the door and `swing_depth` deep
    (default: door width, i.e. a full inswing arc's bounding box). Configurable
    per opening; the choice is listed in the report's parameter table.
    """
    if o.kind != "door":
        raise ValueError("clearance only defined for doors")
    a, u, n, length = wall_frame(env, o.wall)
    depth = o.swing_depth if o.swing_depth is not None else o.width
    c = a + u * (o.t * length)
    half = o.width / 2.0
    return Polygon(
        [
            tuple(c - u * half),
            tuple(c + u * half),
            tuple(c + u * half + n * depth),
            tuple(c - u * half + n * depth),
        ]
    )


def door_interior_point(env: Envelope, o: Opening, inset: float = 0.5) -> tuple[float, float]:
    """A point just inside the room in front of a door; the start of every path."""
    p = wall_point(env, o.wall, o.t, inset)
    return float(p[0]), float(p[1])


def free_floor(env: Envelope, entities: list[Entity], walk_clear_elevation: float = 4.0) -> Polygon:
    """Envelope minus the footprints of entities that block walking.

    Entities elevated at or above `walk_clear_elevation` (upper cabinets, wall
    shelves) are not obstacles.
    """
    room = envelope_polygon(env)
    blocking = [e for e in entities if e.elevation < walk_clear_elevation]
    if not blocking:
        return room
    blocked = unary_union([entity_footprint(env, e) for e in blocking])
    return room.difference(blocked)


def vertical_ranges_overlap(a: Entity, b: Entity) -> bool:
    return a.elevation < b.top and b.elevation < a.top


def headroom_at(env: Envelope, x: float, y: float) -> float:
    """Ceiling height at a floor point, honoring a sloped-ceiling plane."""
    c = env.ceiling
    if c.slope_wall is None or c.slope_ft_per_ft == 0:
        return c.height
    a, u, n, length = wall_frame(env, c.slope_wall)
    dist = float(np.dot(np.array([x, y]) - a, n))
    h = c.height - c.slope_ft_per_ft * max(dist, 0.0)
    if c.min_height is not None:
        h = max(h, c.min_height)
    return h


def entity_min_headroom(env: Envelope, e: Entity) -> float:
    """Lowest ceiling over any corner of the entity's footprint."""
    fp = entity_footprint(env, e)
    return min(headroom_at(env, x, y) for x, y in list(fp.exterior.coords)[:-1])


def polygon_area(p: Polygon) -> float:
    return float(p.area)


def centroid(p: Polygon) -> tuple[float, float]:
    c = p.centroid
    return float(c.x), float(c.y)


def point_in(p: Polygon, x: float, y: float) -> bool:
    return p.contains(ShPoint(x, y))


def angle_deg(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))

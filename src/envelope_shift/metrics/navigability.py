"""Navigability: Nav = 100 * (SR - 0.35 * DF), range -35..100.

Reimplemented from the published formula. SR is the fraction of
door-to-target pairs with a collision-free path; DF is the mean detour
factor (path length / straight-line distance - 1) over successful pairs. Each
pair's detour is capped (params.nav_detour_cap) so the score cannot leave -35..100.

Unpublished choices (see params.py): the target list per room type, grid
resolution, the walking body radius used to erode free floor, and how a
path "reaches" a target. The pathfinder is a plain 8-connected A* on a grid
laid over the exact free-floor polygon; the polygon is exact, only the
search is discretized.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

import numpy as np
from shapely.geometry import Point as ShPoint
from shapely.prepared import prep

from ..geometry import door_interior_point, entity_footprint, free_floor
from ..inventory import inventory_for
from ..params import DEFAULT, Params
from ..schema import Entity, Envelope


@dataclass(frozen=True)
class PathResult:
    door: int
    target: str
    reachable: bool
    path_len: float
    # Reachable pairs: straight line between the path's own start and end cells, so
    # path_len >= straight_len. Unreachable pairs: door point to the target footprint.
    straight_len: float

    @property
    def detour(self) -> float:
        if not self.reachable or self.straight_len <= 0:
            return 0.0
        return max(self.path_len / self.straight_len - 1.0, 0.0)


@dataclass(frozen=True)
class NavigabilityResult:
    score: float
    success_rate: float
    mean_detour: float
    pairs: tuple[PathResult, ...]

    def as_dict(self) -> dict:
        return {
            "navigability": self.score,
            "nav_success_rate": self.success_rate,
            "nav_mean_detour": self.mean_detour,
            "nav_pairs": len(self.pairs),
        }


_NEIGHBORS = [
    (1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
    (1, 1, math.sqrt(2)), (1, -1, math.sqrt(2)), (-1, 1, math.sqrt(2)), (-1, -1, math.sqrt(2)),
]


class _Grid:
    def __init__(self, env: Envelope, entities: list[Entity], params: Params):
        walkable = free_floor(env, entities, params.walk_clear_elevation_ft).buffer(-params.nav_body_radius_ft)
        self.walkable = walkable
        self._prepared = prep(walkable)
        minx, miny, maxx, maxy = env_bounds(env)
        self.res = params.nav_grid_ft
        self.ox, self.oy = minx, miny
        self.nx = int(math.ceil((maxx - minx) / self.res)) + 1
        self.ny = int(math.ceil((maxy - miny) / self.res)) + 1
        self.free = np.zeros((self.nx, self.ny), dtype=bool)
        for i in range(self.nx):
            for j in range(self.ny):
                self.free[i, j] = self._prepared.contains(ShPoint(*self.to_xy(i, j)))

    def to_xy(self, i: int, j: int) -> tuple[float, float]:
        return self.ox + i * self.res, self.oy + j * self.res

    def nearest_free(self, x: float, y: float, max_r: float) -> tuple[int, int] | None:
        ci, cj = round((x - self.ox) / self.res), round((y - self.oy) / self.res)
        best, best_d = None, float("inf")
        r = int(math.ceil(max_r / self.res))
        for i in range(max(ci - r, 0), min(ci + r + 1, self.nx)):
            for j in range(max(cj - r, 0), min(cj + r + 1, self.ny)):
                if self.free[i, j]:
                    d = math.hypot(i - ci, j - cj)
                    if d < best_d:
                        best, best_d = (i, j), d
        return best

    def astar(self, start: tuple[int, int], goals: set[tuple[int, int]]) -> list[tuple[int, int]] | None:
        """Shortest path (list of cells) from start to any goal cell, or None."""
        if start in goals:
            return [start]
        gx = np.array([g[0] for g in goals])
        gy = np.array([g[1] for g in goals])

        def h(c: tuple[int, int]) -> float:
            return float(np.min(np.hypot(gx - c[0], gy - c[1])))

        open_heap = [(h(start), 0.0, start)]
        best_g = {start: 0.0}
        came_from: dict[tuple[int, int], tuple[int, int]] = {}
        while open_heap:
            f, g, cur = heapq.heappop(open_heap)
            if cur in goals:
                path = [cur]
                while cur in came_from:
                    cur = came_from[cur]
                    path.append(cur)
                return path[::-1]
            if g > best_g.get(cur, float("inf")):
                continue
            for di, dj, cost in _NEIGHBORS:
                nxt = (cur[0] + di, cur[1] + dj)
                if not (0 <= nxt[0] < self.nx and 0 <= nxt[1] < self.ny):
                    continue
                if not self.free[nxt]:
                    continue
                # Forbid diagonal corner-cutting through a blocked cell.
                if di and dj and not (self.free[cur[0] + di, cur[1]] and self.free[cur[0], cur[1] + dj]):
                    continue
                ng = g + cost
                if ng < best_g.get(nxt, float("inf")):
                    best_g[nxt] = ng
                    came_from[nxt] = cur
                    heapq.heappush(open_heap, (ng + h(nxt), ng, nxt))
        return None

    def path_length(self, path: list[tuple[int, int]]) -> float:
        return sum(
            math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(path, path[1:])
        ) * self.res

    def goal_cells(self, zone) -> set[tuple[int, int]]:
        return {
            (i, j)
            for i in range(self.nx)
            for j in range(self.ny)
            if self.free[i, j] and zone.contains(ShPoint(*self.to_xy(i, j)))
        }


def env_bounds(env: Envelope) -> tuple[float, float, float, float]:
    xs = [v[0] for v in env.vertices]
    ys = [v[1] for v in env.vertices]
    return min(xs), min(ys), max(xs), max(ys)


def navigability(env: Envelope, entities: list[Entity], params: Params = DEFAULT) -> NavigabilityResult:
    inv = inventory_for(env.room_type)
    targets = [e for e in entities if e.type in inv.targets]
    doors = env.doors
    if not doors or not targets:
        return NavigabilityResult(score=0.0, success_rate=0.0, mean_detour=0.0, pairs=())

    grid = _Grid(env, entities, params)
    pairs: list[PathResult] = []
    for di, door in enumerate(doors):
        dx, dy = door_interior_point(env, door, params.nav_door_inset_ft)
        start = grid.nearest_free(dx, dy, max_r=params.nav_body_radius_ft * 2 + params.nav_reach_ft)
        for tgt in targets:
            fp = entity_footprint(env, tgt)
            straight = fp.distance(ShPoint(dx, dy))
            if straight == 0.0 and not params.nav_door_on_target_reached:
                # The door's interior point lies inside the target: the fixture stands in the
                # doorway, so this door/target pair is unreached. Other targets from the same
                # door are still path-found as usual.
                pairs.append(PathResult(di, tgt.type, False, 0.0, 0.0))
                continue
            if start is None:
                pairs.append(PathResult(di, tgt.type, False, 0.0, straight))
                continue
            reach_zone = fp.buffer(params.nav_reach_ft + params.nav_body_radius_ft)
            goals = grid.goal_cells(reach_zone)
            path = grid.astar(start, goals) if goals else None
            if path is None:
                pairs.append(PathResult(di, tgt.type, False, 0.0, straight))
            else:
                # Both quantities span the SAME two realized points: the cell the walk
                # started on and the goal cell it reached. The door-to-footprint distance
                # above runs to the footprint itself, which the walk stops short of by
                # nav_reach_ft + nav_body_radius_ft, so it cannot be compared with this path.
                (sx, sy), (gx, gy) = grid.to_xy(*path[0]), grid.to_xy(*path[-1])
                pairs.append(PathResult(di, tgt.type, True, grid.path_length(path), math.hypot(gx - sx, gy - sy)))

    ok = [p for p in pairs if p.reachable]
    sr = len(ok) / len(pairs)
    df = float(np.mean([min(p.detour, params.nav_detour_cap) for p in ok])) if ok else 0.0
    score = 100.0 * (sr - params.nav_detour_weight * df)
    return NavigabilityResult(score=score, success_rate=sr, mean_detour=df, pairs=tuple(pairs))

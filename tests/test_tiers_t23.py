"""Tier-scoped geometric contracts for T2 (non-convex) and T3 (non-orthogonal).

T2 rooms must actually be non-convex; T3 rooms must have at least one wall that
is not parallel to an axis. Both tiers carry 8 rooms across >= 4 room types,
one line of atypicality note each, and openings that fit on their walls.
"""

import math

import pytest

from envelope_shift.envelopes import by_tier
from envelope_shift.geometry import envelope_polygon, is_ccw
from envelope_shift.schema import Tier

T2 = by_tier(Tier.T2_NONCONVEX)
T3 = by_tier(Tier.T3_NONORTHOGONAL)
ROOMS_PER_TIER = 8
MIN_ROOM_TYPES = 4
AXIS_EPS = 1e-9


def _ids(envs):
    return [e.id for e in envs]


def _wall_is_axis_parallel(a, b) -> bool:
    dx, dy = b[0] - a[0], b[1] - a[1]
    return abs(dx) < AXIS_EPS or abs(dy) < AXIS_EPS


@pytest.mark.parametrize("tier, envs", [(Tier.T2_NONCONVEX, T2), (Tier.T3_NONORTHOGONAL, T3)])
def test_tier_has_eight_rooms(tier, envs):
    assert len(envs) == ROOMS_PER_TIER, (tier, _ids(envs))


@pytest.mark.parametrize("tier, envs", [(Tier.T2_NONCONVEX, T2), (Tier.T3_NONORTHOGONAL, T3)])
def test_tier_covers_at_least_four_room_types(tier, envs):
    types = {e.room_type for e in envs}
    assert len(types) >= MIN_ROOM_TYPES, (tier, sorted(types))


@pytest.mark.parametrize("env", T2 + T3, ids=lambda e: e.id)
def test_room_is_valid_ccw_polygon(env):
    poly = envelope_polygon(env)  # raises on a self-intersecting or degenerate polygon
    assert poly.is_valid and poly.area > 20, env.id
    assert is_ccw(env), f"{env.id} is wound clockwise; CCW is the house convention"


@pytest.mark.parametrize("env", T2, ids=lambda e: e.id)
def test_t2_room_is_nonconvex(env):
    poly = envelope_polygon(env)
    hull = poly.convex_hull.area
    assert hull > poly.area * 1.02, (
        f"{env.id}: hull {hull:.1f} vs area {poly.area:.1f}; T2 rooms must be visibly non-convex"
    )


@pytest.mark.parametrize("env", T3, ids=lambda e: e.id)
def test_t3_room_has_a_non_axis_wall(env):
    slanted = [i for i in range(env.n_walls) if not _wall_is_axis_parallel(*env.wall(i))]
    assert slanted, f"{env.id}: every wall is axis-parallel; T3 rooms need a slanted or curved wall"


@pytest.mark.parametrize("env", T2 + T3, ids=lambda e: e.id)
def test_atypicality_brief_is_one_nonempty_line(env):
    note = env.atypicality.brief
    assert note.strip(), env.id
    assert "\n" not in note, env.id


@pytest.mark.parametrize("env", T2 + T3, ids=lambda e: e.id)
def test_openings_fit_within_their_walls(env):
    for o in env.openings:
        a, b = env.wall(o.wall)
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        lo, hi = o.t * length - o.width / 2, o.t * length + o.width / 2
        assert lo >= -1e-9 and hi <= length + 1e-9, (
            f"{env.id}: {o.kind} on wall {o.wall} spans [{lo:.2f}, {hi:.2f}] on a {length:.2f} ft wall"
        )

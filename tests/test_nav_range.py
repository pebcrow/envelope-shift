"""Navigability stays inside its declared range.

The detour factor is path length over straight line minus one, unbounded as the
straight line shrinks. A door whose interior point lands ON a target footprint
used to give a straight line of 0, which navigability floored at a tiny epsilon,
and scored -10,937,431.5. That clamp has been removed; the detour is now capped
by nav_detour_cap in params.py.
"""

from __future__ import annotations

import pytest
from shapely.geometry import Point as ShPoint

from envelope_shift.analysis.calibration import NAV_RANGE
from envelope_shift.envelopes import load_all
from envelope_shift.geometry import door_interior_point, entity_footprint
from envelope_shift.inventory import inventory_for
from envelope_shift.metrics import navigability
from envelope_shift.metrics.navigability import PathResult
from envelope_shift.params import DEFAULT, PARAM_SETS, Params
from envelope_shift.schema import Entity

ENVS = {e.id: e for e in load_all()}
LO, HI = NAV_RANGE


def _on_door(env, door, target: str) -> Entity:
    """A target whose footprint covers the point a path starts from at `door`."""
    return Entity(type=target, wall=door.wall, t=door.t, offset=0, width=3.0, depth=3.0, height=2.0)


def _door_on_target_layouts():
    for env in ENVS.values():
        if not env.doors:
            continue
        for target in inventory_for(env.room_type).targets:
            yield env, [_on_door(env, d, target) for d in env.doors]


@pytest.mark.parametrize("name", sorted(PARAM_SETS))
def test_door_interior_point_on_a_target_footprint_scores_in_range(name):
    params = PARAM_SETS[name]
    degenerate = 0
    for env, ents in _door_on_target_layouts():
        for door in env.doors:
            dx, dy = door_interior_point(env, door, params.nav_door_inset_ft)
            degenerate += sum(entity_footprint(env, e).distance(ShPoint(dx, dy)) == 0 for e in ents)
        nav = navigability(env, ents, params)
        assert LO <= nav.score <= HI, (env.id, nav.score)
    assert degenerate, "no layout put a door's interior point on a target: the test is vacuous"


def test_zero_straight_line_carries_no_detour():
    assert PathResult(0, "bed_king", True, 5.0, 0.0).detour == 0.0
    assert PathResult(0, "bed_king", True, 0.0, 0.0).detour == 0.0


def test_a_pair_that_nearly_coincides_is_capped_not_inflated():
    # Two cells one grid step apart joined by a 20 ft walk: detour 39 uncapped.
    assert PathResult(0, "bed_king", True, 20.0, 0.5).detour == pytest.approx(39.0)


def test_detour_cap_bounds_the_mean_and_pins_the_floor_to_the_declared_range():
    assert -100 * DEFAULT.nav_detour_weight * DEFAULT.nav_detour_cap == LO
    env = ENVS["t0_pbed_14x16"]
    bed = Entity(type="bed_queen", wall=2, t=0.5, offset=0, width=5, depth=6.7, height=2.5)
    barrier = Entity(type="nightstand", wall=0, t=0.45, offset=3, width=9, depth=1.5, height=2.2)
    free = navigability(env, [bed, barrier])
    assert free.mean_detour > 0.15
    capped = navigability(env, [bed, barrier], Params(nav_detour_cap=0.1))
    assert capped.mean_detour == pytest.approx(0.1)
    assert capped.score > free.score


@pytest.mark.parametrize("name", sorted(PARAM_SETS))
def test_the_cap_is_disclosed_in_the_published_parameter_table(name):
    from pathlib import Path

    table = (Path(__file__).parent.parent / "report" / "data" / f"params_{name}.md").read_text()
    assert "`nav_detour_cap`" in table


def test_a_fixture_on_the_only_door_blocks_it():
    # A target whose footprint covers the door's interior point stands in the doorway. With one
    # door there is no other way in, so the pair is unreached, not a zero-length success.
    cases = 0
    for env in ENVS.values():
        if len(env.doors) != 1:
            continue
        for target in inventory_for(env.room_type).targets:
            nav = navigability(env, [_on_door(env, env.doors[0], target)])
            assert nav.pairs[0].reachable is False, (env.id, target, nav.pairs[0])
            cases += 1
    assert cases, "no single-door envelope with a target type: the test is vacuous"


def test_a_target_clear_of_the_door_is_still_reached():
    # Negative control: the doorway rule must not touch a fixture that leaves the door point free.
    env = ENVS["t0_pbed_14x16"]
    bed = Entity(type="bed_queen", wall=2, t=0.5, offset=0, width=5, depth=6.7, height=2.5)
    dx, dy = door_interior_point(env, env.doors[0], DEFAULT.nav_door_inset_ft)
    assert entity_footprint(env, bed).distance(ShPoint(dx, dy)) > 2.0
    nav = navigability(env, [bed])
    assert [p.reachable for p in nav.pairs] == [True]

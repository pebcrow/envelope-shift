"""Contract tests for the T4 (sloped ceiling) and T5 (unconventional program) tiers."""

import numpy as np

from envelope_shift.envelopes import by_tier, load_all, t4_vertical, t5_program
from envelope_shift.geometry import envelope_polygon, headroom_at, point_in
from envelope_shift.inventory import inventory_for
from envelope_shift.schema import Tier

T4 = t4_vertical.build()
T5 = t5_program.build()



def _floor_samples(env, step: float = 0.5):
    """Interior floor points on a grid, well inside the wall faces."""
    poly = envelope_polygon(env)
    xs = [v[0] for v in env.vertices]
    ys = [v[1] for v in env.vertices]
    pts = []
    for x in np.arange(min(xs) + 0.1, max(xs), step):
        for y in np.arange(min(ys) + 0.1, max(ys), step):
            if point_in(poly, float(x), float(y)):
                pts.append((float(x), float(y)))
    assert len(pts) > 20, env.id
    return pts


# --- T4 ---------------------------------------------------------------------


def test_t4_has_exactly_eight_unique_rooms():
    assert len(T4) == 8
    assert len({e.id for e in T4}) == 8
    assert all(e.atypicality.tier == Tier.T4_VERTICAL for e in T4)


def test_t4_every_room_has_a_sloped_ceiling():
    for e in T4:
        c = e.ceiling
        assert c.slope_wall is not None, e.id
        assert 0 <= c.slope_wall < e.n_walls, e.id
        assert c.slope_ft_per_ft > 0, e.id
        assert c.min_height is not None and c.min_height < c.height, e.id


def test_t4_headroom_varies_by_at_least_two_feet():
    for e in T4:
        step = 0.5
        hs = [headroom_at(e, x, y) for x, y in _floor_samples(e, step)]
        lo, hi = min(hs), max(hs)
        assert hi - lo >= 2.0, f"{e.id}: headroom range {hi - lo:.2f} ft ({lo:.2f}..{hi:.2f})"
        # The high side reaches the nominal height and the low side reaches the
        # knee wall, each within one grid step of drop (no sample sits exactly
        # on a wall face).
        c = e.ceiling
        slack = c.slope_ft_per_ft * step + 1e-9
        assert hi >= c.height - slack, e.id
        assert lo <= c.min_height + slack, e.id
        assert lo >= c.min_height - 1e-9, e.id


def test_t4_covers_at_least_four_room_types():
    assert len({e.room_type for e in T4}) >= 4


# --- T5 ---------------------------------------------------------------------


def test_t5_has_at_least_eight_unique_rooms():
    # >= rather than == : a concurrent bead appends one more T5 room.
    assert len(T5) >= 8
    assert len({e.id for e in T5}) == len(T5)
    assert all(e.atypicality.tier == Tier.T5_PROGRAM for e in T5)


def test_t5_keeps_the_ids_other_beads_reference():
    ids = {e.id for e in T5}
    assert {"t5_kitchen_laundry", "t5_sbed_worknook", "t5_pbath_aging_in_place"} <= ids


def test_t5_declares_extraneous_elements_outside_the_brief():
    for e in T5:
        a = e.atypicality
        assert a.brief.strip(), e.id
        # The answer key is a held-out field, not a clause riding on the transmitted brief.
        assert "extraneous:" not in a.brief, e.id
        assert a.declared_extraneous, e.id
        assert all(t and t == t.strip() for t in a.declared_extraneous), e.id
        # Each declared type must really be outside the room type's expected inventory,
        # otherwise coverage would not penalize it and E2 would be pairing against nothing.
        expected = inventory_for(e.room_type).expected_types()
        for t in a.declared_extraneous:
            assert t not in expected, f"{e.id}: {t!r} is in the {e.room_type} inventory"


def test_only_t5_declares_extraneous_types():
    for e in load_all():
        if e.atypicality.tier != Tier.T5_PROGRAM:
            assert e.atypicality.declared_extraneous == [], e.id


def test_t5_covers_at_least_four_room_types():
    assert len({e.room_type for e in T5}) >= 4


def test_t4_t5_are_flat_ceilings_elsewhere_and_load_cleanly():
    # by_tier goes through load_all, which asserts global id uniqueness.
    assert len(by_tier(Tier.T4_VERTICAL)) == 8
    assert len(by_tier(Tier.T5_PROGRAM)) >= 8
    for e in load_all():
        if e.atypicality.tier != Tier.T4_VERTICAL:
            assert e.ceiling.slope_ft_per_ft == 0, e.id

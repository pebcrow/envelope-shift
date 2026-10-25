"""E2 contract: four hand-authored T5 pairs, every layout valid, and the
conventional layout out-scores the better-to-live-in one on coverage."""

from envelope_shift.experiments.e2_pairs import (
    ENVS, PAIRS, TURNING_CIRCLE, coverage_gap_rows, is_valid, score_pairs, turning_circle_clear,
)
from envelope_shift.geometry import entity_footprint, envelope_polygon
from envelope_shift.inventory import inventory_for
from envelope_shift.metrics import score_all

ROWS = score_pairs()


def test_four_pairs_over_distinct_t5_rooms():
    assert len(PAIRS) == 4
    ids = [p.envelope_id for p in PAIRS]
    assert len(set(ids)) == 4
    for pid in ids:
        assert ENVS[pid].atypicality.tier.value == "T5", pid


def test_every_layout_is_valid():
    # Acceptance 1: overlap_clearance < 1.0 and nav_success_rate == 1.0 for all eight.
    assert len(ROWS) == 8
    for r in ROWS:
        assert r["overlap_clearance"] < 1.0, (r["envelope_id"], r["layout"], r["overlap_clearance"])
        assert r["nav_success_rate"] == 1.0, (r["envelope_id"], r["layout"], r["nav_success_rate"])
        assert is_valid(r)


def test_every_entity_sits_inside_its_room():
    for pid, conv, unconv in PAIRS:
        room = envelope_polygon(ENVS[pid]).buffer(1e-6)
        for ents in (conv, unconv):
            for e in ents:
                assert room.contains(entity_footprint(ENVS[pid], e)), (pid, e.type)


def test_conventional_coverage_strictly_higher_in_at_least_three_pairs():
    # Acceptance 2.
    wins = 0
    for pid, conv, unconv in PAIRS:
        env = ENVS[pid]
        c = score_all(env, conv)["coverage"]
        u = score_all(env, unconv)["coverage"]
        wins += c > u
    assert wins >= 3, wins


def test_every_off_inventory_type_is_declared_by_its_envelope():
    # The stimulus carries only manipulations the envelope itself declares. Every type a
    # layout holds outside the room's expected inventory must be in the envelope's
    # declared_extraneous; otherwise coverage docks it (0.5/N per type) for something the
    # brief never named. This can fail: add an undeclared type to a layout and it does.
    for pid, conv, unconv in PAIRS:
        env = ENVS[pid]
        expected = inventory_for(env.room_type).expected_types()
        declared = set(env.atypicality.declared_extraneous)
        assert all(e.type in expected for e in conv), pid
        undeclared = {e.type for e in unconv} - expected - declared
        assert not undeclared, (pid, sorted(undeclared))


def test_declared_extraneous_types_are_used_by_the_unconventional_layout():
    # The other direction: a declaration nothing uses would hide an authoring drift.
    for pid, _conv, unconv in PAIRS:
        used = {e.type for e in unconv}
        assert set(ENVS[pid].atypicality.declared_extraneous) <= used, pid


def test_coverage_gap_decomposition_sums_to_each_pairs_gap():
    rows = coverage_gap_rows()
    for pid, conv, unconv in PAIRS:
        env = ENVS[pid]
        gap = score_all(env, conv)["coverage"] - score_all(env, unconv)["coverage"]
        mine = [r for r in rows if r["envelope_id"] == pid]
        assert abs(sum(r["gap_points"] for r in mine) - gap) < 1e-9, pid
        n = inventory_for(env.room_type).n
        for r in mine:
            if r["source"] == "extraneous":
                assert r["declared"] == "True", (pid, r["name"])
                assert abs(r["unconventional_lost"] - 50.0 / n) < 1e-9, (pid, r["name"])


def test_aging_in_place_bath_keeps_a_five_foot_turning_circle():
    for pid, (center, diameter) in TURNING_CIRCLE.items():
        pair = next(p for p in PAIRS if p.envelope_id == pid)
        assert turning_circle_clear(pair.env, pair.unconventional, center, diameter), pid

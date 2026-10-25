from envelope_shift.envelopes import load_all
from envelope_shift.geometry import entity_footprint, envelope_polygon, headroom_at
from envelope_shift.metrics import coverage, experience, navigability, overlap_clearance, score_all
from envelope_shift.schema import Entity

ENVS = {e.id: e for e in load_all()}


def good_bedroom():
    """A sensible layout for t0_pbed_14x16 (door on wall 0 at t=0.15, windows on wall 2)."""
    return [
        Entity(type="bed_king", wall=2, t=0.5, offset=0, width=6.5, depth=7.0, height=2.5),
        Entity(type="nightstand", wall=2, t=0.15, offset=0, width=2.0, depth=1.5, height=2.2),
        Entity(type="nightstand", wall=2, t=0.85, offset=0, width=2.0, depth=1.5, height=2.2),
        Entity(type="dresser", wall=0, t=0.7, offset=0, width=5.0, depth=1.7, height=2.8),
    ]


def test_envelopes_are_valid_polygons():
    for env in ENVS.values():
        assert envelope_polygon(env).is_valid, env.id
        assert envelope_polygon(env).area > 20, env.id


def test_footprint_inside_room_when_against_wall():
    env = ENVS["t0_pbed_14x16"]
    room = envelope_polygon(env)
    for e in good_bedroom():
        fp = entity_footprint(env, e)
        assert room.buffer(1e-6).contains(fp), e.type


def test_good_bedroom_scores_well():
    env = ENVS["t0_pbed_14x16"]
    ents = good_bedroom()
    cov = coverage(env, ents)
    assert cov.score == 100.0, cov
    oc = overlap_clearance(env, ents)
    assert oc.score == 0.0, oc
    nav = navigability(env, ents)
    assert nav.success_rate == 1.0, nav.pairs
    assert nav.score > 80, nav


def test_extraneous_item_lowers_coverage_even_when_inventory_complete():
    env = ENVS["t0_pbed_14x16"]
    ents = good_bedroom() + [
        Entity(type="reading_nook_builtin", wall=1, t=0.5, offset=0, width=4, depth=2, height=3)
    ]
    assert coverage(env, ents).score < 100.0


def test_missing_group_lowers_coverage():
    env = ENVS["t0_pbed_14x16"]
    ents = [e for e in good_bedroom() if not e.type.startswith("bed")]
    cov = coverage(env, ents)
    assert "bed" in cov.missing
    assert cov.score < 100.0


def test_overlap_detected():
    env = ENVS["t0_pbed_14x16"]
    ents = good_bedroom() + [
        Entity(type="dresser", wall=2, t=0.5, offset=1.0, width=5, depth=1.7, height=2.8)  # on the bed
    ]
    oc = overlap_clearance(env, ents)
    assert oc.entity_overlap_fraction > 0
    assert oc.global_overlap_area > 0


def test_door_clearance_intrusion():
    env = ENVS["t0_pbed_14x16"]
    # Door on wall 0 at t=0.15; park a dresser right in front of it.
    ents = [Entity(type="dresser", wall=0, t=0.15, offset=0.2, width=5, depth=1.7, height=2.8)]
    assert overlap_clearance(env, ents).door_clearance_intrusion > 0.5


def test_wall_bounds_violation():
    env = ENVS["t0_pbed_14x16"]
    ents = [Entity(type="dresser", wall=2, t=0.5, offset=0, width=5, depth=20, height=2.8)]
    assert overlap_clearance(env, ents).wall_bounds_violation > 0.1


def test_blocked_target_fails_navigation():
    env = ENVS["t0_pbed_14x16"]
    # Wall the bed off with a full-width dresser row.
    ents = [
        Entity(type="bed_queen", wall=2, t=0.5, offset=0, width=5, depth=6.7, height=2.5),
        Entity(type="dresser", wall=1, t=0.5, offset=0, width=16, depth=13, height=2.8),
    ]
    nav = navigability(env, ents)
    assert nav.success_rate < 1.0


def test_sloped_ceiling_headroom():
    env = ENVS["t4_sbed_attic"]
    # Slope wall is 2 (top, y=14). Near it headroom is 8; near wall 0 it is 4.
    assert abs(headroom_at(env, 6, 13.9) - 8.0) < 0.1
    assert headroom_at(env, 6, 0.1) == 4.0
    tall = [Entity(type="dresser", wall=0, t=0.5, offset=0, width=4, depth=1.5, height=5.0)]
    assert overlap_clearance(env, tall).headroom_violation_fraction == 1.0
    short = [Entity(type="dresser", wall=2, t=0.5, offset=0, width=4, depth=1.5, height=5.0)]
    assert overlap_clearance(env, short).headroom_violation_fraction == 0.0


def test_experience_axis_runs_and_is_labeled_exploratory():
    env = ENVS["t0_pbed_14x16"]
    r = experience(env, good_bedroom())
    assert r.exploratory is True
    assert r.n_samples > 20
    assert r.isovist_area_mean > 0


def test_score_all_flat_dict():
    env = ENVS["t0_office_10x11"]
    ents = [
        Entity(type="desk", wall=2, t=0.5, offset=0, width=5, depth=2.5, height=2.5),
        Entity(type="office_chair", wall=2, t=0.5, offset=2.5, width=2, depth=2, height=3),
        Entity(type="bookshelf", wall=1, t=0.5, offset=0, width=3, depth=1, height=6),
    ]
    row = score_all(env, ents)
    for k in ("coverage", "navigability", "overlap_clearance", "exp_exploratory"):
        assert k in row


def _bed_behind_barrier():
    """Queen bed on the far wall of t0_pbed_14x16 and a 9 ft nightstand-height barrier 3 ft in
    from the door wall, so the walk to the bed has to swing round the barrier's right end.

    The route is only ~1.3 ft longer than the open-floor one, which is the point: the pre-fix
    door-to-footprint straight line (9.1 ft) is longer than this whole path (8.5 ft), so the old
    code clamped the detour to 0 here."""
    bed = Entity(type="bed_queen", wall=2, t=0.5, offset=0, width=5, depth=6.7, height=2.5)
    barrier = Entity(type="nightstand", wall=0, t=0.45, offset=3, width=9, depth=1.5, height=2.2)
    return bed, barrier


def test_reachable_pairs_never_report_path_shorter_than_straight_line():
    # Invariant: path and straight line span the same two realized points.
    env = ENVS["t0_pbed_14x16"]
    bed, barrier = _bed_behind_barrier()
    for ents in (good_bedroom(), [bed], [bed, barrier]):
        for p in navigability(env, ents).pairs:
            if p.reachable:
                assert p.path_len >= p.straight_len - 1e-9, p


def test_path_is_never_shorter_than_straight_line_on_any_envelope():
    # The same invariant over the whole test set: every envelope with a door, every target type
    # its room type declares, one such entity standing on each door.
    from envelope_shift.inventory import inventory_for

    reachable = 0
    for env in ENVS.values():
        if not env.doors:
            continue
        for target in inventory_for(env.room_type).targets:
            ents = [
                Entity(type=target, wall=d.wall, t=d.t, offset=0, width=3.0, depth=3.0, height=2.0)
                for d in env.doors
            ]
            for p in navigability(env, ents).pairs:
                if p.reachable:
                    reachable += 1
                    assert p.path_len >= p.straight_len - 1e-9, (env.id, target, p)
    # 190 reachable before fixtures on a doorway counted as unreached, 32 after.
    assert reachable >= 25, f"only {reachable} reachable pairs: the guard is close to vacuous"


def test_detour_term_is_live_when_an_obstacle_forces_a_longer_route():
    # POSITIVE CONTROL: the invariant above is also satisfied by a metric that always reports
    # detour 0 (the pre-fix bug), so assert the term actually moves when a route is forced.
    env = ENVS["t0_pbed_14x16"]
    bed, barrier = _bed_behind_barrier()
    open_floor = navigability(env, [bed])
    blocked = navigability(env, [bed, barrier])
    assert blocked.success_rate == open_floor.success_rate == 1.0
    assert blocked.mean_detour > 0.15, blocked.pairs
    assert blocked.mean_detour > open_floor.mean_detour + 0.1
    # ...and it reaches the published score, not only the diagnostic field.
    assert blocked.score < open_floor.score - 0.35 * 100 * 0.1

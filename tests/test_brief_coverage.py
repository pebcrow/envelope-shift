"""Brief-aware coverage (report section 11): a no-op without a brief program, and the
incentive it creates where there is one."""

from __future__ import annotations

import pytest

from envelope_shift.analysis import e5_brief_coverage as e5
from envelope_shift.envelopes import load_all
from envelope_shift.experiments.e2_pairs import PAIRS
from envelope_shift.inventory import inventory_for
from envelope_shift.metrics.coverage import brief_inventory, coverage, coverage_brief
from envelope_shift.schema import Entity

ENVS = load_all()


def _entity(t: str) -> Entity:
    return Entity(type=t, wall=0, t=0.5, offset=0.0, width=1.0, depth=1.0, height=1.0, rotation=0.0)


def _standard(env) -> list[Entity]:
    """One entity per standard inventory line: a layout that ignores any brief."""
    ents = []
    for line in inventory_for(env.room_type).lines:
        t = getattr(line, "type", None) or line.alternatives[0]
        ents += [_entity(t)] * getattr(line, "count", 1)
    return ents


@pytest.mark.parametrize("env", [e for e in ENVS if not e.atypicality.declared_extraneous], ids=lambda e: e.id)
@pytest.mark.parametrize("mode", ["tolerate", "require"])
def test_without_a_declared_program_brief_aware_coverage_is_the_published_score(env, mode):
    ents = _standard(env) + [_entity("unrelated_thing")]
    assert brief_inventory(env, mode) == inventory_for(env.room_type)
    assert coverage_brief(env, ents, mode=mode) == coverage(env, ents)


@pytest.mark.parametrize("env", [e for e in ENVS if e.atypicality.declared_extraneous], ids=lambda e: e.id)
def test_adding_the_brief_program_lowers_published_raises_require_and_leaves_tolerate(env):
    base = _standard(env)
    full = base + [_entity(t) for t in e5.program(env)]
    assert coverage(env, full).score < coverage(env, base).score
    assert coverage_brief(env, full, mode="tolerate").score == coverage_brief(env, base, mode="tolerate").score
    assert coverage_brief(env, full, mode="require").score > coverage_brief(env, base, mode="require").score


def test_an_unknown_mode_is_refused():
    with pytest.raises(ValueError):
        brief_inventory(ENVS[0], "reward")


def test_on_the_hand_authored_pairs_require_never_prefers_the_layout_that_ignores_the_brief():
    rows = {(r["envelope_id"], r["layout"]): r for r in e5.pair_rows()}
    for pair in PAIRS:
        conv, unconv = rows[(pair.envelope_id, "conventional")], rows[(pair.envelope_id, "unconventional")]
        assert unconv["fulfilment"] > conv["fulfilment"]
        assert conv["published"] > unconv["published"]  # the section 5 finding
        assert unconv["require"] >= conv["require"]     # the fix

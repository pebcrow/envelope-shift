"""The atypicality brief must reach the model, and the scorer's answer key must not.

`envelope_prompt` used to serialise geometry only, so a T5 room's programmatic
atypicality (a laundry in the kitchen, an aging-in-place bath) never reached any model arm,
while the T5 notes ended with the coverage metric's answer key. The two halves are asserted
together on purpose: transmitting the note verbatim would pass the first and fail the second.
"""

import json
import re

import pytest

from envelope_shift.envelopes import DATA_DIR, load_all
from envelope_shift.generate import envelope_prompt
from envelope_shift.schema import Envelope, Tier

ENVS = load_all()
ARMS = [True, False]  # include_inventory: inventory-supplied, inventory-withheld


def _has_token(text: str, name: str) -> bool:
    # WHOLE token, never a substring: `washer` is inside `dishwasher`, a real kitchen
    # inventory line. Underscores are word characters, so `shower` is not in `roll_in_shower`.
    return re.search(r"(?<![0-9A-Za-z_])" + re.escape(name) + r"(?![0-9A-Za-z_])", text) is not None


@pytest.mark.parametrize("include_inventory", ARMS)
@pytest.mark.parametrize("env", ENVS, ids=lambda e: e.id)
def test_brief_reaches_the_prompt_at_every_tier(env, include_inventory):
    assert env.atypicality.brief.strip(), env.id
    assert env.atypicality.brief in envelope_prompt(env, include_inventory)


@pytest.mark.parametrize("include_inventory", ARMS)
@pytest.mark.parametrize(
    "env", [e for e in ENVS if e.atypicality.declared_extraneous], ids=lambda e: e.id
)
def test_declared_extraneous_never_reaches_the_prompt(env, include_inventory):
    text = envelope_prompt(env, include_inventory)
    for t in env.atypicality.declared_extraneous:
        assert not _has_token(text, t), f"{env.id}: {t!r} leaked into the prompt"


def test_every_t5_envelope_declares_something_to_hold_out():
    # Guards the guard: the test above is vacuous for an envelope with an empty list.
    t5 = [e for e in ENVS if e.atypicality.tier == Tier.T5_PROGRAM]
    assert t5 and all(e.atypicality.declared_extraneous for e in t5)


def test_whole_token_matcher_ignores_substrings():
    assert not _has_token("- dishwasher x1", "washer")
    assert not _has_token("roll_in_shower", "shower")
    assert _has_token("a washer and dryer", "washer")


def test_leak_half_catches_a_verbatim_note():
    # The pre-fix builder sent no note at all, so the leak half passes vacuously against it;
    # prove it is not vacuous by feeding it the verbatim-note prompt the rebuild plan proposed.
    env = next(e for e in ENVS if e.id == "t5_kitchen_laundry")
    verbatim = envelope_prompt(env) + "\nextraneous: " + ", ".join(env.atypicality.declared_extraneous)
    assert any(_has_token(verbatim, t) for t in env.atypicality.declared_extraneous)


def test_committed_json_matches_the_factories():
    # The 48 JSON files are a reading copy of the factories (envelopes.dump); a stale copy
    # would still carry the old `note` shape.
    for env in ENVS:
        path = DATA_DIR / env.atypicality.tier.value / f"{env.id}.json"
        assert Envelope.model_validate(json.loads(path.read_text())) == env, env.id

"""Every OpenAI-backend row records what the provider says ANSWERED (claim v6).

call_config.model is the id we REQUESTED. DeepSeek's upstream catalog stopped listing
`deepseek-v4-flash` while the id kept answering, and an id the provider no longer lists can be
re-aliased to a different backing model without our noticing. Only the response's own `model`
(and `system_fingerprint`, where the provider sends one) says what answered, so the sweep row
keeps them under call_config.observed, beside the requested id and never in place of it.

The fake client stands in for openai's ChatCompletion, in which `model` is a required str and
`system_fingerprint` is Optional[str] = None (openai 3.8.0, types/chat/chat_completion.py).
"""

from __future__ import annotations

import json

import pytest

from envelope_shift import generate as g
from envelope_shift import run
from envelope_shift.envelopes import load_all
from envelope_shift.failure import PARSE, TRANSPORT

REQUESTED = "deepseek-v4-flash-proxy"  # models.toml [deepseek]
ANSWERED = "deepseek-v4-flash-0921"
GOOD = "[]"


class _Client:
    """A fake OpenAI-compatible endpoint. `answer` holds the response attributes it returns;
    a key left out of it is a response object without that attribute."""

    answer: dict = {}
    reply: str = GOOD
    error: Exception | None = None

    def __init__(self, **_):
        self.chat = type("C", (), {"completions": self})()

    def create(self, **kwargs):
        if type(self).error is not None:
            raise type(self).error
        msg = type("M", (), {"content": type(self).reply})()
        body = {"choices": [type("Ch", (), {"message": msg})()], **type(self).answer}
        return type("R", (), body)()


@pytest.fixture
def wire(monkeypatch):
    import openai

    _Client.answer, _Client.reply, _Client.error = {}, GOOD, None
    monkeypatch.setattr(openai, "OpenAI", _Client)
    return _Client


def _sweep(out, model="deepseek"):
    run.main(["sweep", "--out", str(out), "--envelopes", "t0_kitchen_12x14", "--models", model])
    read = lambda n: [json.loads(ln) for ln in (out / n).read_text().splitlines()] if (out / n).exists() else []
    return read("layouts.jsonl"), read("transport_failures.jsonl")


def test_observed_model_row_records_what_answered_beside_what_was_requested(tmp_path, wire):
    wire.answer = {"model": ANSWERED, "system_fingerprint": "fp_abc123"}
    (row,), _ = _sweep(tmp_path)
    cfg = row["call_config"]
    assert cfg["model"] == REQUESTED  # still the requested id
    assert cfg["observed"] == {"model": ANSWERED, "system_fingerprint": "fp_abc123"}
    assert "observed" not in row  # it lives under call_config only
    assert {"backend", "reasoning", "sampling", "source"} <= cfg.keys()  # v6's own fields untouched


def test_observed_model_absent_fields_are_null_never_invented(tmp_path, wire):
    wire.answer = {"model": ANSWERED}  # a response with no system_fingerprint attribute at all
    (row,), _ = _sweep(tmp_path / "no_fingerprint")
    assert row["call_config"]["observed"] == {"model": ANSWERED, "system_fingerprint": None}

    wire.answer = {"model": None, "system_fingerprint": None}
    (row,), _ = _sweep(tmp_path / "explicit_null")
    assert row["call_config"]["observed"] == {"model": None, "system_fingerprint": None}

    wire.answer = {}  # a proxy that echoes neither
    (row,), _ = _sweep(tmp_path / "neither")
    assert row["call_config"]["observed"] == {"model": None, "system_fingerprint": None}
    assert row["call_config"]["model"] == REQUESTED


def test_observed_model_is_recorded_on_a_parse_failure_too(tmp_path, wire):
    wire.answer = {"model": ANSWERED, "system_fingerprint": "fp_x"}
    wire.reply = "I cannot lay this room out."
    (row,), failures = _sweep(tmp_path)
    assert failures == [] and row["failure_kind"] == PARSE
    assert row["call_config"]["observed"] == {"model": ANSWERED, "system_fingerprint": "fp_x"}
    assert row["call_config"]["model"] == REQUESTED


def test_observed_model_a_transport_failure_has_no_response_so_no_observed_block(tmp_path, wire):
    wire.answer = {"model": ANSWERED}
    wire.error = g.TransportError("nope", status=400)
    layouts, (row,) = _sweep(tmp_path)
    assert layouts == [] and row["failure_kind"] == TRANSPORT
    assert "observed" not in row["call_config"] and "observed" not in row
    assert row["call_config"]["model"] == REQUESTED


def test_observed_model_only_the_openai_transports_read_a_response_model():
    """A double that returns bare text, and the claude_cli/anthropic Response, carry no
    observed block: their conditions are recorded elsewhere (cli events, v8)."""
    spec = g.load_models()["deepseek"]
    env = next(iter(load_all()))
    assert g.generate(env, spec, transport=lambda *_: GOOD).observed is None
    assert g.generate(env, spec, transport=lambda *_: g.Response(GOOD)).observed is None
    told = {"model": "m", "system_fingerprint": None}
    assert g.generate(env, spec, transport=lambda *_: g.Response(GOOD, observed=told)).observed == told

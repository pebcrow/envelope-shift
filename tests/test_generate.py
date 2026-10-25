import json

import httpx2
import openai
import pytest

from envelope_shift import generate as g
from envelope_shift.envelopes import load_all
from envelope_shift.generate import CallFailed, ModelSpec, TransportError, generate, load_models, parse_entities
from envelope_shift.run import parse_model

ENVS = {e.id: e for e in load_all()}
OFFICE = ENVS["t0_office_10x11"]

GOOD_JSON = json.dumps([
    {"type": "desk", "wall": 2, "t": 0.5, "offset": 0, "width": 5, "depth": 2.5, "height": 2.5},
    {"type": "office_chair", "wall": 2, "t": 0.5, "offset": 2.5, "width": 2, "depth": 2, "height": 3},
    {"type": "bookshelf", "wall": 1, "t": 0.5, "offset": 0, "width": 3, "depth": 1, "height": 6},
])

SPEC = ModelSpec(name="fake", backend="openai", model="fake-1")


class FakeTransport:
    """Yields the scripted outcomes in order: an exception instance is raised, a string is returned."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, spec, system, user):
        self.calls += 1
        out = self.outcomes.pop(0)
        if isinstance(out, BaseException):
            raise out
        return out


def run(transport):
    sleeps: list[float] = []
    layout = generate(OFFICE, SPEC, transport=transport, sleep=sleeps.append)
    return layout, sleeps


# ----------------------------------------------------------------- models.toml


def test_parse_model_resolves_repo_models_toml():
    opus = parse_model("opus")
    assert opus.backend == "claude_cli"
    assert opus.model == "claude-opus-5"
    assert opus.temperature is None and opus.effort == "medium"
    assert parse_model("sonnet").model == "claude-sonnet-5"
    local = parse_model("local")
    assert local.backend == "openai" and local.base_url == "http://localhost:8000/v1"
    assert local.model == "qwen3-30b-a3b"


def test_parse_model_grammar_still_works_and_names_win():
    a = parse_model("anthropic:claude-haiku-4-5", models={})
    assert (a.backend, a.model, a.api_key_env) == ("anthropic", "claude-haiku-4-5", "ANTHROPIC_API_KEY")
    o = parse_model("openai:gpt-x@http://h:1/v1", models={})
    assert (o.backend, o.model, o.base_url) == ("openai", "gpt-x", "http://h:1/v1")
    assert parse_model("local", models={}) is g.LOCAL
    custom = {"local": ModelSpec("local", "openai", "other")}
    assert parse_model("local", custom).model == "other"
    with pytest.raises(SystemExit):
        parse_model("nope", models={})


def test_load_models_from_file(tmp_path):
    p = tmp_path / "models.toml"
    p.write_text('[x]\nbackend = "openai"\nmodel = "m"\ntemperature = 0.8\nmax_tokens = 12\n')
    specs = load_models(p)
    assert specs["x"] == ModelSpec("x", "openai", "m", temperature=0.8, max_tokens=12)
    assert load_models(tmp_path / "missing.toml") == {}
    p.write_text('[x]\nbackend = "openai"\nmodel = "m"\nbogus = 1\n')
    with pytest.raises(ValueError, match=r"\[x\]"):
        load_models(p)


# ----------------------------------------------------------------- retry


def test_429_then_success_is_retried_once():
    t = FakeTransport(TransportError("rate limited", 429), GOOD_JSON)
    layout, sleeps = run(t)
    assert layout.parse_ok and len(layout.entities) == 3
    assert t.calls == 2
    assert len(sleeps) == 1 and 1.0 <= sleeps[0] <= 2.0


def test_three_500s_record_error_without_raising():
    t = FakeTransport(*[TransportError("boom", 500)] * 3)
    layout, sleeps = run(t)
    assert not layout.parse_ok and layout.entities == []
    assert layout.error.startswith("call: boom")
    assert "exhausted after 3 attempts" in layout.error
    assert t.calls == 3
    assert len(sleeps) == 2 and sleeps[1] > sleeps[0]  # exponential


def test_connection_errors_are_retried():
    t = FakeTransport(ConnectionError("refused"), TransportError("no route"), GOOD_JSON)
    layout, sleeps = run(t)
    assert layout.parse_ok and t.calls == 3 and len(sleeps) == 2


def test_400_is_not_retried():
    t = FakeTransport(TransportError("bad request", 400), GOOD_JSON)
    layout, sleeps = run(t)
    assert not layout.parse_ok and "not retried" in layout.error
    assert t.calls == 1 and sleeps == []


def test_parse_failure_is_a_result_not_a_retry():
    t = FakeTransport("here is prose with no array", GOOD_JSON)
    layout, sleeps = run(t)
    assert not layout.parse_ok and layout.error.startswith("parse:")
    assert layout.raw == "here is prose with no array"
    assert t.calls == 1 and sleeps == []


def test_sdk_status_errors_are_classified():
    def sdk_error(status):
        resp = httpx2.Response(status, request=httpx2.Request("POST", "http://x"))
        return openai.APIStatusError("x", response=resp, body=None)

    assert g.is_retryable(sdk_error(429))
    assert g.is_retryable(sdk_error(503))
    assert not g.is_retryable(sdk_error(401))
    assert g.is_retryable(openai.APIConnectionError(request=httpx2.Request("POST", "http://x")))
    assert not g.is_retryable(KeyError("programming error"))


def test_call_with_retry_raises_callfailed_with_attempts():
    t = FakeTransport(TransportError("x", 502), TransportError("y", 503), TransportError("z", 504))
    with pytest.raises(CallFailed) as info:
        g.call_with_retry(t, SPEC, "s", "u", sleep=lambda s: None)
    assert info.value.attempts == 3 and info.value.exhausted
    assert isinstance(info.value.cause, TransportError)


def test_backoff_is_exponential_with_jitter():
    assert g.backoff_seconds(1, rng=lambda: 0.0) == 1.0
    assert g.backoff_seconds(2, rng=lambda: 0.0) == 2.0
    assert g.backoff_seconds(2, rng=lambda: 1.0) == 4.0


# ----------------------------------------------------------------- parsing


def test_parse_entities_strips_think_block():
    raw = "<think>\nLet me place the desk...\n[not json]\n</think>\n" + GOOD_JSON
    ents = parse_entities(raw)
    assert [e.type for e in ents] == ["desk", "office_chair", "bookshelf"]


def test_parse_entities_strips_fenced_and_unterminated_think():
    assert len(parse_entities("```json\n" + GOOD_JSON + "\n```")) == 3
    with pytest.raises(ValueError, match="no JSON array"):
        parse_entities("<think>still thinking when tokens ran out [")


def test_generate_via_mocked_transport_uses_think_stripping():
    t = FakeTransport("<think>hmm</think>" + GOOD_JSON)
    layout, _ = run(t)
    assert layout.parse_ok and layout.model == "fake"

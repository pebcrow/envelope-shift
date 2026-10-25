"""The reasoning configuration is declared, sent, and recorded on the row (claim v6).

The artifact's original honesty defect was not a wrong number. DeepSeek ran with thinking
DISABLED and GLM at reasoning_effort=low — both stated in models.toml the whole time — while
the report called them frontier. models.toml describes what a sweep would send TODAY; nothing
tied any existing row to the configuration that produced it, so the corpus could not
contradict the prose.

Re-running on Claude adds a second such variable, adaptive thinking at effort `high`, on a
transport layer no other oracle watches. Oracle v1 proved the atypicality brief reaches the
prompt, but v1 reads `envelope_prompt()` — it cannot see the request. These tests cover the
non-host-bound half: that the spec carries the setting, that the anthropic transport actually
puts it in the request, and that the row records what was sent rather than what the spec
merely holds. The host-bound half (every row in the canonical corpus) is oracle v6.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from envelope_shift.arm import arm_label, base_model
from envelope_shift.generate import ModelSpec, load_models

REPO = Path(__file__).resolve().parents[1]
ANTHROPIC_ARMS = ("opus", "sonnet")


# --- 1. the declaration exists and is explicit -----------------------------

# The API-key spec the anthropic transport tests below drive. models.toml no longer holds one:
# Claude is reached through the subscription (backend claude_cli), never a billed API key.
API_SPEC = ModelSpec(
    "opus", "anthropic", "claude-opus-5", api_key_env="ANTHROPIC_API_KEY",
    thinking="adaptive", effort="high",
)


@pytest.mark.parametrize("name", ANTHROPIC_ARMS)
def test_claude_arms_declare_effort_on_the_subscription_transport(name):
    """Not inherited from the provider default: effort medium is a stated choice (the author,
    2026-09-21), sent as --effort. The CLI has no thinking switch, so none is declared, and
    no api_key_env: the sweep path never touches a token-billed key."""
    spec = load_models()[name]
    assert spec.backend == "claude_cli"
    assert spec.effort == "medium"
    assert spec.thinking is None
    assert spec.reasoning() == {"effort": "medium"}
    raw = (REPO / "models.toml").read_text()
    assert "api_key_env" not in raw.split(f"[{name}]", 1)[1].split("\n[", 1)[0]


@pytest.mark.parametrize("name", ANTHROPIC_ARMS)
def test_anthropic_arms_carry_no_temperature(name):
    """Current Claude models reject sampling params with a 400, so the transport never sends
    one. A parameter that is not sent has no business in a published parameter table."""
    raw = (REPO / "models.toml").read_text()
    table = raw.split(f"[{name}]", 1)[1].split("\n[", 1)[0]
    assert "temperature" not in table, f"[{name}] still declares a temperature that is never sent"
    assert load_models()[name].call_config()["sampling"] == {}


def test_openai_arms_keep_their_reasoning_visible():
    """The two proxy arms the report called 'frontier'. Their settings were always in
    models.toml; the point of call_config is that they now reach the row too."""
    models = load_models()
    assert models["deepseek"].reasoning() == {"thinking": {"type": "disabled"}}
    assert models["glm"].reasoning() == {"reasoning_effort": "low"}
    assert models["local"].reasoning() == {}, "the local arm sends no reasoning configuration"


# --- 2. the transport actually sends it ------------------------------------

def test_anthropic_transport_sends_thinking_and_effort(monkeypatch):
    """The request body, not the config file. This is the layer v1 cannot see."""
    sent: dict = {}

    class _Messages:
        def create(self, **kwargs):
            sent.update(kwargs)
            return type("R", (), {"content": []})()

    class _Client:
        def __init__(self, **_):
            self.messages = _Messages()

    import anthropic

    from envelope_shift import generate as gen

    monkeypatch.setattr(anthropic, "Anthropic", _Client)
    monkeypatch.setattr(gen, "_api_key", lambda spec: "test-key")
    gen._call_anthropic(API_SPEC, "system", "user")

    assert sent["thinking"] == {"type": "adaptive"}
    assert sent["output_config"] == {"effort": "high"}
    assert "temperature" not in sent, "sampling params are a 400 on current Claude models"


def test_anthropic_transport_omits_what_is_not_declared(monkeypatch):
    """A spec with no reasoning declaration must send neither key, so the OpenAI-compatible
    arms and any future undeclared spec are untouched rather than silently defaulted."""
    sent: dict = {}

    class _Messages:
        def create(self, **kwargs):
            sent.update(kwargs)
            return type("R", (), {"content": []})()

    class _Client:
        def __init__(self, **_):
            self.messages = _Messages()

    import anthropic

    from envelope_shift import generate as gen

    monkeypatch.setattr(anthropic, "Anthropic", _Client)
    monkeypatch.setattr(gen, "_api_key", lambda spec: "test-key")
    bare = ModelSpec("bare", "anthropic", "claude-opus-5")
    gen._call_anthropic(bare, "system", "user")

    assert "thinking" not in sent
    assert "output_config" not in sent
    assert bare.reasoning() == {}


# --- 3. the row records what was sent --------------------------------------

def test_call_config_shape_is_what_v6_requires():
    cfg = load_models()["opus"].call_config()
    assert set(cfg) >= {"backend", "model", "reasoning", "source"}
    assert cfg["model"] == "claude-opus-5", "the provider id, never the arm label"
    assert cfg["source"] == "recorded"
    assert load_models()["opus"].call_config("backfilled")["source"] == "backfilled"


def test_reasoning_is_an_empty_object_not_a_missing_key():
    """'none sent' and 'not recorded' have to be different states. A spec that sends no
    reasoning configuration still carries the key, with {} — otherwise a row that forgot to
    record is indistinguishable from one that deliberately sent nothing."""
    cfg = load_models()["local"].call_config()
    assert "reasoning" in cfg
    assert cfg["reasoning"] == {}


def test_backfill_resolves_the_arm_to_its_model(tmp_path: Path):
    """The arm is the prompt condition, not a different model: glm-noinv is the glm spec."""
    assert base_model("glm-noinv") == "glm"
    assert base_model("glm") == "glm"
    assert base_model(arm_label("glm", include_inventory=False)) == "glm"


def test_backfill_stamps_and_is_idempotent(tmp_path: Path):
    from envelope_shift.run import main as run_main

    raw = tmp_path / "layouts.jsonl"
    raw.write_text(json.dumps({
        "envelope_id": "t0_kitchen_12x14", "model": "glm-noinv", "sample": 0,
        "parse_ok": True, "entities": [], "include_inventory": False,
    }) + "\n")

    run_main(["backfill-call-config", str(raw)])
    row = json.loads(raw.read_text())
    assert row["call_config"]["model"] == "glm-5-3-proxy"
    assert row["call_config"]["reasoning"] == {"reasoning_effort": "low"}
    assert row["call_config"]["source"] == "backfilled", "a reconstruction is not a recording"

    before = raw.read_bytes()
    run_main(["backfill-call-config", str(raw)])
    assert raw.read_bytes() == before, "a re-run must change nothing"


def test_backfill_refuses_an_arm_it_cannot_resolve(tmp_path: Path):
    """Refused rather than guessed at — the same stance failure.py takes on a failed row
    whose kind cannot be recovered."""
    from envelope_shift.run import main as run_main

    raw = tmp_path / "layouts.jsonl"
    raw.write_text(json.dumps({
        "envelope_id": "t0_kitchen_12x14", "model": "some-model-nobody-declared",
        "sample": 0, "parse_ok": True, "entities": [], "include_inventory": True,
    }) + "\n")
    with pytest.raises(SystemExit, match="refusing to guess"):
        run_main(["backfill-call-config", str(raw)])


def _row(**extra) -> str:
    return json.dumps({
        "envelope_id": "t0_kitchen_12x14", "model": "glm", "sample": 0,
        "parse_ok": True, "entities": [], "include_inventory": True, **extra,
    }) + "\n"


def test_backfill_takes_sampling_from_the_row_not_the_spec(tmp_path: Path):
    """A row sampled at 0.8 records 0.8, though the spec's temperature is 0.2."""
    from envelope_shift.run import main as run_main

    assert load_models()["glm"].temperature == 0.2
    raw = tmp_path / "layouts.jsonl"
    raw.write_text(_row(temperature=0.8))
    run_main(["backfill-call-config", str(raw)])
    assert json.loads(raw.read_text())["call_config"]["sampling"] == {"temperature": 0.8}


def test_backfill_row_with_no_temperature_field_asserts_none(tmp_path: Path):
    from envelope_shift.run import main as run_main

    raw = tmp_path / "layouts.jsonl"
    raw.write_text(_row())
    run_main(["backfill-call-config", str(raw)])
    sampling = json.loads(raw.read_text())["call_config"]["sampling"]
    assert sampling.get("temperature") is None
    assert sampling["recorded"] is False


def test_backfill_row_that_sent_no_temperature_records_empty_sampling(tmp_path: Path):
    from envelope_shift.run import main as run_main

    raw = tmp_path / "layouts.jsonl"
    raw.write_text(_row(temperature=None))
    run_main(["backfill-call-config", str(raw)])
    assert json.loads(raw.read_text())["call_config"]["sampling"] == {}


def test_restamp_corrects_backfilled_rows_and_never_touches_recorded_ones(tmp_path: Path):
    from envelope_shift.run import main as run_main

    spec_stamped = load_models()["glm"].call_config("backfilled")
    assert spec_stamped["sampling"] == {"temperature": 0.2}
    wrong = _row(temperature=0.8, call_config=spec_stamped)
    no_field = _row(sample=1, call_config=spec_stamped)
    recorded_cfg = load_models()["glm"].call_config("recorded")
    recorded = _row(sample=2, temperature=0.8, call_config=recorded_cfg)  # would disagree
    raw = tmp_path / "layouts.jsonl"
    raw.write_text(wrong + no_field + recorded)

    run_main(["backfill-call-config", str(raw)])
    assert raw.read_text() == wrong + no_field + recorded, "without --restamp nothing is corrected"

    run_main(["backfill-call-config", "--restamp", str(raw)])
    rows = [json.loads(line) for line in raw.read_text().splitlines()]
    assert rows[0]["call_config"]["sampling"] == {"temperature": 0.8}
    assert rows[0]["call_config"]["source"] == "backfilled"
    assert rows[1]["call_config"]["sampling"] == {"temperature": None, "recorded": False}
    assert raw.read_text().splitlines(keepends=True)[2] == recorded, "a recorded row is never re-stamped"

    once = raw.read_bytes()
    run_main(["backfill-call-config", "--restamp", str(raw)])
    assert raw.read_bytes() == once, "re-stamping is idempotent"

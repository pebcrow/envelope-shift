"""The claude_cli transport, provider-default sampling and `sweep --resume`.

Claude is reached through the Claude Code subscription, and the row stores what the CLI
EMITTED (its stream-json events and the argv) so that claim v8 can re-derive the condition
from the response instead of trusting the code that made the call. No test here calls the
CLI: `subprocess.run` is faked, fed by the two responses in fixtures/claude_cli_rows.json.
That fixture is synthetic: one row per arm with the shape of a real stream-json response
(init, thinking, assistant text, result) and invented ids; the argv is the one this code
builds for the kitchen envelope.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from envelope_shift import generate as g
from envelope_shift import run
from envelope_shift.envelopes import load_all
from envelope_shift.failure import PARSE, TRANSPORT
from envelope_shift.generate import CLAUDE_CMD_ENV, ModelSpec, generate, load_models
from envelope_shift.schema import Layout

REAL_RUN = subprocess.run  # the fake below patches the module attribute, oracle call needs the real one
FIXTURE = Path(__file__).parent / "fixtures" / "claude_cli_rows.json"
REAL = {r["model"]: r for r in json.loads(FIXTURE.read_text())}  # one recorded-shape row per arm
ENVS = {e.id: e for e in load_all()}
KITCHEN = ENVS["t0_kitchen_12x14"]  # the envelope both fixture rows are for
OPUS = load_models()["opus"]
SONNET = load_models()["sonnet"]


def _stdout(events: list[dict]) -> str:
    return "".join(json.dumps(e) + "\n" for e in events)


class FakeRun:
    """Stands in for subprocess.run: records the call, replies with what the CLI would."""

    def __init__(self, stdout: str = "", returncode: int = 0, stderr: str = "", raises=None):
        self.stdout, self.returncode, self.stderr, self.raises = stdout, returncode, stderr, raises
        self.calls: list[tuple[list[str], dict]] = []

    def __call__(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        if self.raises:
            raise self.raises
        return subprocess.CompletedProcess(cmd, self.returncode, self.stdout, self.stderr)


@pytest.fixture
def cli(monkeypatch):
    """A fake CLI replaying the fixture's opus response; the launcher prefix is the default."""
    monkeypatch.delenv(CLAUDE_CMD_ENV, raising=False)
    fake = FakeRun(_stdout(REAL["opus"]["cli"]["events"]))
    monkeypatch.setattr(g.subprocess, "run", fake)
    return fake


# ------------------------------------------------------------------ the invocation


def test_claude_cli_argv_is_the_one_permitted_invocation(cli):
    """Element for element the argv the fixture row recorded: model, --effort medium, --tools "",
    and the prompt and system this envelope and arm build. v8 compares it exactly."""
    generate(KITCHEN, OPUS)
    (cmd, kwargs), = cli.calls
    assert cmd == ["claude", *REAL["opus"]["cli"]["argv"]]
    argv = cmd[1:]
    assert argv[argv.index("--effort") + 1] == "medium"
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--model") + 1] == "claude-opus-5"
    assert "--effort" in argv and argv.count("--effort") == 1
    assert kwargs["stdin"] == subprocess.DEVNULL, "a CLI waiting on a terminal would hang the sweep"
    assert kwargs["timeout"] == g.CLI_TIMEOUT_SECONDS


def test_claude_cli_argv_follows_the_arm_and_the_inventory(cli):
    generate(KITCHEN, SONNET, include_inventory=False)
    (cmd, _), = cli.calls
    argv = cmd[1:]
    assert argv[argv.index("--model") + 1] == "claude-sonnet-5"
    assert argv[1] == g.envelope_prompt(KITCHEN, include_inventory=False)
    assert argv[argv.index("--system-prompt") + 1] == g.SYSTEM
    assert "Expected contents" not in argv[1]


def test_claude_cli_launcher_prefix_comes_from_the_environment(cli, monkeypatch):
    monkeypatch.setenv(CLAUDE_CMD_ENV, "wrapper --room 'a dir' --")
    generate(KITCHEN, OPUS)
    (cmd, _), = cli.calls
    assert cmd[:3] == ["wrapper", "--room", "a dir"] and cmd[3] == "--"
    assert cmd[4:] == REAL["opus"]["cli"]["argv"], "the recorded argv is what follows the prefix"


def test_claude_cli_refuses_to_run_without_a_declared_effort(cli):
    layout = generate(KITCHEN, ModelSpec("x", "claude_cli", "claude-opus-5", temperature=None))
    assert layout.failure_kind == TRANSPORT and layout.raw is None
    assert cli.calls == []


# ------------------------------------------------------------------ the response


def test_claude_cli_stores_the_events_and_raw_is_the_result_text(cli):
    layout = generate(KITCHEN, OPUS)
    real = REAL["opus"]
    assert layout.parse_ok and layout.entities
    assert layout.raw == real["cli"]["events"][-1]["result"]
    assert layout.raw == real["raw"]
    assert layout.cli == {"argv": real["cli"]["argv"], "events": real["cli"]["events"]}


def test_claude_cli_drops_only_the_host_paths_of_the_init_event(monkeypatch):
    events = copy.deepcopy(REAL["sonnet"]["cli"]["events"])
    events[0] = {**events[0], "cwd": "/host/dir", "messaging_socket_path": "/host/sock"}
    monkeypatch.delenv(CLAUDE_CMD_ENV, raising=False)
    monkeypatch.setattr(g.subprocess, "run", FakeRun(_stdout(events)))
    layout = generate(KITCHEN, SONNET)
    stored = layout.cli["events"]
    assert stored == REAL["sonnet"]["cli"]["events"], "everything else is verbatim, nothing added"
    assert "cwd" not in stored[0] and "messaging_socket_path" not in stored[0]
    assert len(stored) == len(events) and [e["type"] for e in stored] == [e["type"] for e in events]


def test_claude_cli_row_records_the_condition_the_cli_ran_under(cli):
    cfg = OPUS.call_config()
    assert cfg == REAL["opus"]["call_config"]
    assert cfg == {"backend": "claude_cli", "model": "claude-opus-5",
                   "reasoning": {"effort": "medium"}, "sampling": {}, "source": "recorded"}


def test_claude_cli_a_reply_that_does_not_parse_is_a_parse_failure_with_its_evidence(monkeypatch):
    events = copy.deepcopy(REAL["opus"]["cli"]["events"])
    events[-1]["result"] = "I cannot lay this room out."
    monkeypatch.setattr(g.subprocess, "run", FakeRun(_stdout(events)))
    layout = generate(KITCHEN, OPUS)
    assert layout.failure_kind == PARSE and not layout.parse_ok
    assert layout.raw == "I cannot lay this room out."
    assert layout.cli["events"] == events, "a response was received, so it is stored"


# ------------------------------------------------------------------ transport failures


def _failing(events_edit):
    events = copy.deepcopy(REAL["opus"]["cli"]["events"])
    events_edit(events[-1])
    return _stdout(events)


@pytest.mark.parametrize(
    "fake",
    [
        FakeRun(_failing(lambda r: r.update(is_error=True, subtype="success",
                                            result="You've hit your usage limit"))),
        FakeRun(_failing(lambda r: r.update(is_error=True, subtype="error_during_execution"))),
        FakeRun("", returncode=1, stderr="boom"),
        FakeRun(_failing(lambda r: None), returncode=2),
        FakeRun("", raises=subprocess.TimeoutExpired("claude", 1)),
        FakeRun("", raises=FileNotFoundError("claude")),
        FakeRun("not json\n"),
        FakeRun(_stdout(REAL["opus"]["cli"]["events"][:-1])),  # no result event
    ],
    ids=["is_error-usage-limit", "is_error-subtype", "nonzero-no-stdout", "nonzero-with-result",
         "timeout", "missing-binary", "garbage-stdout", "no-result-event"],
)
def test_claude_cli_failures_are_transport_and_are_never_retried(fake, monkeypatch):
    monkeypatch.setattr(g.subprocess, "run", fake)
    slept: list[float] = []
    layout = generate(KITCHEN, OPUS, sleep=slept.append)
    assert layout.failure_kind == TRANSPORT and layout.parse_ok is False
    assert layout.raw is None and layout.cli is None and layout.error.startswith("call:")
    assert len(fake.calls) <= 1 and slept == [], "a usage limit stays one; --resume is the retry"


def test_claude_cli_usage_limit_text_reaches_the_error(monkeypatch):
    monkeypatch.setattr(g.subprocess, "run", FakeRun(_failing(
        lambda r: r.update(is_error=True, result="You've hit your usage limit"))))
    assert "usage limit" in generate(KITCHEN, OPUS).error


# ------------------------------------------------------------------ the sweep row


def _sweep(tmp_path, monkeypatch, *argv, fake=None):
    monkeypatch.delenv(CLAUDE_CMD_ENV, raising=False)
    if fake is not None:
        monkeypatch.setattr(g.subprocess, "run", fake)
    run.main(["sweep", "--out", str(tmp_path), "--envelopes", "t0_kitchen_12x14", *argv])
    rows = lambda name: [json.loads(ln) for ln in (tmp_path / name).read_text().splitlines()] \
        if (tmp_path / name).exists() else []
    return rows("layouts.jsonl"), rows("transport_failures.jsonl")


def test_claude_cli_sweep_row_carries_cli_and_provider_default_sampling(tmp_path, monkeypatch):
    fake = FakeRun(_stdout(REAL["opus"]["cli"]["events"]))
    layouts, failures = _sweep(tmp_path, monkeypatch, "--models", "opus", fake=fake)
    (row,) = layouts
    assert failures == []
    real = REAL["opus"]
    assert row["model"] == "opus" and row["sample"] == 0 and row["include_inventory"] is True
    assert row["raw"] == real["raw"] and row["cli"] == real["cli"]
    assert row["call_config"] == real["call_config"]
    assert row["parse_ok"] and row["failure_kind"] is None


def test_claude_cli_sweep_noinv_arm_label_and_failure_file(tmp_path, monkeypatch):
    fake = FakeRun(_failing(lambda r: r.update(is_error=True, result="limit")))
    layouts, failures = _sweep(tmp_path, monkeypatch, "--models", "sonnet", "--no-inventory", fake=fake)
    assert layouts == []
    (row,) = failures
    assert row["model"] == "sonnet-noinv" and row["parse_ok"] is False and row["raw"] is None
    assert row["failure_kind"] == "transport" and row["call_config"]["backend"] == "claude_cli"
    assert "cli" not in row


def test_sweep_rows_of_other_backends_keep_their_shape(tmp_path, monkeypatch):
    def fake(env, spec, include_inventory=True, **_):
        return Layout(envelope_id=env.id, model=spec.name, raw="[]")
    monkeypatch.setattr(run, "generate", fake)
    layouts, _ = _sweep(tmp_path, monkeypatch, "--models", "local")
    assert "cli" not in layouts[0]


# ------------------------------------------------------------------ v8 accepts the row

VALIDITY = os.environ.get("ENVELOPE_SHIFT_VALIDITY_PY")


@pytest.mark.skipif(not VALIDITY, reason=(
    "ENVELOPE_SHIFT_VALIDITY_PY is not set: the v8 validity oracle this checks against is a "
    "separate script that is not distributed with this repo"))
def test_claude_cli_row_is_accepted_by_v8(tmp_path, monkeypatch):
    """The row this transport writes is the row the frozen oracle re-derives the condition
    from: the only complaints left are coverage of the full grid."""
    fake = FakeRun(_stdout(REAL["opus"]["cli"]["events"]))
    _sweep(tmp_path / "claude", monkeypatch, "--models", "opus", fake=fake)
    fake.stdout = _stdout(REAL["sonnet"]["cli"]["events"])
    _sweep(tmp_path / "claude", monkeypatch, "--models", "sonnet", fake=fake)
    out = REAL_RUN([sys.executable, VALIDITY, "v8", str(tmp_path)], capture_output=True, text=True)
    text = out.stdout + out.stderr
    assert "rows re-derived" not in text  # coverage is short, so v8 is RED as it must be
    assert "no successful row" not in text, text
    complaints = [ln for ln in text.splitlines() if "covers" in ln]
    assert complaints and all("grid" in ln for ln in complaints), text
    assert not [ln for ln in text.splitlines() if ln.strip().startswith("-") and "covers" not in ln
                and "must be re-derivable" not in ln], text


# ------------------------------------------------------------------ provider-default sampling


class _OpenAI:
    sent: dict = {}

    def __init__(self, **_):
        self.chat = type("C", (), {"completions": self})()

    def create(self, **kwargs):
        type(self).sent = kwargs
        msg = type("M", (), {"content": "[]"})()
        return type("R", (), {"choices": [type("Ch", (), {"message": msg})()]})()


def _openai_spec(**kw):
    return ModelSpec("m", "openai", "m-1", base_url="http://h/v1", **kw)


def test_sampling_default_sends_no_temperature_and_records_none(monkeypatch):
    import openai

    monkeypatch.setattr(openai, "OpenAI", _OpenAI)
    spec = _openai_spec(temperature=None)
    g._call_openai(spec, "s", "u")
    assert "temperature" not in _OpenAI.sent
    assert spec.call_config()["sampling"] == {}
    g._call_openai(_openai_spec(temperature=0.2), "s", "u")
    assert _OpenAI.sent["temperature"] == 0.2, "--temperature keeps reproducing the old rows"
    assert _openai_spec(temperature=0.2).call_config()["sampling"] == {"temperature": 0.2}


def test_sweep_sampling_default_flag_reaches_every_backend(tmp_path, monkeypatch):
    seen: list[ModelSpec] = []

    def fake(env, spec, include_inventory=True, **_):
        seen.append(spec)
        return Layout(envelope_id=env.id, model=spec.name, raw="[]")

    monkeypatch.setattr(run, "generate", fake)
    layouts, _ = _sweep(tmp_path, monkeypatch, "--models", "local", "glm", "--sampling", "default")
    assert [s.temperature for s in seen] == [None, None]
    assert [r["call_config"]["sampling"] for r in layouts] == [{}, {}]
    assert all(r["temperature"] is None for r in layouts)


def test_sweep_temperature_flag_still_works_and_excludes_sampling_default(tmp_path, monkeypatch):
    seen: list[ModelSpec] = []

    def fake(env, spec, include_inventory=True, **_):
        seen.append(spec)
        return Layout(envelope_id=env.id, model=spec.name, raw="[]")

    monkeypatch.setattr(run, "generate", fake)
    layouts, _ = _sweep(tmp_path, monkeypatch, "--models", "local", "--temperature", "0.8")
    assert seen[0].temperature == 0.8
    assert layouts[0]["call_config"]["sampling"] == {"temperature": 0.8}
    with pytest.raises(SystemExit):
        _sweep(tmp_path / "x", monkeypatch, "--models", "local", "--temperature", "0.8", "--sampling", "default")


def test_models_toml_sampling_default_means_no_temperature(tmp_path):
    p = tmp_path / "models.toml"
    p.write_text('[a]\nbackend = "openai"\nmodel = "m"\nsampling = "default"\n')
    assert load_models(p)["a"].temperature is None
    p.write_text('[a]\nbackend = "openai"\nmodel = "m"\nsampling = "default"\ntemperature = 0.2\n')
    with pytest.raises(ValueError):
        load_models(p)


# ------------------------------------------------------------------ --resume


def _row(env_id, model, sample, *, transport=False, inv=True):
    return {"envelope_id": env_id, "model": model, "sample": sample, "include_inventory": inv,
            "parse_ok": not transport, "failure_kind": "transport" if transport else None,
            "raw": None if transport else "[]", "error": "call: usage limit" if transport else None}


def _resume(tmp_path, monkeypatch, *argv):
    calls: list[tuple[str, str]] = []

    def fake(env, spec, include_inventory=True, **_):
        calls.append((spec.name, env.id))
        return Layout(envelope_id=env.id, model=spec.name, raw="[]")

    monkeypatch.setattr(run, "generate", fake)
    layouts, failures = _sweep(tmp_path, monkeypatch, "--samples", "3", *argv)
    return calls, layouts, failures


def _write(path, rows, tail=""):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows) + tail)


def test_resume_skips_done_keys_and_retries_transport_only_keys(tmp_path, monkeypatch):
    kid = "t0_kitchen_12x14"
    _write(tmp_path / "layouts.jsonl", [_row(kid, "opus", 0), _row(kid, "opus", 1)])
    _write(tmp_path / "transport_failures.jsonl",
           [_row(kid, "opus", 2, transport=True),      # retried: only a failure so far
            _row(kid, "opus", 1, transport=True),      # stale: sample 1 succeeded since
            _row(kid, "sonnet", 0, transport=True)])   # outside this sweep: untouched
    calls, layouts, failures = _resume(tmp_path, monkeypatch, "--models", "opus", "--resume")
    assert calls == [("opus", kid)], "only sample 2 is asked for"
    assert [(r["model"], r["sample"]) for r in layouts] == [("opus", 0), ("opus", 1), ("opus", 2)]
    assert [(r["model"], r["sample"]) for r in failures] == [("sonnet", 0)]


def test_resume_a_second_time_asks_for_nothing_and_duplicates_nothing(tmp_path, monkeypatch):
    calls, layouts, _ = _resume(tmp_path, monkeypatch, "--models", "opus", "--resume")
    assert len(calls) == 3
    calls, again, _ = _resume(tmp_path, monkeypatch, "--models", "opus", "--resume")
    assert calls == [] and again == layouts


def test_resume_keys_include_the_arm(tmp_path, monkeypatch):
    kid = "t0_kitchen_12x14"
    _write(tmp_path / "layouts.jsonl", [_row(kid, "opus", k) for k in range(3)])
    calls, layouts, _ = _resume(tmp_path, monkeypatch, "--models", "opus", "--no-inventory", "--resume")
    assert len(calls) == 3, "opus-noinv is a different arm from opus"
    calls, _, _ = _resume(tmp_path, monkeypatch, "--models", "opus", "sonnet", "--resume")
    assert sorted(set(calls)) == [("sonnet", kid)] and len(calls) == 3, "opus is done, sonnet is not"


def test_resume_repairs_a_half_written_last_row(tmp_path, monkeypatch):
    """A sweep killed mid-write must not leave a row the next append fuses onto."""
    kid = "t0_kitchen_12x14"
    _write(tmp_path / "layouts.jsonl", [_row(kid, "opus", 0)], tail='{"envelope_id": "t0_kit')
    calls, layouts, _ = _resume(tmp_path, monkeypatch, "--models", "opus", "--resume")
    assert len(calls) == 2
    assert [r["sample"] for r in layouts] == [0, 1, 2], "every line still parses"


def test_without_resume_a_sweep_still_appends_everything(tmp_path, monkeypatch):
    kid = "t0_kitchen_12x14"
    _write(tmp_path / "layouts.jsonl", [_row(kid, "opus", 0)])
    calls, layouts, _ = _resume(tmp_path, monkeypatch, "--models", "opus")
    assert len(calls) == 3 and len(layouts) == 4, "the old behaviour: no flag, no dedupe"

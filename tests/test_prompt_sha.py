"""Every row records the prompt it was actually sent (claim v9).

v1 proves `envelope_prompt()` is right TODAY; it cannot say what an old row was sent (the
DeepSeek/GLM/local E1 rows predate the atypicality brief). So each transport hashes the
system and user strings out of the request it BUILT and the row stores that
`prompt_sha256`. These tests read the sha back against what a fake client captured off the
wire, never against a second call to `envelope_prompt`, which is exactly the check that could
not tell a transport that altered the prompt.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from envelope_shift import generate as g
from envelope_shift import run
from envelope_shift.envelopes import load_all
from envelope_shift.failure import TRANSPORT
from envelope_shift.generate import ModelSpec, Response, generate, prompt_sha256

ENV = {e.id: e for e in load_all()}["t0_kitchen_12x14"]
FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "claude_cli_rows.json").read_text())
OPUS_EVENTS = next(r for r in FIXTURE if r["model"] == "opus")["cli"]["events"]
OPENAI = ModelSpec("m", "openai", "m-1", base_url="http://h/v1")
ANTHROPIC = ModelSpec("a", "anthropic", "claude-x", thinking="adaptive", effort="medium")
CLI_SPEC = g.load_models()["opus"]


def _sha(system: str, user: str) -> str:
    """The oracle's definition, spelled out: not `prompt_sha256` under test."""
    return hashlib.sha256(json.dumps([system, user], ensure_ascii=False).encode("utf-8")).hexdigest()


class _Client:
    """A fake OpenAI-compatible endpoint: captures every POSTed request, replies `reply` or
    raises `error`."""

    sent: list[dict] = []
    reply: str = "[]"
    error: Exception | None = None

    def __init__(self, **_):
        self.chat = type("C", (), {"completions": self})()

    def create(self, **kwargs):
        type(self).sent.append(kwargs)
        if type(self).error is not None:
            raise type(self).error
        msg = type("M", (), {"content": type(self).reply})()
        return type("R", (), {"choices": [type("Ch", (), {"message": msg})()]})()


@pytest.fixture
def openai_wire(monkeypatch):
    import openai

    _Client.sent, _Client.reply, _Client.error = [], "[]", None
    monkeypatch.setattr(openai, "OpenAI", _Client)
    return _Client


def _posted(client) -> tuple[str, str]:
    (request,) = client.sent
    system, user = request["messages"]
    assert (system["role"], user["role"]) == ("system", "user")
    return system["content"], user["content"]


# ---------------------------------------------------------------- the definition


def test_prompt_sha256_definition_is_the_oracles_byte_for_byte():
    assert prompt_sha256("s", "u") == _sha("s", "u")
    # ensure_ascii=False: a non-ASCII prompt (feet-inch marks, dashes) hashes as UTF-8, not \u escapes.
    assert prompt_sha256("sys", "12′ × 14′ — kitchen") == _sha("sys", "12′ × 14′ — kitchen")
    assert prompt_sha256("a", "b") != prompt_sha256("b", "a")


# ---------------------------------------------------------------- openai-compatible


@pytest.mark.parametrize("inventory", [True, False])
def test_prompt_sha_openai_row_is_the_sha_of_the_posted_messages(openai_wire, inventory):
    layout = generate(ENV, OPENAI, include_inventory=inventory)
    system, user = _posted(openai_wire)
    assert layout.prompt_sha256 == _sha(system, user)
    assert ("Expected contents" in user) is inventory, "the two arms send different prompts"


def test_prompt_sha_differs_between_the_inventory_arms(openai_wire):
    with_inv = generate(ENV, OPENAI, include_inventory=True).prompt_sha256
    without = generate(ENV, OPENAI, include_inventory=False).prompt_sha256
    assert with_inv and without and with_inv != without


def test_prompt_sha_follows_what_the_transport_sent_not_what_envelope_prompt_returns(
        openai_wire, monkeypatch):
    real_request = g._openai_request
    monkeypatch.setattr(g, "_openai_request", lambda spec, system, user: real_request(
        spec, system, user + "\n(altered in flight)"))
    layout = generate(ENV, OPENAI)
    system, user = _posted(openai_wire)
    assert user.endswith("(altered in flight)")
    assert layout.prompt_sha256 == _sha(system, user)
    assert layout.prompt_sha256 != _sha(g.SYSTEM, g.envelope_prompt(ENV, True))


def test_prompt_sha_a_transport_double_reports_the_sha_of_its_own_request():
    def transport(spec, system, user):
        return Response("[]", prompt_sha256=_sha(system, user + " altered"))

    layout = generate(ENV, OPENAI, transport=transport)
    assert layout.prompt_sha256 == _sha(g.SYSTEM, g.envelope_prompt(ENV, True) + " altered")


def test_prompt_sha_a_plain_reply_double_falls_back_to_the_strings_it_was_handed():
    layout = generate(ENV, OPENAI, transport=lambda spec, system, user: "[]")
    assert layout.prompt_sha256 == _sha(g.SYSTEM, g.envelope_prompt(ENV, True))


def test_prompt_sha_is_recorded_on_a_parse_failure(openai_wire):
    openai_wire.reply = "I cannot lay this room out."
    layout = generate(ENV, OPENAI)
    assert not layout.parse_ok and layout.failure_kind != TRANSPORT
    assert layout.prompt_sha256 == _sha(*_posted(openai_wire))


def test_prompt_sha_is_recorded_on_a_transport_failure(openai_wire):
    openai_wire.error = g.TransportError("bad request", status=400)  # not retried
    layout = generate(ENV, OPENAI)
    assert layout.failure_kind == TRANSPORT
    assert layout.prompt_sha256 == _sha(*_posted(openai_wire))


def test_prompt_sha_a_retried_call_records_the_prompt_of_the_final_attempt(openai_wire):
    openai_wire.error = g.TransportError("down", status=503)
    layout = generate(ENV, OPENAI, sleep=lambda _s: None)
    assert len(openai_wire.sent) == g.MAX_ATTEMPTS and layout.failure_kind == TRANSPORT
    system, user = openai_wire.sent[-1]["messages"][0]["content"], openai_wire.sent[-1]["messages"][1]["content"]
    assert layout.prompt_sha256 == _sha(system, user)


def test_prompt_sha_no_backend_means_nothing_was_sent_so_no_sha():
    layout = generate(ENV, ModelSpec("x", "nope", "x"))
    assert layout.failure_kind == TRANSPORT and layout.prompt_sha256 is None


# ---------------------------------------------------------------- anthropic


def test_prompt_sha_anthropic_row_is_the_sha_of_the_system_and_message(monkeypatch):
    import anthropic

    sent: list[dict] = []

    class _Anthropic:
        def __init__(self, **_):
            self.messages = self

        def create(self, **kwargs):
            sent.append(kwargs)
            return type("R", (), {"content": [type("B", (), {"type": "text", "text": "[]"})()]})()

    monkeypatch.setattr(anthropic, "Anthropic", _Anthropic)
    layout = generate(ENV, ANTHROPIC, include_inventory=False)
    (request,) = sent
    assert layout.prompt_sha256 == _sha(request["system"], request["messages"][0]["content"])
    assert request["messages"][0]["content"] == g.envelope_prompt(ENV, False)


# ---------------------------------------------------------------- claude_cli


def _cli_run(monkeypatch, stdout: str = "", returncode: int = 0):
    calls: list[list[str]] = []

    def fake(cmd, **_):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode, stdout, "")

    monkeypatch.delenv(g.CLAUDE_CMD_ENV, raising=False)
    monkeypatch.setattr(g.subprocess, "run", fake)
    return calls


@pytest.mark.parametrize("inventory", [True, False])
def test_prompt_sha_claude_cli_row_is_the_sha_of_its_argv_prompt(monkeypatch, inventory):
    calls = _cli_run(monkeypatch, "".join(json.dumps(e) + "\n" for e in OPUS_EVENTS))
    layout = generate(ENV, CLI_SPEC, include_inventory=inventory)
    (cmd,) = calls
    argv = layout.cli["argv"]
    assert cmd[1:] == argv, "the stored argv is the one that ran"
    system, user = argv[argv.index("--system-prompt") + 1], argv[argv.index("-p") + 1]
    assert layout.prompt_sha256 == _sha(system, user)


def test_prompt_sha_claude_cli_failure_row_carries_it_too(monkeypatch):
    calls = _cli_run(monkeypatch, "", returncode=1)
    layout = generate(ENV, CLI_SPEC)
    (cmd,) = calls
    assert layout.failure_kind == TRANSPORT
    assert layout.prompt_sha256 == _sha(cmd[cmd.index("--system-prompt") + 1], cmd[cmd.index("-p") + 1])


# ---------------------------------------------------------------- the sweep row


def test_prompt_sha_sweep_writes_it_on_response_rows_and_on_transport_failure_rows(
        tmp_path, openai_wire):
    def sweep(out, *argv):
        run.main(["sweep", "--out", str(out), "--envelopes", "t0_kitchen_12x14", "--models", "local", *argv])
        read = lambda n: [json.loads(ln) for ln in (out / n).read_text().splitlines()] if (out / n).exists() else []
        return read("layouts.jsonl"), read("transport_failures.jsonl")

    for arm, inventory in (("", True), ("--no-inventory", False)):
        openai_wire.sent.clear()
        layouts, _ = sweep(tmp_path / f"ok{inventory}", *([arm] if arm else []))
        (row,) = layouts
        assert row["include_inventory"] is inventory
        assert row["prompt_sha256"] == _sha(*_posted(openai_wire))

    openai_wire.sent.clear()
    openai_wire.error = g.TransportError("nope", status=400)
    layouts, failures = sweep(tmp_path / "down")
    (row,) = failures
    assert layouts == [] and row["failure_kind"] == TRANSPORT
    assert row["prompt_sha256"] == _sha(*_posted(openai_wire))

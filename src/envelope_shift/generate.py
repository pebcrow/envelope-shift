"""Prompt a model with an envelope, parse a layout back.

One interface, three backends: anything OpenAI-compatible (which includes the
local server at localhost:8000), the Anthropic API, and the Claude Code
CLI on a subscription (`claude_cli`, which is how the sweeps reach Claude: see
_call_claude_cli). Models are chosen by config, not code: named specs live in
models.toml at the repo root (`load_models`), and a sweep resolves bare names
against it first.

Transport failures that are plausibly transient (429, 5xx, connection
errors) are retried a bounded number of times with jittered exponential
backoff; when retries are exhausted the failure is recorded in Layout.error.
Parse failures are NOT retried: the failure rate per tier is itself a result.

The published comparison ran frontier models against the same task. Their
encoder is given "geometry, topology and required entities", so by default
the prompt includes the expected inventory too. Set `include_inventory=False`
to test what models do when told only the room type.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import shlex
import subprocess
import time
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from .failure import PARSE, TRANSPORT
from .inventory import Group, Item, inventory_for
from .schema import Entity, Envelope, Layout

SYSTEM = """You are a residential architectural layout engine. You place furniture,
fixtures and casework inside a room whose walls, doors and windows are given.
Output ONLY a JSON array of entities; no prose, no markdown fences.

Units are feet. Walls are indexed in order; wall i runs from vertices[i] to
vertices[i+1] (wrapping). Each entity is placed relative to one supporting wall:

  type      snake_case entity type
  wall      index of the supporting wall (the entity's back faces this wall)
  t         position of the entity's back-edge midpoint along the wall, 0..1
  offset    distance from the wall face to the entity's back edge, feet (0 = against the wall)
  width     extent along the wall, feet
  depth     extent into the room, feet
  height    feet
  rotation  degrees counter-clockwise about the back-edge midpoint (usually 0)
  elevation height of the entity's bottom above the floor, feet (0 for floor-standing;
            upper cabinets and wall shelves are elevated)

Entities must not overlap each other, must stay inside the room, must not
block doors, and every door must have a walkable path to the important
destinations in the room. Respect the ceiling: an entity cannot be taller
than the headroom where it stands."""


def envelope_prompt(env: Envelope, include_inventory: bool = True) -> str:
    body = {
        "room_type": env.room_type.value,
        "vertices": env.vertices,
        "walls": [
            {"index": i, "from": env.vertices[i], "to": env.vertices[(i + 1) % env.n_walls]}
            for i in range(env.n_walls)
        ],
        "openings": [o.model_dump() for o in env.openings],
        "ceiling": env.ceiling.model_dump(),
    }
    text = "Room:\n" + json.dumps(body, indent=1)
    # The brief is the experiment's independent variable: geometry reaches the model through
    # the vertices, program (T5) only through this line. `declared_extraneous` is the
    # scorer's answer key and must never be serialised into the prompt.
    text += "\n\nAbout this room: " + env.atypicality.brief
    if include_inventory:
        inv = inventory_for(env.room_type)
        lines = []
        for line in inv.lines:
            if isinstance(line, Item):
                lines.append(f"- {line.type} x{line.count}")
            else:
                lines.append(f"- one of: {', '.join(line.alternatives)}")
        text += "\n\nExpected contents for this room type:\n" + "\n".join(lines)
    text += "\n\nReturn the JSON array now."
    return text


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
# Reasoning models (Qwen3, DeepSeek) emit their scratchpad inline; drop it.
# An unterminated block means the model ran out of tokens while thinking.
_THINK = re.compile(r"<think>.*?(</think>|\Z)", re.DOTALL)


def parse_entities(raw: str) -> list[Entity]:
    cleaned = _FENCE.sub("", _THINK.sub("", raw).strip())
    # Tolerate leading prose by finding the first '['.
    start = cleaned.find("[")
    if start < 0:
        raise ValueError("no JSON array in response")
    data = json.loads(cleaned[start : cleaned.rfind("]") + 1])
    if not isinstance(data, list):
        raise ValueError("top-level JSON is not an array")
    return [Entity.model_validate(item) for item in data]


# --------------------------------------------------------------------------- specs


@dataclass(frozen=True)
class ModelSpec:
    name: str  # label used in results
    backend: str  # "openai" | "anthropic" | "claude_cli"
    model: str  # provider model id
    base_url: str | None = None
    api_key_env: str = "OPENAI_API_KEY"
    # None = the provider's default sampling: no temperature is sent and the row records
    # sampling {} (`sweep --sampling default`, or `sampling = "default"` in models.toml).
    temperature: float | None = 0.2
    max_tokens: int = 4000
    # Provider-specific request fields sent verbatim (OpenAI-compatible backends
    # only), e.g. DeepSeek's {"thinking": {"type": "disabled"}}. Stored as a
    # tuple of (key, value) pairs so the frozen dataclass stays hashable.
    extra_body: tuple[tuple[str, object], ...] = ()
    # Reasoning configuration for the ANTHROPIC backends, which ignore extra_body.
    # `thinking` is the thinking block's type ("adaptive"); `effort` is
    # output_config.effort ("low".."max") on the API and --effort on the CLI. Both omitted
    # from the request when None, so the OpenAI-compatible arms are untouched. The CLI has
    # no thinking switch: it runs adaptive thinking itself, so claude_cli declares effort only.
    #
    # These exist because the report's existing honesty defect is exactly here: DeepSeek
    # ran with thinking disabled and GLM at reasoning_effort=low while the report called
    # them frontier. Re-running on Claude without declaring its setting would repeat that
    # in the opposite direction, so the setting is named rather than inherited from the
    # provider default.
    thinking: str | None = None
    effort: str | None = None

    def extra_body_dict(self) -> dict:
        return dict(self.extra_body)

    def reasoning(self) -> dict:
        """The reasoning configuration this spec actually sends. {} means none sent.

        Empty is a real answer, not a missing one — see call_config().
        """
        if self.backend == "claude_cli":
            return {"effort": self.effort} if self.effort else {}
        if self.backend == "anthropic":
            out = {}
            if self.thinking:
                out["thinking"] = self.thinking
            if self.effort:
                out["effort"] = self.effort
            return out
        # The OpenAI-compatible arms carry theirs in extra_body: DeepSeek's
        # {"thinking": {"type": "disabled"}} and z.ai's reasoning_effort.
        body = self.extra_body_dict()
        return {k: v for k, v in body.items() if k in ("thinking", "reasoning_effort")}

    def call_config(self, source: str = "recorded") -> dict:
        """What the call actually sent, as the raw row records it (claim v6).

        The condition a measurement was taken under has to be readable from the row.
        models.toml describes what a sweep would send TODAY; it says nothing about what
        an existing row did send, and this artifact has already published one set of
        model claims that the corpus could not corroborate.

        `sampling` is empty on the anthropic backend ON PURPOSE. Current Claude models
        reject temperature with a 400, so _call_anthropic does not send it — and the
        sweep used to stamp `temperature: 0.2` onto those rows anyway, from the spec,
        which is precisely the kind of unearned parameter this claim exists to stop. The CLI
        has no sampling flag at all, so it is empty there for the same reason; and a spec at
        provider-default sampling (temperature None) sends none on any backend.
        """
        sends_temperature = self.backend not in ("anthropic", "claude_cli") and self.temperature is not None
        return {
            "backend": self.backend,
            "model": self.model,
            "reasoning": self.reasoning(),
            "sampling": {"temperature": self.temperature} if sends_temperature else {},
            "source": source,
        }


LOCAL = ModelSpec(
    "local", "openai", "qwen3-30b-a3b",
    base_url="http://localhost:8000/v1", api_key_env="LOCAL_KEY",
    max_tokens=16000,  # reasoning models spend most of this thinking
)

MODELS_ENV = "ENVELOPE_SHIFT_MODELS"


def models_path() -> Path:
    """models.toml: $ENVELOPE_SHIFT_MODELS, else ./models.toml, else the repo root's."""
    if p := os.environ.get(MODELS_ENV):
        return Path(p)
    cwd = Path.cwd() / "models.toml"
    if cwd.exists():
        return cwd
    return Path(__file__).resolve().parents[2] / "models.toml"


def load_models(path: str | os.PathLike[str] | None = None) -> dict[str, ModelSpec]:
    """Named specs from models.toml; each top-level table is one ModelSpec.

    A missing file yields an empty mapping so the backend:model grammar still works.
    """
    p = Path(path) if path is not None else models_path()
    if not p.exists():
        return {}
    data = tomllib.loads(p.read_text())
    specs: dict[str, ModelSpec] = {}
    for name, fields in data.items():
        if not isinstance(fields, dict):
            raise ValueError(f"{p}: [{name}] must be a table")
        if isinstance(fields.get("extra_body"), dict):
            fields = {**fields, "extra_body": tuple(fields["extra_body"].items())}
        if "sampling" in fields:
            if fields["sampling"] != "default" or "temperature" in fields:
                raise ValueError(f'{p}: [{name}]: sampling is only "default", and excludes temperature')
            fields = {**{k: v for k, v in fields.items() if k != "sampling"}, "temperature": None}
        try:
            specs[name] = ModelSpec(name=name, **fields)
        except TypeError as exc:
            raise ValueError(f"{p}: [{name}]: {exc}") from None
    return specs


# --------------------------------------------------------------------------- keys

# Optional key file of NAME=value lines (sections and comments ignored), named by this env
# var. Unset means keys come from the process environment only.
KEYFILE_ENV = "ENVELOPE_SHIFT_KEYFILE"
# Spec-level env names that differ from the variable name in the key file.
_ENVARS_ALIASES = {"LOCAL_KEY": "LLM_LOCAL_KEY"}


def _envars_value(name: str) -> str | None:
    """Value of NAME=... from the key file, whichever section it sits in."""
    keyfile = os.environ.get(KEYFILE_ENV)
    if not keyfile:
        return None
    path = os.path.expanduser(keyfile)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            if key.strip() == name:
                return value.strip().strip('"').strip("'")
    return None


def _api_key(spec: ModelSpec) -> str | None:
    """Process env first, then the key file by the same name (or its alias). Never logged."""
    key = os.environ.get(spec.api_key_env)
    if not key:
        key = _envars_value(spec.api_key_env)
    if not key and spec.api_key_env in _ENVARS_ALIASES:
        key = _envars_value(_ENVARS_ALIASES[spec.api_key_env])
    return key or None


# --------------------------------------------------------------------------- transports

@dataclass(frozen=True)
class Response:
    """A transport's answer when the response itself is evidence: the text the layout is
    parsed from, plus what the provider emitted around it, stored verbatim on the row."""

    text: str
    cli: dict | None = None
    # sha256 of the system and user strings the transport put in its request (claim v9).
    prompt_sha256: str | None = None
    # What the OpenAI-compatible provider says answered: {"model", "system_fingerprint"}, each
    # taken from the response object or None when it carried none. None on the whole means no
    # response was read (the other transports), and the row then has no observed block.
    observed: dict | None = None


def prompt_sha256(system: str, user: str) -> str:
    """The one prompt fingerprint: sha256 of the UTF-8 JSON array [system, user]. Claim v9's
    oracle defines it byte for byte; it is taken from the request a transport BUILT, never by
    calling `envelope_prompt` again, so it says what was sent rather than what should have been."""
    return hashlib.sha256(json.dumps([system, user], ensure_ascii=False).encode("utf-8")).hexdigest()


def _stamp(exc: BaseException, sha: str) -> BaseException:
    """Carry the sha of a request that failed on the exception, so a transport failure row
    still records what it asked. Set on SDK exceptions too; they accept attributes."""
    try:
        exc.prompt_sha256 = sha  # type: ignore[attr-defined]
    except AttributeError:  # pragma: no cover - an exception type with __slots__
        pass
    return exc


# A transport returns the reply text, or a Response when the raw response is to be stored.
Transport = Callable[[ModelSpec, str, str], "str | Response"]


class TransportError(Exception):
    """A provider failure with an optional HTTP status; status None means the
    connection itself failed. Transports and test doubles raise this; SDK
    exceptions are classified by duck-typing in `is_retryable`."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class CliError(TransportError):
    """The CLI call failed: non-zero exit, is_error, a timeout, or no result event. Never
    retried here — each attempt spends subscription quota, and a usage-limit error stays
    one until the window resets. `sweep --resume` is the retry, and it is a decision."""


def _openai_request(spec: ModelSpec, system: str, user: str) -> dict:
    """The exact keyword arguments of the chat completion; the prompt hash is read back from
    its `messages`, so it is the payload's, not the caller's."""
    # Provider-default sampling sends no temperature at all.
    sampling = {} if spec.temperature is None else {"temperature": spec.temperature}
    return dict(
        model=spec.model,
        max_tokens=spec.max_tokens,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        extra_body=spec.extra_body_dict() or None,
        **sampling,
    )


def _call_openai(spec: ModelSpec, system: str, user: str) -> Response:
    from openai import OpenAI

    request = _openai_request(spec, system, user)
    sha = prompt_sha256(*(m["content"] for m in request["messages"]))
    try:
        # max_retries=0: retry policy lives in call_with_retry, not the SDK.
        client = OpenAI(base_url=spec.base_url, api_key=_api_key(spec) or "none", max_retries=0)
        r = client.chat.completions.create(**request)
    except Exception as exc:
        _stamp(exc, sha)
        raise
    return Response(r.choices[0].message.content or "", prompt_sha256=sha, observed=_observed(r))


def _observed(response: object) -> dict:
    """The response's own `model` and `system_fingerprint`. The request's model id is what we
    asked for; a provider that no longer lists an id can still answer it with a different
    backing model, and only the response says which. A field the response lacks (or does not
    give as a string; `system_fingerprint` is optional in the openai client's ChatCompletion)
    is None: nothing is invented."""
    def field(name: str) -> str | None:
        value = getattr(response, name, None)
        return value if isinstance(value, str) else None

    return {"model": field("model"), "system_fingerprint": field("system_fingerprint")}


def _anthropic_request(spec: ModelSpec, system: str, user: str) -> dict:
    """The exact keyword arguments of the messages call; see `_openai_request`."""
    # Reasoning configuration is DECLARED, never inherited. Opus 5 runs adaptive thinking
    # by default at effort `high`; sending the same values explicitly is what makes the
    # experimental condition a stated choice the report can be held to.
    extra: dict = {}
    if spec.thinking:
        extra["thinking"] = {"type": spec.thinking}
    if spec.effort:
        extra["output_config"] = {"effort": spec.effort}
    return dict(
        model=spec.model,
        max_tokens=spec.max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        **extra,
    )


def _call_anthropic(spec: ModelSpec, system: str, user: str) -> Response:
    import anthropic

    request = _anthropic_request(spec, system, user)
    sha = prompt_sha256(request["system"], request["messages"][0]["content"])
    try:
        # Current Claude models (Sonnet 5 / Opus 5) reject sampling parameters
        # with a 400, so `temperature` is not sent on this backend. api_key=None
        # lets the SDK fall back to its own credential resolution.
        client = anthropic.Anthropic(api_key=_api_key(spec), max_retries=0)
        r = client.messages.create(**request)
    except Exception as exc:
        _stamp(exc, sha)
        raise
    return Response("".join(b.text for b in r.content if getattr(b, "type", "") == "text"), prompt_sha256=sha)


# --- claude_cli: Claude through the Claude Code subscription.
#
# The author's decisions of 2026-09-21: Claude is reached through the subscription, never a
# token-billed API key; it runs adaptive thinking at effort MEDIUM, stated for every arm.
# The transport returns the CLI's own stream-json events with the text, and the sweep stores
# them on the row, so validity claim v8 re-derives the condition from what the CLI emitted
# (apiKeySource, the tool/MCP/skill lists, the model, the argv, the token counts) rather than
# trusting what this code says it asked for.
#
# The launcher prefix is host configuration and lives in the environment, never in a tracked
# file: no tracked file carries a host path. The host wants an isolated environment, because
# outside one the local harness leaks in (~16.5K input tokens against ~413 inside), which v8
# rejects. The default, plain `claude`, is not one.
CLAUDE_CMD_ENV = "ENVELOPE_SHIFT_CLAUDE_CMD"
CLI_TIMEOUT_SECONDS = 900
# Keys of the init event that are host paths; everything else in the events is stored verbatim.
_HOST_INIT_KEYS = ("cwd", "messaging_socket_path")


def claude_cli_argv(spec: ModelSpec, system: str, user: str) -> list[str]:
    """The CLI arguments after the launcher prefix. Exactly one invocation is permitted (v8
    compares it element for element): no extra flag, no repeated flag."""
    return ["-p", user, "--model", spec.model, "--effort", spec.effort or "",
            "--tools", "", "--system-prompt", system, "--strict-mcp-config",
            "--disable-slash-commands", "--no-session-persistence",
            "--output-format", "stream-json", "--verbose"]


def _argv_prompt_sha256(argv: list[str]) -> str:
    """The prompt hash of a claude_cli invocation, read from the argv it will run: the values
    after `--system-prompt` and `-p`."""
    return prompt_sha256(argv[argv.index("--system-prompt") + 1], argv[argv.index("-p") + 1])


def _scrub(event: dict) -> dict:
    if event.get("type") == "system" and event.get("subtype") == "init":
        return {k: v for k, v in event.items() if k not in _HOST_INIT_KEYS}
    return event


def _call_claude_cli(spec: ModelSpec, system: str, user: str) -> Response:
    if not spec.effort:
        raise CliError("claude_cli needs a declared effort: it is what makes the condition a stated choice")
    argv = claude_cli_argv(spec, system, user)
    sha = _argv_prompt_sha256(argv)
    try:
        return _run_claude_cli(argv, sha)
    except CliError as exc:
        _stamp(exc, sha)
        raise


def _run_claude_cli(argv: list[str], sha: str) -> Response:
    prefix = shlex.split(os.environ.get(CLAUDE_CMD_ENV) or "claude")
    try:
        # stdin is /dev/null: a CLI that waits on a terminal would hang the sweep.
        proc = subprocess.run(
            [*prefix, *argv], stdin=subprocess.DEVNULL, capture_output=True, text=True,
            encoding="utf-8", timeout=CLI_TIMEOUT_SECONDS, check=False,
        )
    except subprocess.TimeoutExpired:
        raise CliError(f"claude cli timed out after {CLI_TIMEOUT_SECONDS}s") from None
    except OSError as exc:
        raise CliError(f"cannot run claude cli {prefix[0]!r}: {exc}") from None
    events = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            raise CliError(f"claude cli exit {proc.returncode}: non-JSON line on stdout") from None
        if not isinstance(event, dict):
            raise CliError(f"claude cli exit {proc.returncode}: stdout line is not an event")
        events.append(event)
    result = next((e for e in reversed(events) if e.get("type") == "result"), None)
    if proc.returncode != 0 or result is None or result.get("is_error") or result.get("subtype") != "success":
        detail = (result or {}).get("result") or proc.stderr.strip() or "no result event"
        raise CliError(f"claude cli exit {proc.returncode}: {str(detail)[:300]}")
    if not isinstance(result.get("result"), str):
        raise CliError(f"claude cli exit {proc.returncode}: result event has no text")
    return Response(result["result"], {"argv": argv, "events": [_scrub(e) for e in events]}, sha)


TRANSPORTS: dict[str, Transport] = {
    "openai": _call_openai, "anthropic": _call_anthropic, "claude_cli": _call_claude_cli,
}


# --------------------------------------------------------------------------- retry

MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 1.0


def _status_of(exc: BaseException) -> int | None:
    if isinstance(exc, TransportError):
        return exc.status
    status = getattr(exc, "status_code", None)  # openai/anthropic APIStatusError
    return status if isinstance(status, int) else None


def is_retryable(exc: BaseException) -> bool:
    """429, any 5xx, or a connection-level failure. Everything else (400s, auth,
    programming errors) fails immediately."""
    if isinstance(exc, CliError):
        return False
    status = _status_of(exc)
    if status is not None:
        return status == 429 or status >= 500
    if isinstance(exc, (TransportError, ConnectionError, TimeoutError)):
        return True
    import anthropic
    import openai

    return isinstance(exc, (openai.APIConnectionError, anthropic.APIConnectionError))


def backoff_seconds(attempt: int, rng: Callable[[], float] = random.random) -> float:
    """Delay after failed attempt `attempt` (1-based): base * 2**(attempt-1), times 1..2 jitter."""
    return BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)) * (1.0 + rng())


class CallFailed(Exception):
    """The transport gave up. `attempts` is how many calls were made."""

    def __init__(self, cause: BaseException, attempts: int, exhausted: bool):
        self.cause, self.attempts, self.exhausted = cause, attempts, exhausted
        detail = f"retries exhausted after {attempts} attempts" if exhausted else "not retried"
        super().__init__(f"{cause} ({detail})")


def call_with_retry(
    transport: Transport,
    spec: ModelSpec,
    system: str,
    user: str,
    *,
    max_attempts: int = MAX_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
    rng: Callable[[], float] = random.random,
) -> "str | Response":
    for attempt in range(1, max_attempts + 1):
        try:
            return transport(spec, system, user)
        except Exception as exc:
            retryable = is_retryable(exc)
            if not retryable or attempt == max_attempts:
                raise CallFailed(exc, attempt, exhausted=retryable) from exc
            sleep(backoff_seconds(attempt, rng))
    raise AssertionError("unreachable")  # pragma: no cover


# --------------------------------------------------------------------------- generate


def generate(
    env: Envelope,
    spec: ModelSpec,
    include_inventory: bool = True,
    *,
    transport: Transport | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Layout:
    """One layout for one envelope. `transport` overrides the backend's caller
    (tests inject a fake); `sleep` is the backoff clock."""
    user = envelope_prompt(env, include_inventory)
    call = transport or TRANSPORTS.get(spec.backend)
    if call is None:
        return Layout(envelope_id=env.id, model=spec.name, parse_ok=False, failure_kind=TRANSPORT,
                      error=f"call: unknown backend {spec.backend!r}")  # nothing was sent: no sha
    try:
        reply = call_with_retry(call, spec, SYSTEM, user, sleep=sleep)
    except CallFailed as exc:  # provider errors are an outcome, not a crash
        return Layout(envelope_id=env.id, model=spec.name, parse_ok=False, failure_kind=TRANSPORT,
                      error=f"call: {exc}", prompt_sha256=getattr(exc.cause, "prompt_sha256", None))
    if isinstance(reply, Response):
        raw, cli, sha, observed = reply.text, reply.cli, reply.prompt_sha256, reply.observed
    else:  # a transport that reports nothing about its request: the strings it was handed
        raw, cli, sha, observed = reply, None, prompt_sha256(SYSTEM, user), None
    try:
        entities = parse_entities(raw)
    except (ValueError, ValidationError, json.JSONDecodeError) as exc:
        return Layout(envelope_id=env.id, model=spec.name, parse_ok=False, failure_kind=PARSE, raw=raw,
                      error=f"parse: {exc}", cli=cli, prompt_sha256=sha, observed=observed)
    return Layout(envelope_id=env.id, model=spec.name, entities=entities, raw=raw, cli=cli,
                  prompt_sha256=sha, observed=observed)

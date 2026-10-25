"""A transport failure is not a model parse failure.

`generate()` returned parse_ok=False for a dead server and for a reply that did not
parse alike, and e1_degradation counted both as "parse failure". On the canonical
corpus all three T3 failures were `call: Connection error`, so the peak of the
published ladder was a dead local server. These tests drive the real aggregation,
sweep and score commands with only the model call faked.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from envelope_shift import run
from envelope_shift.analysis import e1_degradation
from envelope_shift.failure import backfill_kinds, backfill_scores, kind_from_error, transport_path
from envelope_shift.generate import CallFailed, ModelSpec, generate
from envelope_shift.schema import Layout

ENVELOPE = "t0_office_10x11"
SPEC = ModelSpec(name="fake", backend="fake", model="fake")


def _row(i: int, ok: bool = True, kind: str | None = None, model: str = "m") -> dict:
    return {"envelope_id": f"e{i}", "tier": "T3", "model": model, "sample": 0, "parse_ok": ok,
            "failure_kind": kind, "coverage": 90.0, "navigability": 80.0, "overlap_clearance": 5.0}


def _cell(rows: list[dict]) -> dict:
    return e1_degradation.summarize(rows)[0]


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# --- the published rate -----------------------------------------------------

def test_a_transport_failure_does_not_raise_the_published_parse_failure_rate():
    """Fails against `1.0 - parsed/rows`, which read this tier as 20% parse failure."""
    ok = [_row(i) for i in range(8)]
    with_parse = ok + [_row(8, False, "parse")]
    cell = _cell(with_parse + [_row(9, False, "transport")])
    assert cell["parse_fail_rate"] == pytest.approx(0.1)  # 1 parse failure in 10 rows
    assert cell["parse_fail_rate"] <= _cell(with_parse + [_row(9)])["parse_fail_rate"]


def test_an_all_transport_failure_tier_has_a_zero_parse_failure_rate():
    """The canonical T3 shape: failures present, every one a dead server."""
    rows = [_row(i) for i in range(37)] + [_row(37 + i, False, "transport") for i in range(3)]
    cell = _cell(rows)
    assert cell["parse_fail_rate"] == 0.0
    assert cell["n_parse_fail"] == 0


def test_transport_failures_are_reported_not_dropped():
    rows = [_row(0), _row(1, False, "parse"), _row(2, False, "transport"), _row(3, False, "transport")]
    cell = _cell(rows)
    assert (cell["n_rows"], cell["n_parsed"], cell["n_parse_fail"], cell["n_transport"]) == (4, 1, 1, 2)
    assert {"n_parse_fail", "n_transport"} <= set(e1_degradation.FIELDS)


def test_rollup_row_reports_the_same_split():
    rows = [_row(0, model="a"), _row(1, False, "transport", model="a"),
            _row(2, False, "parse", model="b"), _row(3, False, "transport", model="b")]
    roll = [r for r in e1_degradation.summarize(rows) if r["model"] == e1_degradation.ALL_ARMS][0]
    assert (roll["n_parse_fail"], roll["n_transport"], roll["parse_fail_rate"]) == (1, 2, 0.25)


def test_a_failed_row_with_no_kind_is_refused_not_guessed():
    with pytest.raises(ValueError, match="backfill-failure-kinds"):
        e1_degradation.summarize([_row(0), _row(1, False, None)])


# --- the kind is data on the layout ----------------------------------------


def test_generate_records_the_kind_as_its_own_field():
    env = next(e for e in run.load_all() if e.id == ENVELOPE)
    down = generate(env, SPEC, transport=lambda *a: (_ for _ in ()).throw(CallFailed("down")), sleep=lambda s: None)
    garbage = generate(env, SPEC, transport=lambda *a: "not json", sleep=lambda s: None)
    assert (down.parse_ok, down.failure_kind) == (False, "transport")
    assert (garbage.parse_ok, garbage.failure_kind) == (False, "parse")


def test_kind_is_derived_from_the_legacy_error_prefix():
    assert kind_from_error("call: Connection error.") == "transport"
    assert kind_from_error("parse: 1 validation error") == "parse"
    assert kind_from_error("something else") is None
    old = {"envelope_id": "e", "model": "m", "parse_ok": False, "error": "call: Connection error."}
    assert Layout.model_validate(old).failure_kind == "transport"
    assert Layout.model_validate({"envelope_id": "e", "model": "m"}).failure_kind is None


# --- sweep and score -------------------------------------------------------

def _sweep_with(tmp_path, monkeypatch, layout_for) -> Path:
    monkeypatch.setattr(run, "generate", lambda env, spec, include_inventory=True: layout_for(env, spec))
    run.main(["sweep", "--models", "local", "--envelopes", ENVELOPE, "--samples", "3", "--out", str(tmp_path)])
    return tmp_path / "layouts.jsonl"


def test_sweep_keeps_transport_failures_out_of_layouts_and_score_carries_the_kind(tmp_path, monkeypatch):
    outcomes = iter([
        lambda env, spec: Layout(envelope_id=env.id, model=spec.model, raw="[]"),
        lambda env, spec: Layout(envelope_id=env.id, model=spec.model, parse_ok=False, failure_kind="parse",
                                 raw="x", error="parse: bad"),
        lambda env, spec: Layout(envelope_id=env.id, model=spec.model, parse_ok=False, failure_kind="transport",
                                 error="call: Connection error."),
    ])
    layouts = _sweep_with(tmp_path, monkeypatch, lambda env, spec: next(outcomes)(env, spec))
    assert [r["failure_kind"] for r in _rows(layouts)] == [None, "parse"]
    assert [r["failure_kind"] for r in _rows(transport_path(layouts))] == ["transport"]

    run.main(["score", str(layouts)])
    scores = _rows(tmp_path / "scores.jsonl")
    assert sorted(str(r["failure_kind"]) for r in scores) == ["None", "parse", "transport"]
    assert all(r["parse_ok"] is False for r in scores if r["failure_kind"])


# --- backfill --------------------------------------------------------------

def _legacy(tmp_path) -> Path:
    def rec(i, ok, err=None):
        return {"envelope_id": f"e{i}", "model": "m", "sample": 0, "parse_ok": ok, "error": err,
                "include_inventory": True}
    raw = [rec(0, True), rec(1, False, "parse: bad json"), rec(2, False, "call: Connection error. (retries exhausted)")]
    layouts = tmp_path / "layouts.jsonl"
    layouts.write_text("".join(json.dumps(r) + "\n" for r in raw))
    (tmp_path / "scores.jsonl").write_text("".join(
        json.dumps({"envelope_id": r["envelope_id"], "model": "m", "sample": 0, "parse_ok": r["parse_ok"]}) + "\n"
        for r in raw))
    return layouts


def test_backfill_classifies_from_the_prefixes_and_moves_transport_rows(tmp_path):
    layouts = _legacy(tmp_path)
    first_line = layouts.read_text().splitlines(keepends=True)[0]

    assert backfill_kinds(layouts) == (2, 1)
    assert backfill_scores(layouts) == 2
    assert _rows(layouts)[1]["failure_kind"] == "parse"
    assert layouts.read_text().splitlines(keepends=True)[0] == first_line  # untouched rows are byte-for-byte
    assert [r["envelope_id"] for r in _rows(layouts)] == ["e0", "e1"]
    assert [r["envelope_id"] for r in _rows(transport_path(layouts))] == ["e2"]
    assert {r["envelope_id"]: r.get("failure_kind") for r in _rows(tmp_path / "scores.jsonl")} == {
        "e0": None, "e1": "parse", "e2": "transport"}


def test_backfill_is_idempotent(tmp_path):
    layouts = _legacy(tmp_path)
    backfill_kinds(layouts)
    backfill_scores(layouts)
    before = (layouts.read_bytes(), transport_path(layouts).read_bytes(), (tmp_path / "scores.jsonl").read_bytes())
    assert backfill_kinds(layouts) == (0, 0)
    assert backfill_scores(layouts) == 0
    assert before == (layouts.read_bytes(), transport_path(layouts).read_bytes(), (tmp_path / "scores.jsonl").read_bytes())


def test_backfill_refuses_a_failure_that_names_neither_kind(tmp_path):
    layouts = tmp_path / "layouts.jsonl"
    layouts.write_text(json.dumps({"envelope_id": "e", "model": "m", "parse_ok": False, "error": "boom"}) + "\n")
    with pytest.raises(ValueError, match="neither"):
        backfill_kinds(layouts)

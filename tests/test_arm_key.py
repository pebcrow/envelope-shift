"""A pooled layouts.jsonl is uniquely keyed by what the analysis joins on.

`sweep` used to write `model` bare and `include_inventory` as a separate field,
while `score` alone suffixed `-noinv`. Pooling both arms into one file then made
(envelope_id, model, sample) collide, and a score row joined to the wrong arm's
raw text. These tests run the real sweep and score commands with only the model
call faked, so they fail against a writer that leaves the arm out of the record.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from envelope_shift import run
from envelope_shift.arm import arm_label, backfill_layouts
from envelope_shift.schema import Layout

ENVELOPE = "t0_office_10x11"
JOIN_KEY = ("envelope_id", "model", "sample")


def _fake_generate(env, spec, include_inventory=True):
    return Layout(envelope_id=env.id, model=spec.model, raw=f"inventory={include_inventory}")


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _pooled_sweep(tmp_path, monkeypatch) -> Path:
    monkeypatch.setattr(run, "generate", _fake_generate)
    for extra in ([], ["--no-inventory"]):
        run.main(["sweep", "--models", "local", "--envelopes", ENVELOPE, "--samples", "2",
                  "--out", str(tmp_path), *extra])
    return tmp_path / "layouts.jsonl"


def test_pooled_layouts_are_uniquely_keyed_by_the_join_fields(tmp_path, monkeypatch):
    rows = _rows(_pooled_sweep(tmp_path, monkeypatch))
    assert len(rows) == 4  # 2 arms x 2 samples
    keys = Counter(tuple(r[f] for f in JOIN_KEY) for r in rows)
    assert max(keys.values()) == 1, f"colliding keys: { {k: n for k, n in keys.items() if n > 1} }"


def test_score_row_traces_to_exactly_one_raw_row_of_its_own_arm(tmp_path, monkeypatch):
    layouts = _pooled_sweep(tmp_path, monkeypatch)
    run.main(["score", str(layouts)])
    raw = _rows(layouts)
    for score in _rows(tmp_path / "scores.jsonl"):
        matches = [r for r in raw if all(r[f] == score[f] for f in JOIN_KEY)]
        assert len(matches) == 1, score
        assert matches[0]["include_inventory"] == score["include_inventory"]
        assert matches[0]["raw"] == f"inventory={score['include_inventory']}"


def test_layout_and_score_agree_on_the_label(tmp_path, monkeypatch):
    layouts = _pooled_sweep(tmp_path, monkeypatch)
    run.main(["score", str(layouts)])
    assert {r["model"] for r in _rows(layouts)} == {r["model"] for r in _rows(tmp_path / "scores.jsonl")}


def test_arm_label_is_idempotent():
    assert arm_label("m", True) == "m"
    assert arm_label("m", False) == "m-noinv"
    assert arm_label("m-noinv", False) == "m-noinv"


def test_backfill_recovers_the_arm_from_include_inventory(tmp_path):
    legacy = [
        {"envelope_id": "e", "model": "m", "sample": 0, "include_inventory": True},
        {"envelope_id": "e", "model": "m", "sample": 0, "include_inventory": False},
    ]
    path = tmp_path / "layouts.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in legacy))
    untouched_line = path.read_text().splitlines(keepends=True)[0]

    assert backfill_layouts(path) == 1
    rows = _rows(path)
    assert [r["model"] for r in rows] == ["m", "m-noinv"]
    assert path.read_text().splitlines(keepends=True)[0] == untouched_line
    assert backfill_layouts(path) == 0  # idempotent


def test_backfill_refuses_a_row_whose_arm_is_not_recorded(tmp_path):
    path = tmp_path / "layouts.jsonl"
    path.write_text(json.dumps({"envelope_id": "e", "model": "m", "sample": 0}) + "\n")
    with pytest.raises(ValueError, match="include_inventory"):
        backfill_layouts(path)

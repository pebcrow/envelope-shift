"""Publishing the original sweeps: the sanitizer refuses leaks, and once original/raw/ is
committed, every results/ table reproduces from it alone."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from envelope_shift.analysis import original

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "layouts_tiny.jsonl"
_FAKE_ID = "0123abcd-" + "0000-4000-8000-" + "00000000beef"


def _results(tmp_path: Path, extra: dict | None = None) -> Path:
    """A results/ tree holding every analysed sweep, each a copy of the tiny fixture."""
    rows = [json.loads(line) for line in FIXTURE.read_text().splitlines() if line.strip()]
    if extra:
        rows[0].update(extra)
    for sweep in original.sweeps():
        d = tmp_path / "results" / sweep
        d.mkdir(parents=True)
        (d / "layouts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return tmp_path / "results"


def test_the_published_sweeps_are_the_analysed_pool_plus_e2b():
    assert original.sweeps()[-1] == "e2b_default"
    assert "claude_opus_e1" in original.sweeps() and "cloud" not in original.sweeps()


def test_leaks_names_the_kind_without_echoing_the_match():
    text = "ok\nid " + _FAKE_ID + "\n" + "/" + "home/someone/x\n"
    hits = original.leaks(text)
    assert hits == ["line 2: uuid", "line 3: path"]
    assert _FAKE_ID not in "".join(hits)


def test_sanitize_writes_every_sweep_and_strips_cli_ids(tmp_path):
    cli = {"argv": ["-p", "x"], "events": [
        {"type": "system", "subtype": "init", "model": "m", "session_id": _FAKE_ID},
        {"type": "result", "subtype": "success", "result": "{}", "uuid": _FAKE_ID, "modelUsage": {"m": {}}}]}
    raw = tmp_path / "raw"
    written = original.sanitize(_results(tmp_path, {"cli": cli}), raw)
    assert {p.parent.name for p in written} == set(original.sweeps())
    assert all(not original.leaks(p.read_text()) for p in written)


def test_sanitize_refuses_a_leak_outside_the_cli_events(tmp_path):
    with pytest.raises(ValueError, match="uuid"):
        original.sanitize(_results(tmp_path, {"error": "request " + _FAKE_ID}), tmp_path / "raw")


def test_sanitize_refuses_a_tree_missing_an_analysed_sweep(tmp_path):
    (tmp_path / "results").mkdir()
    with pytest.raises(FileNotFoundError):
        original.sanitize(tmp_path / "results", tmp_path / "raw")


@pytest.mark.original
@pytest.mark.skipif(not original.RAW.is_dir(), reason="original/raw/ is not committed yet")
def test_every_results_table_reproduces_from_the_committed_original_rows():
    assert original.check() == []

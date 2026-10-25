"""`envelope-shift score-layout`: the offline path from a committed layout to its metrics.

It must work on a fresh clone, with no results/ directory and no model, so it defaults to a
committed fixture, scores exactly one record, and writes nothing.
"""

from __future__ import annotations

import pytest

from envelope_shift import run
from envelope_shift.envelopes import load_all
from envelope_shift.failure import read_raw


def _printed(capsys) -> dict[str, str]:
    out = capsys.readouterr().out
    return dict(line.split(None, 1) for line in out.splitlines())


def test_default_is_a_committed_fixture():
    assert run.SMOKE_LAYOUTS.is_file()
    assert "results" not in run.SMOKE_LAYOUTS.parts


def test_scores_the_first_record_of_the_default_fixture(capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # nothing may be read from, or written to, the working dir
    run.main(["score-layout"])
    got = _printed(capsys)
    assert got["envelope_id"] == "t0_kitchen_12x14"
    for metric in ("coverage", "navigability", "overlap_clearance"):
        float(got[metric])
    assert list(tmp_path.iterdir()) == []


def test_prints_what_score_would_write_for_that_record(capsys):
    rec = read_raw(run.SMOKE_LAYOUTS)[1]
    expected = run.score_record(rec, {e.id: e for e in load_all()}, "strict")
    run.main(["score-layout", str(run.SMOKE_LAYOUTS), "--row", "1", "--params", "strict"])
    got = _printed(capsys)
    assert got["envelope_id"] == expected["envelope_id"]
    assert float(got["coverage"]) == pytest.approx(expected["coverage"], abs=1e-4)
    assert float(got["navigability"]) == pytest.approx(expected["navigability"], abs=1e-4)
    assert got["params"] == "strict"


def test_a_parse_failure_prints_no_metrics(capsys):
    rows = read_raw(run.SMOKE_LAYOUTS)
    i = next(n for n, r in enumerate(rows) if not r.get("parse_ok", True))
    run.main(["score-layout", "--row", str(i)])
    got = _printed(capsys)
    assert got["parse_ok"] == "False" and "coverage" not in got


def test_a_row_out_of_range_exits_with_a_message():
    with pytest.raises(SystemExit, match="no row 99"):
        run.main(["score-layout", "--row", "99"])

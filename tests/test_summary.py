"""Tests for envelope-shift summary: offline per-arm table from scores.jsonl."""

import json
import os
from pathlib import Path

import pytest

from envelope_shift.run import main as run_main


def _write_scores(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def _read_lines(path: Path) -> list[str]:
    return [l for l in path.read_text().splitlines() if l.strip()]


# ── hand-computed means ──────────────────────────────────────────────────

def test_hand_computed_means_and_n(tmp_path):
    """Arithmetic mean over parse_ok=true rows with finite values, n=count."""
    rows = [
        {"model": "opus", "parse_ok": True, "coverage": 80.0, "navigability": 50.0,
         "overlap_clearance": 10.0, "exp_isovist_area_mean": 100.0},
        {"model": "opus", "parse_ok": True, "coverage": 60.0, "navigability": 70.0,
         "overlap_clearance": 20.0, "exp_isovist_area_mean": 200.0},
        {"model": "sonnet", "parse_ok": True, "coverage": 90.0, "navigability": 40.0,
         "overlap_clearance": 30.0, "exp_isovist_area_mean": 300.0},
    ]
    _write_scores(tmp_path / "scores.jsonl", rows)
    out = tmp_path / "summary.md"
    run_main(["summary", str(tmp_path), "--out", str(out)])
    lines = _read_lines(out)
    # source line
    assert str(tmp_path / "scores.jsonl") in lines[1]
    assert "3 rows" in lines[1]
    # arm rows (sorted alphabetically, skip header and separator)
    arm_lines = [l for l in lines if l.startswith("|") and l.endswith("|") and "arm" not in l.lower() and "---" not in l]
    assert len(arm_lines) == 2
    # opus: mean(80,60)=70.0, mean(50,70)=60.0, mean(10,20)=15.0, mean(100,200)=150.0, n=2
    opus_line = next(l for l in arm_lines if "opus" in l)
    for val in ["70.0 (n=2)", "60.0 (n=2)", "15.0 (n=2)", "150.0 (n=2)"]:
        assert val in opus_line, f"{val} not in {opus_line}"
    # sonnet: mean(90)=90.0, mean(40)=40.0, mean(30)=30.0, mean(300)=300.0, n=1
    sonnet_line = next(l for l in arm_lines if "sonnet" in l)
    for val in ["90.0 (n=1)", "40.0 (n=1)", "30.0 (n=1)", "300.0 (n=1)"]:
        assert val in sonnet_line, f"{val} not in {sonnet_line}"


# ── parse_ok false excluded ─────────────────────────────────────────────

def test_parse_ok_false_row_excluded(tmp_path):
    """A row with parse_ok=false is excluded from all cell averages."""
    rows = [
        {"model": "opus", "parse_ok": True, "coverage": 80.0, "navigability": 50.0,
         "overlap_clearance": 10.0, "exp_isovist_area_mean": 100.0},
        {"model": "opus", "parse_ok": False, "coverage": 0.0, "navigability": 0.0,
         "overlap_clearance": 0.0, "exp_isovist_area_mean": 0.0},
    ]
    _write_scores(tmp_path / "scores.jsonl", rows)
    out = tmp_path / "summary.md"
    run_main(["summary", str(tmp_path), "--out", str(out)])
    lines = _read_lines(out)
    arm_lines = [l for l in lines if l.startswith("|") and "opus" in l]
    assert len(arm_lines) == 1
    # only the parse_ok=true row counts: n=1
    assert "80.0 (n=1)" in arm_lines[0]
    assert "80.0 (n=2)" not in arm_lines[0]


# ── null and NaN excluded from cell only ─────────────────────────────────

def test_null_and_nan_excluded_from_cell(tmp_path, capsys):
    """Null and NaN in one metric are excluded from that cell only.
    NaN is counted as non-finite and triggers the skip note."""
    rows = [
        {"model": "opus", "parse_ok": True, "coverage": 80.0, "navigability": None,
         "overlap_clearance": 10.0, "exp_isovist_area_mean": 100.0},
        {"model": "opus", "parse_ok": True, "coverage": 60.0, "navigability": float("nan"),
         "overlap_clearance": 20.0, "exp_isovist_area_mean": 200.0},
    ]
    _write_scores(tmp_path / "scores.jsonl", rows)
    out = tmp_path / "summary.md"
    run_main(["summary", str(tmp_path), "--out", str(out)])
    lines = _read_lines(out)
    arm_lines = [l for l in lines if l.startswith("|") and "opus" in l]
    assert len(arm_lines) == 1
    line = arm_lines[0]
    # coverage: mean(80,60)=70.0, n=2
    assert "70.0 (n=2)" in line
    # navigability: both null/NaN -> n=0
    assert "\u2014 (n=0)" in line
    # overlap_clearance: mean(10,20)=15.0, n=2
    assert "15.0 (n=2)" in line
    # exp_isovist_area_mean: mean(100,200)=150.0, n=2
    assert "150.0 (n=2)" in line
    # NaN is counted as non-finite → Note line and stderr skip
    text = out.read_text()
    assert "Note: skipped 1 (0 malformed lines, 1 non-finite values)." in text
    stderr = capsys.readouterr().err
    assert "skipped 1 (0 malformed lines, 1 non-finite values)" in stderr


# ── 10**400 counted as non-finite ────────────────────────────────────────

def test_large_int_counted_as_nonfinite(tmp_path, capsys):
    """An int too large for float (10**400) is excluded from its cell and counted."""
    rows = [
        {"model": "opus", "parse_ok": True, "coverage": 10**400, "navigability": 50.0,
         "overlap_clearance": 10.0, "exp_isovist_area_mean": 100.0},
        {"model": "opus", "parse_ok": True, "coverage": 80.0, "navigability": 70.0,
         "overlap_clearance": 20.0, "exp_isovist_area_mean": 200.0},
    ]
    _write_scores(tmp_path / "scores.jsonl", rows)
    out = tmp_path / "summary.md"
    run_main(["summary", str(tmp_path), "--out", str(out)])
    lines = _read_lines(out)
    arm_lines = [l for l in lines if l.startswith("|") and "opus" in l]
    assert len(arm_lines) == 1
    line = arm_lines[0]
    # coverage: 10**400 excluded, only 80.0 -> n=1
    assert "80.0 (n=1)" in line
    # navigability: mean(50,70)=60.0, n=2
    assert "60.0 (n=2)" in line
    # stderr and Note line
    stderr = capsys.readouterr().err
    assert "skipped 1 (0 malformed lines, 1 non-finite values)" in stderr
    text = out.read_text()
    assert "Note: skipped 1 (0 malformed lines, 1 non-finite values)." in text


# ── malformed lines counted ──────────────────────────────────────────────

def test_malformed_lines_counted(tmp_path, capsys):
    """A malformed line, a JSON array line, and invalid UTF-8 are each counted."""
    scores = tmp_path / "scores.jsonl"
    scores.write_bytes(
        b'{"model": "opus", "parse_ok": true, "coverage": 80.0, "navigability": 50.0,'
        b' "overlap_clearance": 10.0, "exp_isovist_area_mean": 100.0}\n'
        b'{invalid json}\n'
        b'[1, 2, 3]\n'
        b'\xff\xfe bad utf-8\n'
        b'{"model": "opus", "parse_ok": true, "coverage": 60.0, "navigability": 70.0,'
        b' "overlap_clearance": 20.0, "exp_isovist_area_mean": 200.0}\n'
    )
    out = tmp_path / "summary.md"
    run_main(["summary", str(tmp_path), "--out", str(out)])
    lines = _read_lines(out)
    arm_lines = [l for l in lines if l.startswith("|") and "opus" in l]
    assert len(arm_lines) == 1
    line = arm_lines[0]
    # Only the 2 valid rows count
    assert "70.0 (n=2)" in line  # mean(50,70)
    assert "15.0 (n=2)" in line  # mean(10,20)
    # 3 malformed lines
    stderr = capsys.readouterr().err
    assert "skipped 3 (3 malformed lines, 0 non-finite values)" in stderr
    text = out.read_text()
    assert "Note: skipped 3 (3 malformed lines, 0 non-finite values)." in text
    # Source still counts only parsed rows
    assert "2 rows" in lines[1]


# ── blank lines not counted ──────────────────────────────────────────────

def test_blank_lines_not_counted(tmp_path, capsys):
    """Blank lines between JSON rows are ignored and not counted as malformed."""
    scores = tmp_path / "scores.jsonl"
    scores.write_bytes(
        b'{"model": "opus", "parse_ok": true, "coverage": 80.0, "navigability": 50.0,'
        b' "overlap_clearance": 10.0, "exp_isovist_area_mean": 100.0}\n'
        b'\n'
        b'\n'
        b'{"model": "opus", "parse_ok": true, "coverage": 60.0, "navigability": 70.0,'
        b' "overlap_clearance": 20.0, "exp_isovist_area_mean": 200.0}\n'
        b'\n'
    )
    out = tmp_path / "summary.md"
    run_main(["summary", str(tmp_path), "--out", str(out)])
    lines = _read_lines(out)
    arm_lines = [l for l in lines if l.startswith("|") and "opus" in l]
    assert len(arm_lines) == 1
    line = arm_lines[0]
    assert "70.0 (n=2)" in line
    # No skips
    stderr = capsys.readouterr().err
    assert "skipped" not in stderr
    text = out.read_text()
    assert "Note: skipped" not in text


# ── clean input produces no Note or stderr ───────────────────────────────

def test_clean_input_no_note_or_skip(tmp_path, capsys):
    """Clean input: no Note line, no stderr skip message, output matches baseline."""
    rows = [
        {"model": "opus", "parse_ok": True, "coverage": 80.0, "navigability": 50.0,
         "overlap_clearance": 10.0, "exp_isovist_area_mean": 100.0},
    ]
    _write_scores(tmp_path / "scores.jsonl", rows)
    out = tmp_path / "summary.md"
    run_main(["summary", str(tmp_path), "--out", str(out)])
    stderr = capsys.readouterr().err
    assert "skipped" not in stderr
    text = out.read_text()
    # Only the exploratory footnote, no skip note
    note_lines = [l for l in text.splitlines() if l.startswith("Note:")]
    assert len(note_lines) == 1
    assert "exploratory" in note_lines[0].lower()


# ── pool dir vs fallback vs direct file ──────────────────────────────────

def test_pool_dir_fallback_direct_file(tmp_path):
    """Pool dir takes priority over fallback; direct file works."""
    # pool dir scores (opus)
    pool_dir = tmp_path / "all"
    _write_scores(pool_dir / "scores.jsonl", [
        {"model": "opus", "parse_ok": True, "coverage": 80.0, "navigability": 50.0,
         "overlap_clearance": 10.0, "exp_isovist_area_mean": 100.0},
    ])
    # fallback scores (sonnet)
    _write_scores(tmp_path / "scores.jsonl", [
        {"model": "sonnet", "parse_ok": True, "coverage": 90.0, "navigability": 40.0,
         "overlap_clearance": 20.0, "exp_isovist_area_mean": 200.0},
    ])
    out = tmp_path / "pool.md"
    run_main(["summary", str(tmp_path), "--pool", "all", "--out", str(out)])
    # pool dir wins
    assert "opus" in out.read_text()
    assert "sonnet" not in out.read_text()

    # without --pool: both all/ and scores.jsonl exist -> all/ wins (opus, not sonnet)
    out2 = tmp_path / "default.md"
    run_main(["summary", str(tmp_path), "--out", str(out2)])
    assert "opus" in out2.read_text()
    assert "sonnet" not in out2.read_text()

    # fallback: flat dir with only scores.jsonl (no all/) -> sonnet
    flat = tmp_path / "flat"
    _write_scores(flat / "scores.jsonl", [
        {"model": "sonnet", "parse_ok": True, "coverage": 90.0, "navigability": 40.0,
         "overlap_clearance": 20.0, "exp_isovist_area_mean": 200.0},
    ])
    out3 = tmp_path / "fallback.md"
    run_main(["summary", str(flat), "--out", str(out3)])
    assert "sonnet" in out3.read_text()

    # direct file
    out4 = tmp_path / "direct.md"
    run_main(["summary", str(pool_dir / "scores.jsonl"), "--out", str(out4)])
    assert "opus" in out4.read_text()


# ── exit 2: path not found ───────────────────────────────────────────────

def test_exit2_path_not_found(tmp_path, capsys):
    """Non-existent path exits 2 with the path in stderr; no --out written."""
    out = tmp_path / "out.md"
    with pytest.raises(SystemExit) as exc:
        run_main(["summary", str(tmp_path / "nope"), "--out", str(out)])
    assert exc.value.code == 2
    assert not out.exists()
    stderr = capsys.readouterr().err
    assert "results path not found:" in stderr
    assert str(tmp_path / "nope") in stderr


# ── exit 2: no scores.jsonl under directory ──────────────────────────────

def test_exit2_no_scores_jsonl(tmp_path, capsys):
    """Directory with no scores.jsonl anywhere exits 2 with path in stderr."""
    out = tmp_path / "out.md"
    # Create a directory with neither <pool>/scores.jsonl nor scores.jsonl
    tmp_path.mkdir(exist_ok=True)
    with pytest.raises(SystemExit) as exc:
        run_main(["summary", str(tmp_path), "--out", str(out)])
    assert exc.value.code == 2
    assert not out.exists()
    stderr = capsys.readouterr().err
    assert "no scores.jsonl under" in stderr
    assert str(tmp_path) in stderr


# ── exit 2: empty scores.jsonl ──────────────────────────────────────────

def test_exit2_empty_file(tmp_path, capsys):
    """scores.jsonl with no non-blank lines exits 2; no --out written."""
    scores = tmp_path / "scores.jsonl"
    scores.write_text("\n\n  \n")
    out = tmp_path / "out.md"
    with pytest.raises(SystemExit) as exc:
        run_main(["summary", str(tmp_path), "--out", str(out)])
    assert exc.value.code == 2
    assert not out.exists()
    stderr = capsys.readouterr().err
    assert "results file is empty:" in stderr
    assert str(scores) in stderr


# ── nothing written besides --out ────────────────────────────────────────

def test_no_extra_files_written(tmp_path):
    """Only --out is created; nothing else is written."""
    _write_scores(tmp_path / "scores.jsonl", [
        {"model": "opus", "parse_ok": True, "coverage": 80.0, "navigability": 50.0,
         "overlap_clearance": 10.0, "exp_isovist_area_mean": 100.0},
    ])
    files_before = {f.name for f in tmp_path.iterdir()}
    out = tmp_path / "out.md"
    run_main(["summary", str(tmp_path), "--out", str(out)])
    files_after = {f.name for f in tmp_path.iterdir()}
    added = files_after - files_before
    assert added == {"out.md"}


# ── title and footnote ───────────────────────────────────────────────────

def test_title_and_footnote(tmp_path):
    """Output starts with the title line and includes the section-7 footnote."""
    _write_scores(tmp_path / "scores.jsonl", [
        {"model": "opus", "parse_ok": True, "coverage": 80.0, "navigability": 50.0,
         "overlap_clearance": 10.0, "exp_isovist_area_mean": 100.0},
    ])
    out = tmp_path / "summary.md"
    run_main(["summary", str(tmp_path), "--out", str(out)])
    text = out.read_text()
    assert text.startswith("# envelope-shift summary")
    assert "section 7" in text.lower()
    assert "exploratory" in text.lower()


# ── parse_ok edge cases (string true/false, 1, missing) ──────────────────

def test_parse_ok_string_bools_and_missing(tmp_path):
    """Only parse_ok is exactly True counts; string 'true','false', 1, and missing are excluded."""
    rows = [
        {"model": "opus", "parse_ok": True, "coverage": 80.0, "navigability": 50.0,
         "overlap_clearance": 10.0, "exp_isovist_area_mean": 100.0},
        {"model": "opus", "parse_ok": "true", "coverage": 999.0, "navigability": 999.0,
         "overlap_clearance": 999.0, "exp_isovist_area_mean": 999.0},
        {"model": "opus", "parse_ok": "false", "coverage": 888.0, "navigability": 888.0,
         "overlap_clearance": 888.0, "exp_isovist_area_mean": 888.0},
        {"model": "opus", "parse_ok": 1, "coverage": 777.0, "navigability": 777.0,
         "overlap_clearance": 777.0, "exp_isovist_area_mean": 777.0},
        {"model": "opus", "coverage": 666.0, "navigability": 666.0,
         "overlap_clearance": 666.0, "exp_isovist_area_mean": 666.0},
    ]
    _write_scores(tmp_path / "scores.jsonl", rows)
    out = tmp_path / "summary.md"
    run_main(["summary", str(tmp_path), "--out", str(out)])
    lines = _read_lines(out)
    arm_lines = [l for l in lines if l.startswith("|") and "opus" in l]
    assert len(arm_lines) == 1
    line = arm_lines[0]
    # only the parse_ok=True row counts: n=1, mean=80.0
    assert "80.0 (n=1)" in line
    assert "999.0" not in line
    assert "888.0" not in line
    assert "777.0" not in line
    assert "666.0" not in line


# ── non-numeric metric values (bool true, string "5") excluded from cell ─

def test_metric_bool_and_string_values_excluded(tmp_path):
    """A metric value that is a bool or string is excluded from that cell."""
    rows = [
        {"model": "opus", "parse_ok": True, "coverage": True, "navigability": "5",
         "overlap_clearance": 10.0, "exp_isovist_area_mean": 100.0},
        {"model": "opus", "parse_ok": True, "coverage": 60.0, "navigability": 40.0,
         "overlap_clearance": 20.0, "exp_isovist_area_mean": 200.0},
    ]
    _write_scores(tmp_path / "scores.jsonl", rows)
    out = tmp_path / "summary.md"
    run_main(["summary", str(tmp_path), "--out", str(out)])
    lines = _read_lines(out)
    arm_lines = [l for l in lines if l.startswith("|") and "opus" in l]
    assert len(arm_lines) == 1
    line = arm_lines[0]
    # coverage: True excluded, only 60.0 -> n=1
    assert "60.0 (n=1)" in line
    assert "True" not in line
    # navigability: "5" excluded, only 40.0 -> n=1
    assert "40.0 (n=1)" in line
    # overlap_clearance: both valid -> mean(10,20)=15.0, n=2
    assert "15.0 (n=2)" in line
    # exp_isovist_area_mean: both valid -> mean(100,200)=150.0, n=2
    assert "150.0 (n=2)" in line


# ── null model renders (none) row ────────────────────────────────────────

def test_null_model_renders_none_row(tmp_path):
    """A row with model=null alongside a named arm renders an (none) row and does not crash."""
    rows = [
        {"model": "opus", "parse_ok": True, "coverage": 80.0, "navigability": 50.0,
         "overlap_clearance": 10.0, "exp_isovist_area_mean": 100.0},
        {"model": None, "parse_ok": True, "coverage": 60.0, "navigability": 40.0,
         "overlap_clearance": 20.0, "exp_isovist_area_mean": 200.0},
    ]
    _write_scores(tmp_path / "scores.jsonl", rows)
    out = tmp_path / "summary.md"
    run_main(["summary", str(tmp_path), "--out", str(out)])
    text = out.read_text()
    assert "(none)" in text
    none_line = [l for l in text.splitlines() if l.startswith("|") and "(none)" in l]
    assert len(none_line) == 1
    assert "60.0 (n=1)" in none_line[0]
    opus_line = [l for l in text.splitlines() if l.startswith("|") and "opus" in l]
    assert len(opus_line) == 1
    assert "80.0 (n=1)" in opus_line[0]


# ── arm with zero valid values ───────────────────────────────────────────

def test_arm_zero_valid_values(tmp_path):
    """An arm with no valid values for any metric renders \u2014 (n=0) per cell."""
    rows = [
        {"model": "broken", "parse_ok": False, "coverage": None, "navigability": None,
         "overlap_clearance": None, "exp_isovist_area_mean": None},
    ]
    _write_scores(tmp_path / "scores.jsonl", rows)
    out = tmp_path / "summary.md"
    run_main(["summary", str(tmp_path), "--out", str(out)])
    lines = _read_lines(out)
    arm_lines = [l for l in lines if l.startswith("|") and "broken" in l]
    assert len(arm_lines) == 1
    assert "\u2014 (n=0)" in arm_lines[0]


# ── exit 2: trailing slash preserved in messages ─────────────────────────

def test_exit2_trailing_slash_not_found(tmp_path, capsys):
    """Non-existent path with trailing slash shows the exact raw string."""
    out = tmp_path / "out.md"
    with pytest.raises(SystemExit) as exc:
        run_main(["summary", str(tmp_path / "nope") + "/", "--out", str(out)])
    assert exc.value.code == 2
    stderr = capsys.readouterr().err
    assert "results path not found: " in stderr
    assert str(tmp_path / "nope") + "/" in stderr


def test_exit2_trailing_slash_no_scores(tmp_path, capsys):
    """Existing dir with trailing slash and no scores.jsonl preserves raw string."""
    mydir = tmp_path / "mydir"
    mydir.mkdir()
    out = tmp_path / "out.md"
    with pytest.raises(SystemExit) as exc:
        run_main(["summary", str(mydir) + "/", "--out", str(out)])
    assert exc.value.code == 2
    stderr = capsys.readouterr().err
    assert "no scores.jsonl under " in stderr
    assert str(mydir) + "/" in stderr


# ── exit 2: unreadable scores.jsonl ──────────────────────────────────────

def test_exit2_unreadable_scores_jsonl(tmp_path, capsys):
    """Unreadable scores.jsonl exits 2 with error message, not traceback."""
    if os.geteuid() == 0:
        pytest.skip("cannot chmod 000 as root")
    scores = tmp_path / "scores.jsonl"
    scores.write_text('{"model": "opus", "parse_ok": true, "coverage": 80.0, "navigability": 50.0, "overlap_clearance": 10.0, "exp_isovist_area_mean": 100.0}\n')
    scores.chmod(0o000)
    out = tmp_path / "out.md"
    try:
        with pytest.raises(SystemExit) as exc:
            run_main(["summary", str(tmp_path), "--out", str(out)])
        assert exc.value.code == 2
        assert not out.exists()
        stderr = capsys.readouterr().err
        assert "cannot read results file:" in stderr
        assert str(scores) in stderr
    finally:
        scores.chmod(0o644)


# ── UTF-8 BOM ────────────────────────────────────────────────────────────

def test_bom_stripped(tmp_path, capsys):
    """UTF-8 BOM at start of file doesn't cost the first row."""
    scores = tmp_path / "scores.jsonl"
    bom = b'\xef\xbb\xbf'
    scores.write_bytes(
        bom
        + b'{"model": "opus", "parse_ok": true, "coverage": 80.0, "navigability": 50.0, "overlap_clearance": 10.0, "exp_isovist_area_mean": 100.0}\n'
        + b'{"model": "opus", "parse_ok": true, "coverage": 60.0, "navigability": 70.0, "overlap_clearance": 20.0, "exp_isovist_area_mean": 200.0}\n'
    )
    out = tmp_path / "summary.md"
    run_main(["summary", str(tmp_path), "--out", str(out)])
    text = out.read_text()
    assert "2 rows" in text
    assert "70.0 (n=2)" in text
    stderr = capsys.readouterr().err
    assert "skipped" not in stderr
    note_lines = [l for l in text.splitlines() if l.startswith("Note:")]
    assert len(note_lines) == 1


# ── Infinity / -Infinity ─────────────────────────────────────────────────

def test_infinity_values(tmp_path, capsys):
    """Rows with Infinity and -Infinity are counted as non-finite."""
    rows = [
        {"model": "opus", "parse_ok": True, "coverage": float("inf"), "navigability": 50.0,
         "overlap_clearance": 10.0, "exp_isovist_area_mean": 100.0},
        {"model": "opus", "parse_ok": True, "coverage": float("-inf"), "navigability": 70.0,
         "overlap_clearance": 20.0, "exp_isovist_area_mean": 200.0},
    ]
    _write_scores(tmp_path / "scores.jsonl", rows)
    out = tmp_path / "summary.md"
    run_main(["summary", str(tmp_path), "--out", str(out)])
    text = out.read_text()
    assert "2 rows" in text
    assert "15.0 (n=2)" in text
    stderr = capsys.readouterr().err
    assert "skipped 2 (0 malformed lines, 2 non-finite values)" in stderr


# ── 5000-digit int ───────────────────────────────────────────────────────

def test_5000_digit_int(tmp_path, capsys):
    """A 5000-digit int line is counted as malformed."""
    scores = tmp_path / "scores.jsonl"
    big_int = "9" * 5000
    scores.write_bytes(
        b'{"model": "opus", "parse_ok": true, "coverage": 80.0, "navigability": 50.0, "overlap_clearance": 10.0, "exp_isovist_area_mean": 100.0}\n'
        + ('{"model": "opus", "parse_ok": true, "coverage": ' + big_int + ', "navigability": 50.0, "overlap_clearance": 10.0, "exp_isovist_area_mean": 100.0}\n').encode()
        + b'{"model": "opus", "parse_ok": true, "coverage": 60.0, "navigability": 70.0, "overlap_clearance": 20.0, "exp_isovist_area_mean": 200.0}\n'
    )
    out = tmp_path / "summary.md"
    run_main(["summary", str(tmp_path), "--out", str(out)])
    text = out.read_text()
    assert "2 rows" in text
    stderr = capsys.readouterr().err
    assert "1 malformed" in stderr


# ── 20000-deep nested array ──────────────────────────────────────────────

def test_20000_deep_nested_array(tmp_path, capsys):
    """A 20000-deep [[[[...]]]] line is counted as malformed."""
    scores = tmp_path / "scores.jsonl"
    deep = "[" * 20000 + "1" + "]" * 20000
    scores.write_bytes(
        b'{"model": "opus", "parse_ok": true, "coverage": 80.0, "navigability": 50.0, "overlap_clearance": 10.0, "exp_isovist_area_mean": 100.0}\n'
        + deep.encode() + b'\n'
        + b'{"model": "opus", "parse_ok": true, "coverage": 60.0, "navigability": 70.0, "overlap_clearance": 20.0, "exp_isovist_area_mean": 200.0}\n'
    )
    out = tmp_path / "summary.md"
    run_main(["summary", str(tmp_path), "--out", str(out)])
    text = out.read_text()
    assert "2 rows" in text
    stderr = capsys.readouterr().err
    assert "1 malformed" in stderr


# ── golden output ────────────────────────────────────────────────────────

def test_golden_output(tmp_path):
    """Golden test: 3-row clean fixture produces exact expected output."""
    scores = tmp_path / "scores.jsonl"
    _write_scores(scores, [
        {"model": "opus", "parse_ok": True, "coverage": 80.0, "navigability": 50.0,
         "overlap_clearance": 10.0, "exp_isovist_area_mean": 100.0},
        {"model": "opus", "parse_ok": True, "coverage": 60.0, "navigability": 70.0,
         "overlap_clearance": 20.0, "exp_isovist_area_mean": 200.0},
        {"model": "sonnet", "parse_ok": True, "coverage": 90.0, "navigability": 40.0,
         "overlap_clearance": 30.0, "exp_isovist_area_mean": 300.0},
    ])
    out = tmp_path / "summary.md"
    run_main(["summary", str(tmp_path), "--out", str(out)])
    source_line = f"Source: {scores} | 3 rows"
    expected = (
        "# envelope-shift summary\n"
        "\n"
        f"{source_line}\n"
        "\n"
        "| arm | coverage | navigability | overlap_clearance | exp_isovist_area_mean (exploratory, unvalidated) |\n"
        "|---|---|---|---|---|\n"
        "| opus | 70.0 (n=2) | 60.0 (n=2) | 15.0 (n=2) | 150.0 (n=2) |\n"
        "| sonnet | 90.0 (n=1) | 40.0 (n=1) | 30.0 (n=1) | 300.0 (n=1) |\n"
        "\n"
        "Note: exp_isovist_area_mean is exploratory and unvalidated against human preference (report section 7).\n"
    )
    assert out.read_text() == expected

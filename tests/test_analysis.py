import csv
import math
from pathlib import Path

import numpy as np
import pytest

from envelope_shift.analysis import e1_degradation, e2b_bestofn, e3_disagreement, e4_correlation
from envelope_shift.analysis._common import PUBLISHED, bootstrap_ci, shannon_entropy, spearman

FIXTURES = Path(__file__).parent / "fixtures"
SCORES = FIXTURES / "scores_tiny.jsonl"
LAYOUTS = FIXTURES / "layouts_tiny.jsonl"


def read_csv(path: Path) -> list[dict]:
    with path.open() as f:
        return list(csv.DictReader(f))


def test_fixture_present():
    assert SCORES.exists() and LAYOUTS.exists()


def test_e1_runs_and_ci_brackets_mean(tmp_path):
    summary = e1_degradation.run(SCORES, tmp_path)
    assert (tmp_path / "e1_degradation.csv").exists()
    assert (tmp_path / "e1_degradation.png").stat().st_size > 0
    assert len(summary) == 18  # 6 tiers x (2 models + the 'all arms' rollup)
    assert len(read_csv(tmp_path / "e1_degradation.csv")) == 18
    rollups = [r for r in summary if r["model"] == e1_degradation.ALL_ARMS]
    assert len(rollups) == 6
    # the rollup pools the arms: its n_rows is the sum of the tier's arm rows
    for roll in rollups:
        arms = [r for r in summary if r["tier"] == roll["tier"] and r is not roll]
        assert roll["n_rows"] == sum(r["n_rows"] for r in arms)
        assert roll["n_parsed"] == sum(r["n_parsed"] for r in arms)
    for r in summary:
        assert 0.0 <= r["parse_fail_rate"] <= 1.0
        for m in PUBLISHED:
            assert r[f"{m}_lo"] <= r[f"{m}_mean"] <= r[f"{m}_hi"], (r["tier"], r["model"], m)
    assert any(r["parse_fail_rate"] > 0 for r in summary)


def test_e1_cli(tmp_path, capsys):
    e1_degradation.main([str(SCORES), str(tmp_path)])
    assert "E1:" in capsys.readouterr().out


def test_e3_runs_and_flags_only_disagreement(tmp_path):
    flagged = e3_disagreement.run(SCORES, tmp_path)
    assert (tmp_path / "e3_disagreement.csv").exists()
    assert (tmp_path / "e3_disagreement.png").stat().st_size > 0
    ids = (tmp_path / "e3_render_ids.txt").read_text().split()
    assert set(ids) == {r["envelope_id"] for r in flagged}
    for r in flagged:
        assert r["coverage"] >= 90
        assert r["navigability"] < 50 or r["overlap_clearance"] >= 10
    assert len(flagged) >= 1  # the fixture has at least one sharp disagreement


def test_e4_runs_and_rho_in_range(tmp_path, capsys):
    table = e4_correlation.run(SCORES, tmp_path)
    assert (tmp_path / "e4_correlation.csv").exists()
    assert (tmp_path / "e4_correlation.png").stat().st_size > 0
    assert table, "no exp_* columns found"
    assert all(not r["exp_column"].startswith("exp_exploratory") for r in table)  # bool column skipped
    for r in table:
        for m in PUBLISHED:
            rho = r[f"{m}_rho"]
            assert math.isnan(rho) or -1.0 <= rho <= 1.0
    e4_correlation.main([str(SCORES), str(tmp_path)])
    out = capsys.readouterr().out
    assert "adds little" in out or "adds information" in out


def test_e2b_runs_and_diversity_finite(tmp_path):
    table = e2b_bestofn.run(SCORES, tmp_path, LAYOUTS)
    assert (tmp_path / "e2b_bestofn.csv").exists()
    assert (tmp_path / "e2b_bestofn.png").stat().st_size > 0
    groups = [r for r in table if r["envelope_id"] != "ALL"]
    totals = [r for r in table if r["envelope_id"] == "ALL"]
    assert len(groups) == 4  # 2 models x 2 T5 rooms with samples 0..3
    assert len(totals) == 2
    for r in groups:
        assert r["n"] >= 2
        assert r["best_coverage"] >= r["pool_mean_coverage"]
        assert math.isfinite(r["sel_entropy"]) and math.isfinite(r["pool_mean_entropy"])
        assert 0 <= r["sel_unique"] <= r["pool_agg_unique"]
    for r in totals:
        assert math.isfinite(r["sel_entropy"]) and math.isfinite(r["pool_agg_entropy"])
        assert r["rand_draws"] == e2b_bestofn.RAND_DRAWS and r["rand_seed"] == e2b_bestofn.RAND_SEED
        assert r["rand_entropy_p05"] <= r["rand_entropy_mean"] <= r["rand_entropy_p95"]
        assert 0.0 <= r["rand_frac_le_sel"] <= 1.0
        assert r["tb_entropy_p05"] <= r["tb_entropy_mean"] <= r["tb_entropy_p95"]
        assert 0.0 <= r["tb_frac_rand_le"] <= 1.0
    for r in groups:
        assert "rand_entropy_mean" not in r and "tb_entropy_mean" not in r


def test_e2b_random_baseline_is_same_size_and_seeded():
    """The baseline draws ONE sample per room, like the selection it is compared with.

    Two rooms, each with a one-type sample and a four-type sample: every draw holds exactly two
    samples, so its entropy lies between the all-narrow and all-wide pair, never the pool's.
    """
    narrow, wide = ["a"], ["b", "c", "d", "e"]
    rooms = [[narrow, wide], [narrow, ["f", "g", "h", "i"]]]
    b = e2b_bestofn.random_baseline(rooms, sel_entropy=shannon_entropy([2]))
    lo, hi = shannon_entropy([2]), shannon_entropy([1] * 8)
    assert lo <= b["rand_entropy_p05"] <= b["rand_entropy_mean"] <= b["rand_entropy_p95"] <= hi
    assert b["rand_entropy_mean"] < shannon_entropy([2, 1, 1, 1, 1, 1, 1, 1, 1])  # the pool's
    assert 0.1 < b["rand_frac_le_sel"] < 0.4                                   # ~1/4 draw both narrow
    assert b == e2b_bestofn.random_baseline(rooms, sel_entropy=shannon_entropy([2]))


def test_e2b_tiebreak_is_random_among_top_coverage_samples():
    """Best-of-N takes the first sample on a coverage tie; the tb_* columns take a random one.

    Each room has a one-type sample first and a four-type sample second, tied at the top
    (index 0 and 1) plus a third, lower sample. First-wins always picks the narrow one; random
    tie-breaking picks it half the time, so the tie-broken entropy lies strictly above the
    first-wins entropy, and never reaches the all-wide value.
    """
    narrow, wide, low = ["a"], ["b", "c", "d", "e"], ["z"]
    rooms = [[narrow, wide, low], [narrow, ["f", "g", "h", "i"], low]]
    first_wins = shannon_entropy([2])
    b = e2b_bestofn.random_baseline(rooms, sel_entropy=first_wins, tied=[[0, 1], [0, 1]])
    assert first_wins < b["tb_entropy_mean"] < shannon_entropy([1] * 8)
    assert b["tb_entropy_p05"] <= b["tb_entropy_mean"] <= b["tb_entropy_p95"]
    # a single top sample per room is a deterministic selection: no tie to break
    fixed = e2b_bestofn.random_baseline(rooms, sel_entropy=first_wins, tied=[[0], [0]])
    assert fixed["tb_entropy_mean"] == pytest.approx(first_wins)
    assert fixed["tb_entropy_p05"] == fixed["tb_entropy_p95"]
    assert "tb_entropy_mean" not in e2b_bestofn.random_baseline(rooms, sel_entropy=first_wins)
    assert b == e2b_bestofn.random_baseline(rooms, sel_entropy=first_wins, tied=[[0, 1], [0, 1]])


def test_e2b_default_layouts_path(tmp_path):
    import shutil

    shutil.copy(SCORES, tmp_path / "scores.jsonl")
    shutil.copy(LAYOUTS, tmp_path / "layouts.jsonl")
    table = e2b_bestofn.run(tmp_path / "scores.jsonl", tmp_path / "out")
    assert (tmp_path / "out" / "e2b_bestofn.csv").exists()
    assert len(table) == 6


def test_bootstrap_ci_brackets_mean():
    x = np.array([1.0, 2.0, 3.0, 10.0])
    m, lo, hi = bootstrap_ci(x)
    assert lo <= m <= hi
    assert m == 4.0
    m, lo, hi = bootstrap_ci([5.0])
    assert m == lo == hi == 5.0
    assert all(math.isnan(v) for v in bootstrap_ci([]))


def test_spearman_matches_known_values():
    x = [1, 2, 3, 4, 5]
    assert spearman(x, [1, 2, 3, 4, 5]) == 1.0
    assert spearman(x, [5, 4, 3, 2, 1]) == -1.0
    assert abs(spearman(x, [1, 3, 2, 5, 4])) == 0.8
    assert math.isnan(spearman(x, [1, 1, 1, 1, 1]))  # constant column -> undefined


def test_shannon_entropy():
    assert shannon_entropy([1, 1]) == 1.0
    assert shannon_entropy([4]) == 0.0
    assert abs(shannon_entropy([1, 1, 1, 1]) - 2.0) < 1e-12


def test_model_colors_covers_twelve_arms_stably_and_distinctly():
    """The pooled corpus has nine arms; an eight-slot palette raised SystemExit."""
    from envelope_shift.analysis._common import SERIES, model_colors

    arms = [f"arm{i:02d}" for i in range(12)]
    colors = model_colors(arms)
    assert len(set(colors.values())) == 12
    assert model_colors(arms) == colors
    assert list(colors.values())[:8] == SERIES[:8] == [
        "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
    with pytest.raises(SystemExit):
        model_colors([f"a{i}" for i in range(len(SERIES) + 1)])

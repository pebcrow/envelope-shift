"""A3 calibration: richer inventories, STRICT parameter set, the
--params flag on `score`, and analysis/calibration.py over a hand-authored
T0 fixture (tests/fixtures/layouts_calib.jsonl).

The fixture stands in for a real sweep's layouts.jsonl: four T0 rooms, each
with a sensible hand-placed layout, in the exact record shape cmd_sweep
writes. Rescoring it under DEFAULT and STRICT is the whole calibration path
minus the model call.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from envelope_shift.analysis import calibration
from envelope_shift.inventory import Group, Item, inventory_for
from envelope_shift.metrics import coverage
from envelope_shift.params import DEFAULT, PARAM_SETS, STRICT, Params
from envelope_shift.run import main, scores_path
from envelope_shift.schema import RoomType

FIXTURE = Path(__file__).parent / "fixtures" / "layouts_calib.jsonl"
FIXTURE_IDS = {"t0_kitchen_12x14", "t0_pbath_10x12", "t0_pbed_14x16", "t0_sbath_5x9"}


# --- 1. inventories -------------------------------------------------------

def test_kitchen_and_bath_inventories_are_production_sized():
    assert inventory_for(RoomType.KITCHEN).n >= 9
    assert inventory_for(RoomType.PRIMARY_BATH).n >= 6
    assert inventory_for(RoomType.SECONDARY_BATH).n >= 6


def test_alternative_groups_preserved():
    def groups(rt):
        return {g.name: set(g.alternatives) for g in inventory_for(rt).lines if isinstance(g, Group)}

    k = groups(RoomType.KITCHEN)
    assert {"range", "cooktop"} <= k["cooking"]
    pb = groups(RoomType.PRIMARY_BATH)
    assert {"bathtub", "shower_stall"} <= pb["bathing"]
    sb = groups(RoomType.SECONDARY_BATH)
    assert {"bathtub", "shower_stall", "tub_shower"} <= sb["bathing"]


def test_kitchen_counts_are_realistic():
    items = {i.type: i.count for i in inventory_for(RoomType.KITCHEN).lines if isinstance(i, Item)}
    assert items["base_cabinet"] >= 6
    assert items["upper_cabinet"] >= 5


def test_thin_kitchen_no_longer_scores_full_coverage():
    """The old six-line kitchen (3 base, 2 upper, sink, fridge, range, dw) is
    now well short of a production kitchen."""
    from envelope_shift.envelopes import load_all
    from envelope_shift.schema import Entity

    env = {e.id: e for e in load_all()}["t0_kitchen_12x14"]
    thin = [Entity(type=t, wall=1, t=0.1 * i, offset=0, width=2, depth=2, height=3)
            for i, t in enumerate(["base_cabinet"] * 3 + ["upper_cabinet"] * 2
                                  + ["sink", "refrigerator", "range", "dishwasher"])]
    assert coverage(env, thin).score < 80


# --- 2. params ------------------------------------------------------------

def test_strict_registered_and_tighter_than_default():
    assert PARAM_SETS == {"default": DEFAULT, "strict": STRICT}
    assert DEFAULT == Params()
    assert STRICT.nav_reach_ft == 0.5 < DEFAULT.nav_reach_ft
    assert STRICT.nav_body_radius_ft == 1.0 > DEFAULT.nav_body_radius_ft
    assert STRICT.coverage_extraneous_penalty == 1.0 > DEFAULT.coverage_extraneous_penalty
    # Published constant is not a tuning knob.
    assert STRICT.nav_detour_weight == DEFAULT.nav_detour_weight == 0.35
    assert {f for f, _, _ in DEFAULT.diff(STRICT)} == {
        "coverage_extraneous_penalty", "nav_reach_ft", "nav_body_radius_ft",
    }


def test_params_command_prints_every_field_for_both_sets(capsys):
    for name, params in PARAM_SETS.items():
        main(["params", "--params", name])
        out = capsys.readouterr().out
        for field, value in params.as_table():
            assert f"| `{field}` | {value} |" in out, (name, field)


# --- 3. score --params ----------------------------------------------------

def test_scores_path_never_collides():
    p = Path("/x/layouts.jsonl")
    assert scores_path(p, "default") == Path("/x/scores.jsonl")
    assert scores_path(p, "strict") == Path("/x/scores_strict.jsonl")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_score_command_writes_separate_files_for_default_and_strict(tmp_path, capsys):
    layouts = tmp_path / "layouts.jsonl"
    layouts.write_text(FIXTURE.read_text())

    main(["score", str(layouts)])
    main(["score", str(layouts), "--params", "strict"])

    default_rows = _read_jsonl(tmp_path / "scores.jsonl")
    strict_rows = _read_jsonl(tmp_path / "scores_strict.jsonl")
    assert {r["envelope_id"] for r in default_rows} == FIXTURE_IDS
    assert {r["envelope_id"] for r in strict_rows} == FIXTURE_IDS
    assert all(r["params"] == "default" for r in default_rows)
    assert all(r["params"] == "strict" for r in strict_rows)
    assert all(r["tier"] == "T0" for r in default_rows)

    by_id = lambda rows: {r["envelope_id"]: r for r in rows}  # noqa: E731
    d, s = by_id(default_rows), by_id(strict_rows)
    for eid in FIXTURE_IDS:
        assert s[eid]["coverage"] <= d[eid]["coverage"], eid
        assert s[eid]["navigability"] <= d[eid]["navigability"], eid
        # Overlap/clearance is not touched by STRICT.
        assert s[eid]["overlap_clearance"] == pytest.approx(d[eid]["overlap_clearance"]), eid


# --- 4. analysis/calibration.py ------------------------------------------

def test_fixture_records_have_sweep_shape():
    rows = _read_jsonl(FIXTURE)
    assert {r["envelope_id"] for r in rows} == FIXTURE_IDS
    for r in rows:
        assert set(r) >= {"envelope_id", "model", "entities", "parse_ok", "raw", "error",
                          "sample", "seconds", "include_inventory"}
        assert r["parse_ok"] and len(r["entities"]) >= 4


def test_calibration_rescores_fixture_under_both_sets():
    pairs = calibration.load_layouts(FIXTURE)
    assert {e.id for e, _ in pairs} == FIXTURE_IDS
    rescored = calibration.rescore(pairs)
    assert set(rescored) == {"default", "strict"}
    table = calibration.summarize(rescored)
    by_name = {row["params"]: row for row in table}
    assert by_name["default"]["n"] == by_name["strict"]["n"] == 4
    assert by_name["strict"]["coverage"] <= by_name["default"]["coverage"]
    assert by_name["strict"]["navigability"] <= by_name["default"]["navigability"]
    # The fixture is built so STRICT actually bites, not just ties.
    assert by_name["strict"]["navigability"] < by_name["default"]["navigability"] - 5
    assert by_name["strict"]["coverage"] < by_name["default"]["coverage"]
    assert by_name[calibration.PUBLISHED_LABEL]["coverage"] == 76.4
    assert by_name[calibration.PUBLISHED_LABEL]["navigability"] == 45.7
    assert by_name[calibration.PUBLISHED_LABEL]["overlap_clearance"] == 7.4


def test_calibration_main_prints_table_with_both_rows(capsys):
    calibration.main([str(FIXTURE), "--per-room"])
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert any(l.startswith("| default | 4 |") for l in lines), out
    assert any(l.startswith("| strict | 4 |") for l in lines), out
    assert any(l.startswith(f"| {calibration.PUBLISHED_LABEL} |") and "76.4 | 45.7 | 7.4" in l for l in lines), out
    assert "nav_reach_ft 1.0 -> 0.5" in out
    for eid in FIXTURE_IDS:
        assert f"| {eid} |" in out


def test_calibration_main_fails_cleanly_on_empty_tier(tmp_path):
    empty = tmp_path / "layouts.jsonl"
    empty.write_text("")
    with pytest.raises(SystemExit):
        calibration.main([str(empty)])


# --- 6. off-scale navigability is counted, never silently pooled ---
#
# navigability.py once floored a zero straight-line distance at a tiny epsilon, so a
# door whose interior point landed on a target footprint scored ~-1e7 instead of
# somewhere in the metric's declared -35..100, and one such room in the STRICT sweep
# dragged its arm mean AND the all-arms mean off scale. That clamp has been removed;
# the per-pair detour is now capped by nav_detour_cap in params.py. Bounding the
# score is the metric's job; making any contaminated mean legible is the summary table's.


def test_out_of_range_counts_only_scores_outside_the_declared_band():
    lo, hi = calibration.NAV_RANGE
    rows = [{"navigability": v} for v in (lo, hi, 0.0, hi + 0.5, lo - 0.5, -1e7)]
    assert calibration.out_of_range(rows) == 3
    assert calibration.out_of_range([]) == 0


def test_arm_summary_carries_the_count_and_pooling_never_drops_it():
    arms = calibration.load_arms(FIXTURE)
    assert arms, "fixture produced no arms"
    table = calibration.arm_summary(arms)

    scored = [r for r in table if r["params"] != calibration.PUBLISHED_LABEL]
    assert scored and all("off_scale" in r for r in scored)

    # The all-arms row is a pool of the per-arm rows, so its count must be their
    # sum — that is what stops a contaminated mean from reading as a clean one.
    for name in {r["params"] for r in scored}:
        rows = [r for r in scored if r["params"] == name]
        pooled = next(r for r in rows if r["arm"] == calibration.ALL_ARMS)
        per_arm = [r for r in rows if r["arm"] != calibration.ALL_ARMS]
        assert pooled["off_scale"] == sum(r["off_scale"] for r in per_arm)
        assert pooled["n"] == sum(r["n"] for r in per_arm)


def test_arm_summary_markdown_has_an_off_scale_column():
    table = calibration.arm_summary(calibration.load_arms(FIXTURE))
    md = calibration.format_arm_summary(table).splitlines()
    assert md[0].endswith("| off_scale |"), md[0]
    # The published-band row has no rows behind it, so it carries no count.
    published = [l for l in md if l.startswith(f"| {calibration.PUBLISHED_LABEL} |")]
    assert len(published) == 1 and published[0].endswith("|  |"), published

"""The T5 coverage drop is an identity against the scorer, not a reading (claim v10).

Two halves. The first builds small layouts and checks the arithmetic: parts sum to the gap on
an unclamped row, a clamped row is counted rather than averaged, a synonym map cannot absolve a
type into nothing. The second reads the COMMITTED tables and synonym map and checks they say
what the module says they say; the last test regenerates them from the canonical results/ tree
and is host-bound, so it skips where that tree is absent.
"""

from __future__ import annotations

import csv
import json
import os
import tomllib
from pathlib import Path

import pytest

from envelope_shift.analysis import t5_decomposition as t5
from envelope_shift.envelopes import load_all
from envelope_shift.inventory import Item, inventory_for

REPO = Path(__file__).resolve().parents[1]
# Host-bound: results/ is gitignored, so it exists only in the canonical checkout.
RESULTS = Path(os.environ.get("ENVELOPE_SHIFT_RESULTS", REPO / "results"))
ENVS = {e.id: e for e in load_all()}
SYNONYMS = t5.load_synonyms()
NURSERY = ENVS["t5_pbed_nursery"]      # declared: crib, changing_table, glider
GARAGE = ENVS["t5_garage_workshop"]


def _ent(type_: str) -> dict:
    return {"type": type_, "wall": 0, "t": 0.5, "offset": 0.0, "width": 2.0, "depth": 2.0, "height": 3.0}


def _layout(env, extras=(), drop=None, model="arm", **row) -> dict:
    """Every inventory line satisfied (except `drop`), plus the extra types."""
    ents = []
    for line in inventory_for(env.room_type).lines:
        if (line.type if isinstance(line, Item) else line.name) == drop:
            continue
        if isinstance(line, Item):
            ents += [_ent(line.type)] * line.count
        else:
            ents.append(_ent(line.alternatives[0]))
    ents += [_ent(t) for t in extras]
    return {"envelope_id": env.id, "model": model, "parse_ok": True, "entities": ents, **row}


def _decompose(env, row, synonyms=SYNONYMS):
    return t5.decompose_row(env, row, synonyms)


# --- 1. the arithmetic ---------------------------------------------------------

def test_parts_sum_exactly_to_the_gap_on_an_unclamped_row():
    n = inventory_for(NURSERY.room_type).n
    dropped = inventory_for(NURSERY.room_type).lines[0]
    drop = dropped.type if isinstance(dropped, Item) else dropped.name
    # one line missing, two declared types, one synonym of a declared type, one unrelated type
    row = _layout(NURSERY, extras=["crib", "changing_table", "glider_chair", "zebra_rug"], drop=drop)
    d = _decompose(NURSERY, row)
    assert not d.clamped
    assert d.declared == ("changing_table", "crib")
    assert d.synonym == (("glider_chair", "glider"),)
    assert d.other == ("zebra_rug",)
    assert d.parts["extraneous_declared"] == pytest.approx(2 * 50.0 / n)
    assert d.parts["extraneous_synonym"] == pytest.approx(50.0 / n)
    assert d.parts["extraneous_other"] == pytest.approx(50.0 / n)
    assert d.parts["missing"] == pytest.approx(100.0 / n)          # one whole line of N
    assert d.coverage + sum(d.parts.values()) == pytest.approx(100.0)


def test_a_row_the_floor_clamp_took_is_counted_not_averaged():
    clean = _layout(NURSERY, extras=["crib"])
    swamped = _layout(GARAGE, extras=[f"junk_{i}" for i in range(20)])
    d = _decompose(GARAGE, swamped)
    assert d.clamped and d.coverage == 0.0
    # the clamp cut the penalty short: the identity is NOT true of this row, which is why it is left out
    assert d.coverage + sum(d.parts.values()) > 100.0 + 1e-6
    rows = [_decompose(NURSERY, clean), d]
    [arm] = t5.summarize(rows)
    assert (arm["n_rows"], arm["n_clamped"]) == (1, 1)
    assert arm["coverage_mean"] == pytest.approx(_decompose(NURSERY, clean).coverage)


def test_the_means_satisfy_the_identity_per_arm():
    rows = [_decompose(NURSERY, _layout(NURSERY, extras=x)) for x in (["crib"], ["glider_chair", "zebra_rug"], [])]
    [arm] = t5.summarize(rows)
    assert arm["coverage_mean"] + sum(arm[p] for p in t5.PARTS) == pytest.approx(100.0)


def test_only_parsed_inventory_supplied_t5_rows_are_analysed():
    ok = _layout(NURSERY, extras=["crib"])
    t0 = _layout(ENVS["t0_kitchen_12x14"])
    rows = t5.t5_rows([ok, t0,
                       {**ok, "model": "arm-noinv"},
                       {**ok, "model": "bare", "include_inventory": False},
                       {**ok, "parse_ok": False}], SYNONYMS)
    assert [(r.envelope_id, r.model) for r in rows] == [("t5_pbed_nursery", "arm")]


def test_common_rooms_compare_every_arm_on_the_same_rooms_and_name_what_each_lost():
    """An arm's mean must not be carried by a room another arm lacks.

    Arm a has both rooms; b's garage is clamped; c's garage did not parse. Over all rows a's
    mean includes a garage no other arm contributes to, so only the nursery is common.
    """
    nursery = _layout(NURSERY, extras=["crib"])
    garage = _layout(GARAGE)
    swamped = _layout(GARAGE, extras=[f"junk_{i}" for i in range(20)])
    raw = [{**nursery, "model": "a"}, {**garage, "model": "a"},
           {**nursery, "model": "b"}, {**swamped, "model": "b"},
           {**nursery, "model": "c"}, {**garage, "model": "c", "parse_ok": False}]
    rows = t5.t5_rows(raw, SYNONYMS)
    assert t5.parse_failures(raw) == {("t5_garage_workshop", "c")}
    common = {r["model"]: r for r in t5.common_rooms(rows, t5.parse_failures(raw))}
    only_nursery = _decompose(NURSERY, nursery).coverage
    for m in "abc":
        assert common[m]["n_rooms"] == 1
        assert common[m]["coverage_mean"] == pytest.approx(only_nursery)
        assert common[m]["coverage_mean"] + sum(common[m][p] for p in t5.PARTS) == pytest.approx(100.0)
    assert common["a"]["excluded"] == ""
    assert common["b"]["excluded"] == "t5_garage_workshop:clamped"
    assert common["c"]["excluded"] == "t5_garage_workshop:parse_failure"
    # and summarize() over all rows is what the common set corrects: a's mean there has the garage in it
    [a] = [r for r in t5.summarize(rows) if r["model"] == "a"]
    assert a["n_rows"] == 2 and a["coverage_mean"] != pytest.approx(only_nursery)


def test_by_envelope_rows_name_each_type_and_its_bucket():
    rows = [_decompose(NURSERY, _layout(NURSERY, extras=["crib", "glider_chair", "zebra_rug"]))]
    [r] = t5.by_envelope(rows)
    assert (r["extraneous_declared"], r["extraneous_synonym"], r["extraneous_other"]) == \
        ("crib", "glider_chair>glider", "zebra_rug")


# --- 2. the synonym map cannot absolve a type into nothing -----------------------

@pytest.mark.parametrize("mapping", [{"zebra_rug": "zebra_rug"},           # to itself
                                     {"zebra_rug": "toaster"},             # outside the room
                                     {"crib": "toaster"}])                 # even a declared type
def test_an_unjustified_mapping_is_refused(mapping):
    row = _layout(NURSERY, extras=["crib", "zebra_rug"])
    with pytest.raises(ValueError, match="neither a declared extraneous type nor an inventory type"):
        _decompose(NURSERY, row, mapping)


def test_a_mapping_to_an_inventory_type_lands_in_synonym():
    d = _decompose(NURSERY, _layout(NURSERY, extras=["zebra_rug"]), {"zebra_rug": "dresser"})
    assert d.synonym == (("zebra_rug", "dresser"),) and d.other == ()


# --- 3. the committed synonym map and tables ------------------------------------

def _t5_named_types() -> set[str]:
    out: set[str] = set()
    for e in ENVS.values():
        if e.atypicality.tier.value == "T5":
            out |= set(e.atypicality.declared_extraneous or []) | inventory_for(e.room_type).expected_types()
    return out


def test_the_committed_map_maps_nothing_to_itself_or_outside_the_t5_rooms():
    raw = tomllib.loads((REPO / "analysis" / "synonyms.toml").read_text())
    assert set(raw) == {"synonyms"} and raw["synonyms"]
    named = _t5_named_types()
    for k, v in raw["synonyms"].items():
        assert k != v, k
        assert v in named, (k, v)
        # a synonym is an emitted spelling, so it is not itself a name the scorer already accepts
        assert k not in named, k


def test_the_committed_tables_have_provenance_that_regenerates_both():
    prov = json.loads((REPO / "report/provenance.json").read_text())
    a, b = prov["report/data/t5_decomposition.csv"], prov["report/data/t5_by_envelope.csv"]
    c = prov["report/data/t5_common_rooms.csv"]
    assert a["command"] == b["command"] == c["command"] and c["output"] == "t5_common_rooms.csv"
    assert a["command"][:3] == ["python", "-m", "envelope_shift.analysis.t5_decomposition"]
    assert a["inputs"] == ["results/all/layouts.jsonl"]


def _read(name: str) -> list[dict]:
    with (REPO / "report/data" / name).open() as f:
        return list(csv.DictReader(f))


def test_the_committed_decomposition_is_an_identity_with_the_columns_the_report_cites():
    with (REPO / "report/data/t5_decomposition.csv").open() as f:
        assert next(csv.reader(f)) == t5.FIELDS
    rows = _read("t5_decomposition.csv")
    assert rows
    for r in rows:
        total = float(r["coverage_mean"]) + sum(float(r[p]) for p in t5.PARTS)
        assert total == pytest.approx(100.0, abs=5e-4), r["model"]     # four cells rounded to 4 dp
        assert int(r["n_rows"]) > 0 and int(r["n_clamped"]) >= 0
        assert not r["model"].endswith("-noinv")


def test_the_committed_common_room_table_compares_every_arm_on_one_room_set():
    with (REPO / "report/data/t5_common_rooms.csv").open() as f:
        assert next(csv.reader(f)) == t5.COMMON_FIELDS
    rows = _read("t5_common_rooms.csv")
    full = {r["model"]: r for r in _read("t5_decomposition.csv")}
    assert {r["model"] for r in rows} == set(full)
    assert len({r["n_rooms"] for r in rows}) == 1
    for r in rows:
        total = float(r["coverage_mean"]) + sum(float(r[p]) for p in t5.PARTS)
        assert total == pytest.approx(100.0, abs=5e-4), r["model"]
        # an arm that lost a room names it; an arm that lost none keeps more rows in the full table
        lost = [x for x in r["excluded"].split(";") if x]
        assert all(x.split(":")[1] in ("clamped", "parse_failure") for x in lost)
        assert int(full[r["model"]]["n_rows"]) + int(full[r["model"]]["n_clamped"]) \
            + sum(x.endswith(":parse_failure") for x in lost) >= int(r["n_rooms"])


def test_every_committed_bucket_assignment_is_what_the_map_and_the_envelope_say():
    for r in _read("t5_by_envelope.csv"):
        env = ENVS[r["envelope_id"]]
        declared = set(env.atypicality.declared_extraneous or [])
        split = lambda s: [x for x in s.split(";") if x]        # noqa: E731
        assert set(split(r["extraneous_declared"])) <= declared
        for pair in split(r["extraneous_synonym"]):
            emitted, named = pair.split(">")
            assert SYNONYMS[emitted] == named and emitted not in declared
        for t in split(r["extraneous_other"]):
            assert t not in declared and t not in SYNONYMS


needs_results = pytest.mark.skipif(
    not (RESULTS / "all" / "layouts.jsonl").is_file(),
    reason=(
        "results/ holds the raw model outputs of the original sweeps; it is gitignored and not "
        "distributed, so this check runs only where that tree exists (set ENVELOPE_SHIFT_RESULTS)"
    ),
)


@needs_results
def test_all_three_tables_regenerate_byte_identically_from_the_pooled_corpus(tmp_path):
    t5.run(RESULTS / "all" / "layouts.jsonl", tmp_path)
    for name in ("t5_decomposition.csv", "t5_by_envelope.csv", "t5_common_rooms.csv"):
        assert (tmp_path / name).read_bytes() == (REPO / "report/data" / name).read_bytes(), name

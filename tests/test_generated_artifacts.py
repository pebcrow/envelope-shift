"""A generated artifact must match the code that generates it.

Two files in this repository are produced by code, committed or relied on, and
were checked by nothing:

  src/envelope_shift/envelopes/data/**.json   the published description of the
      independent variable. `load_all()` reads the Python factories, so the JSON
      is a dump for readers. If it drifts, the stimulus a reader sees is not the
      stimulus the experiment ran.

  results/**/scores.jsonl                     every published E1/E3/E4 number.
      Gitignored, so no provenance entry and no c4 coverage. On 2026-09-20 every
      one of them was stale: 238 of 240 rows in results/all, 149 in navigability,
      three landed metric fixes that had never reached a published number. c4 was
      green the whole time, because it regenerated the tables FROM the stale
      scores and compared them to tables built from the same stale scores.

Both failures are the epic's founding defect one level out: a check that passes
because the thing it reads and the thing it compares against are equally wrong.
"""

from __future__ import annotations

import json
from pathlib import Path

from envelope_shift.analysis.regenerate import stale_scores
from envelope_shift.envelopes import DATA_DIR, dump, load_all
from envelope_shift.run import score_rows, serialize_scores

REPO = Path(__file__).resolve().parents[1]


# --- 1. the committed envelope dump matches the factories ------------------

def test_committed_envelope_dump_matches_the_factories(tmp_path: Path):
    """Every committed envelope JSON is what dump() writes today.

    Drift from EITHER side fails it, and both were demonstrated rather than
    assumed: mutating a factory (t5_kitchen_laundry 14x18 -> 14x19)
    and mutating the committed JSON (wall_thickness 0.375 -> 0.5) each name
    T5/t5_kitchen_laundry.json.

    A caution carried over from the bead that asked for this test, because it is
    still true of every OTHER test here: mutating the JSON is not a way to probe
    them. `load_all()` reads the Python factories, so the JSON changes no
    behaviour at all and the rest of the suite stays green — which reads like a
    weak suite and is not. This test is the one exception, because committed-
    equals-generated is precisely what it asserts.
    """
    dump(tmp_path)
    committed = {p.relative_to(DATA_DIR): p for p in DATA_DIR.rglob("*.json")}
    fresh = {p.relative_to(tmp_path): p for p in tmp_path.rglob("*.json")}

    assert set(committed) == set(fresh), (
        f"dump() no longer writes the same set of files: "
        f"only committed {sorted(map(str, set(committed) - set(fresh)))}, "
        f"only fresh {sorted(map(str, set(fresh) - set(committed)))}"
    )
    drifted = [str(rel) for rel in sorted(committed)
               if committed[rel].read_bytes() != fresh[rel].read_bytes()]
    assert not drifted, (
        f"{len(drifted)} committed envelope dump(s) no longer match the factories: "
        f"{drifted[:5]} — regenerate with `python -m envelope_shift.run dump-envelopes`"
    )


def test_the_dump_covers_every_envelope():
    assert len({p for p in DATA_DIR.rglob("*.json")}) == len(load_all())


# --- 2. stale_scores() discriminates ---------------------------------------

def _mini_corpus(root: Path) -> Path:
    """A one-row results tree: a real envelope, an empty layout, scored honestly."""
    env = load_all()[0]
    root.mkdir(parents=True, exist_ok=True)
    layouts = root / "layouts.jsonl"
    layouts.write_text(json.dumps({
        "envelope_id": env.id, "model": "fixture", "sample": 0,
        "parse_ok": True, "entities": [], "raw": "[]", "error": None,
        "include_inventory": True, "seconds": 0.0,
    }) + "\n")
    (root / "scores.jsonl").write_text(serialize_scores(score_rows(layouts)))
    return layouts


def test_stale_scores_is_silent_when_scores_are_current(tmp_path: Path):
    _mini_corpus(tmp_path / "mini")
    assert stale_scores(tmp_path) == []


def test_stale_scores_names_a_scores_file_its_layouts_no_longer_produce(tmp_path: Path):
    """The failure this exists for: the metric moved and nobody rescored.

    Simulated from the other side — the scores file holds a value the live
    metric does not produce — because that is indistinguishable from a stale
    file and needs no monkeypatching of the metric to demonstrate.
    """
    layouts = _mini_corpus(tmp_path / "mini")
    scores = layouts.with_name("scores.jsonl")
    rows = [json.loads(line) for line in scores.read_text().splitlines()]
    rows[0]["coverage"] = (rows[0].get("coverage") or 0.0) + 1.0
    scores.write_text(serialize_scores(rows))

    assert stale_scores(tmp_path) == [scores]


def test_stale_scores_ignores_a_corpus_that_has_never_been_scored(tmp_path: Path):
    """No scores.jsonl is not a stale scores.jsonl — a raw sweep is allowed to
    sit unscored without failing the regeneration gate."""
    layouts = _mini_corpus(tmp_path / "mini")
    layouts.with_name("scores.jsonl").unlink()
    assert stale_scores(tmp_path) == []

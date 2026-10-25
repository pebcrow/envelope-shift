"""The pooled corpus is built by a committed step from a committed manifest.

results/all was assembled by hand, off-repo: nothing said which sweeps it held or in what
order, so "open the raw row" held only because nobody re-pooled. `envelope-shift pool` makes it
a function of analysis/corpora.toml.

The pool is CONCATENATION. Two tests prove that on the real corpus, before the manifest's
contents changed: pooling the ORIGINAL inputs (the top-level local sweep, cloud, cloud_noinv,
glm, glm_noinv) reproduces the results/all those inputs made, byte for byte, and dropping any
one of them does not. The reference is a sha256 of that results/all, recorded here because the
canonical results/ tree is gitignored and host-bound, and the real results/all is now rebuilt
from the new manifest. Those two tests skip on a host without the canonical tree.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from envelope_shift import pool, run

REPO = Path(__file__).resolve().parents[1]
# results/ is gitignored, so it exists only in the author's checkout; a fresh clone has none
# and these tests skip there. Never a host path in a tracked file.
RESULTS = Path(os.environ.get("ENVELOPE_SHIFT_RESULTS", REPO / "results"))

# The sweeps the hand-built results/all held, in its order ("." is results/ itself: the
# top-level local sweep), as a committed manifest the real command is run on.
ORIGINAL_MANIFEST = REPO / "tests" / "fixtures" / "corpora_original.toml"
ORIGINAL = pool.load_manifest(ORIGINAL_MANIFEST)["all"]

# sha256 of the results/all those inputs made, read off the file on 2026-09-21 before it was
# rebuilt: 236 layouts, 240 scores (236 + the 4 transport failures), 4 transport failures.
ORIGINAL_SHA256 = {
    "layouts.jsonl": "c3353b8d292dd44f64192f2ccadec9cd3e31e9f7c325aa001acfc611ec85daec",
    "scores.jsonl": "ab31b6cf9ccdcca43589940426f55ce662bc0050263bd99b933c90cd4a369df4",
    "transport_failures.jsonl": "96fcb000e526a370acb13a678d83f54173383d5537359841be0bcc248e0e5927",
}

needs_results = pytest.mark.skipif(
    not (RESULTS / "cloud" / "layouts.jsonl").is_file(),
    reason=(
        "results/ holds the raw model outputs of the original sweeps; it is gitignored and not "
        "distributed, so this check runs only where that tree exists (set ENVELOPE_SHIFT_RESULTS)"
    ),
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _n(text: str) -> int:
    return len(text.splitlines())


def _pool_through_the_command(tmp_path: Path, manifest: Path, score: bool) -> dict[str, str]:
    """Run `envelope-shift pool` on the real results/, writing into tmp_path, and read it back."""
    argv = ["pool", "--results", str(RESULTS), "--out", str(tmp_path), "--manifest", str(manifest)]
    run.main(argv if score else argv + ["--no-score"])
    return {p.name: p.read_text() for p in sorted((tmp_path / "all").iterdir())}


@needs_results
def test_pooling_the_original_inputs_reproduces_the_hand_built_results_all_byte_for_byte(tmp_path):
    files = _pool_through_the_command(tmp_path, ORIGINAL_MANIFEST, score=True)
    assert {name: _sha(text) for name, text in files.items()} == ORIGINAL_SHA256


@needs_results
@pytest.mark.parametrize("dropped", ORIGINAL)
def test_a_manifest_that_drops_a_directory_no_longer_reproduces_it(tmp_path, dropped):
    """The reproduction is not vacuous: each input's rows are in the pool, so a manifest that
    leaves one out loses exactly its rows and its bytes differ from the original's."""
    kept = [d for d in ORIGINAL if d != dropped]
    manifest = tmp_path / "dropped.toml"
    manifest.write_text("[pools.all]\nsweeps = %s\n" % json.dumps(kept))
    files = _pool_through_the_command(tmp_path / "out", manifest, score=False)
    lost = _n((RESULTS / dropped / "layouts.jsonl").read_text())
    assert _n(files["layouts.jsonl"]) == 236 - lost
    assert _sha(files["layouts.jsonl"]) != ORIGINAL_SHA256["layouts.jsonl"]


def test_concatenation_keeps_manifest_order_and_bytes(tmp_path):
    for name, rows in {"a": "a1\na2\n", "b": "b1\n"}.items():
        (tmp_path / name).mkdir()
        (tmp_path / name / "layouts.jsonl").write_text(rows)
    (tmp_path / "b" / "transport_failures.jsonl").write_text("b-fail\n")
    assert pool.concatenate(tmp_path, ["b", "a"]) == {
        "layouts.jsonl": "b1\na1\na2\n", "transport_failures.jsonl": "b-fail\n"}
    assert pool.concatenate(tmp_path, ["a", "b"])["layouts.jsonl"] == "a1\na2\nb1\n"


def test_a_listed_sweep_with_no_layouts_is_an_error_not_an_empty_contribution(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "layouts.jsonl").write_text("a1\n")
    with pytest.raises(FileNotFoundError, match="'gone' has no layouts.jsonl"):
        pool.concatenate(tmp_path, ["a", "gone"])


def test_a_file_without_a_final_newline_is_refused_rather_than_fusing_two_rows(tmp_path):
    for name, rows in {"a": "a1", "b": "b1\n"}.items():
        (tmp_path / name).mkdir()
        (tmp_path / name / "layouts.jsonl").write_text(rows)
    with pytest.raises(ValueError, match="does not end in a newline"):
        pool.concatenate(tmp_path, ["a", "b"])


def test_the_committed_manifest_names_only_sweeps_that_exist_and_none_twice():
    pools = pool.load_manifest(REPO / pool.MANIFEST)
    assert "all" in pools
    for name, sweeps in pools.items():
        assert len(set(sweeps)) == len(sweeps), name
        for sweep in sweeps:
            assert not sweep.startswith("/"), f"{name}: {sweep} is not relative to results/"


def test_a_manifest_naming_a_sweep_twice_is_refused(tmp_path):
    m = tmp_path / "corpora.toml"
    m.write_text('[pools.all]\nsweeps = ["a", "a"]\n')
    with pytest.raises(SystemExit, match="names a sweep twice"):
        pool.load_manifest(m)

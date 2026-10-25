"""report/provenance.json: one entry per committed derived table, and the
entry point that re-runs them all.

Claim c4 of the report contract is host-bound — it regenerates from the
canonical results/ tree, which is gitignored and so absent from every clone
and lane worktree. These tests cover the half that is NOT host-bound: the
manifest's shape, its coverage of what is actually committed, and byte
identity for the two derived tables that read no results/ at all (the
parameter disclosure tables and the hand-authored E2 pair table).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from envelope_shift.analysis import regenerate
from envelope_shift.experiments.e2_pairs import score_pairs, write_coverage_gap, write_table
from envelope_shift.params import DEFAULT, PARAM_SETS, STRICT
from envelope_shift.run import params_table

REPO = Path(__file__).resolve().parents[1]
PROV = json.loads((REPO / "report/provenance.json").read_text())

# Mirrors the contract's own globs: a csv or md anywhere under report/data/, and
# a csv or md directly in report/figures/, is a derived table and needs an entry.
DERIVED_GLOBS = ("report/data/**/*.csv", "report/data/**/*.md",
                 "report/figures/*.csv", "report/figures/*.md")


def committed_derived() -> list[str]:
    return sorted({str(p.relative_to(REPO)) for g in DERIVED_GLOBS for p in REPO.glob(g)})


# --- 1. the manifest covers what is committed, and vice versa --------------

def test_every_committed_derived_table_has_an_entry():
    unowned = [rel for rel in committed_derived() if rel not in PROV]
    assert unowned == []


def test_every_entry_names_a_committed_file():
    missing = [rel for rel in PROV if not (REPO / rel).exists()]
    assert missing == []


def test_the_report_tables_the_sections_need_are_all_present():
    """Acceptance 3: E1, E3, E4, E2b, E2, calibration and params, all covered."""
    required = {
        "report/data/e1_degradation.csv",
        "report/data/e3_disagreement.csv",
        "report/data/e4_correlation.csv",
        "report/data/e2b_bestofn.csv",
        "report/data/e2_pairs.csv",
        "report/data/calibration_t0_default.csv",
        "report/data/calibration_t0_strict.csv",
        "report/data/calibration_t0_summary.md",
        "report/data/params_default.md",
        "report/data/params_strict.md",
    }
    assert required <= set(PROV)
    assert required <= set(committed_derived())


# --- 2. every entry is runnable and machine-independent --------------------

@pytest.mark.parametrize("rel", sorted(PROV))
def test_entry_command_is_relocatable(rel):
    entry = PROV[rel]
    cmd = entry["command"]
    assert isinstance(cmd, list) and all(isinstance(a, str) for a in cmd)
    assert cmd[:2] == ["python", "-m"], cmd
    # An absolute path in a command would pin the table to one machine.
    assert not [a for a in cmd if a.startswith("/")], cmd
    # Every command must be told where to write, or it would write into the tree.
    assert any("{out}" in a for a in cmd), cmd
    # {results} is the only other placeholder, and it is always a results/ path.
    assert all(a.startswith("{results}/") for a in cmd if "{results}" in a), cmd


@pytest.mark.parametrize("rel", sorted(PROV))
def test_entry_output_is_the_committed_basename(rel):
    assert PROV[rel]["output"] == Path(rel).name


@pytest.mark.parametrize("rel", sorted(PROV))
def test_declared_inputs_are_results_paths_the_command_reads(rel):
    entry = PROV[rel]
    args = [a[len("{results}/"):] for a in entry["command"] if a.startswith("{results}/")]
    for src in entry["inputs"]:
        assert src.startswith("results/"), (rel, src)
        # A command may name the file, or a directory (or the tree) holding it.
        assert any(src[len("results/"):].startswith(a) if a.endswith("/") or not a
                   else src[len("results/"):] == a for a in args), (rel, src)


#: Rendered image formats whose bytes are not stable across library versions. Matplotlib does
#: not promise byte-identical PNG output, and Pillow's GIF encoder does not either, so these
#: are checked for existence rather than compared. Every other derived file — every csv and md
#: table the report cites — must reproduce byte for byte, which is claim c4.
UNSTABLE_RENDER_SUFFIXES = (".png", ".gif")


@pytest.mark.parametrize("rel", sorted(PROV))
def test_only_figures_are_exempt_from_byte_identity(rel):
    expected = not rel.endswith(UNSTABLE_RENDER_SUFFIXES)
    assert PROV[rel]["byte_identical"] is expected, rel


def test_every_exempt_entry_is_actually_a_rendered_figure():
    """The exemption is a property of the FORMAT, not an escape hatch. A table that cannot
    reproduce is a c4 failure and must not be silenced by flipping this flag."""
    for rel, entry in PROV.items():
        if not entry["byte_identical"]:
            assert rel.endswith(UNSTABLE_RENDER_SUFFIXES), (
                f"{rel} is exempt from byte-identity but is not a rendered figure")


def test_resolve_binds_the_placeholders_and_the_interpreter():
    argv = regenerate.resolve(
        ["python", "-m", "m", "{results}/all/scores.jsonl", "{out}"],
        Path("/r"), Path("/o"),
    )
    assert argv[0].endswith("python") or "python" in argv[0]
    assert argv[1:] == ["-m", "m", "/r/all/scores.jsonl", "/o"]


def test_commands_sharing_a_run_are_grouped_once():
    """The analysis scripts emit a CSV and a PNG in one pass; regenerating each
    entry separately would run them twice for no gain."""
    groups = regenerate._groups(PROV)
    assert sum(len(rels) for _, rels in groups) == len(PROV)
    assert len(groups) < len(PROV)


# --- 3. byte identity for the entries that read no results/ ----------------

@pytest.mark.parametrize("name", sorted(PARAM_SETS))
def test_params_table_regenerates_byte_identically(name):
    committed = (REPO / f"report/data/params_{name}.md").read_bytes()
    assert params_table(name).encode() == committed


@pytest.mark.parametrize("name", sorted(PARAM_SETS))
def test_params_table_lists_every_field_and_marks_the_strict_ones(name):
    """Acceptance 4 / claim c8: nothing unpublished is used without disclosure."""
    text = (REPO / f"report/data/params_{name}.md").read_text()
    moved = {f for f, _, _ in DEFAULT.diff(STRICT)}
    rows = [ln for ln in text.splitlines() if ln.startswith("| `")]
    assert len(rows) == len(PARAM_SETS[name].as_table())
    for field, value in PARAM_SETS[name].as_table():
        row = next(ln for ln in rows if ln.startswith(f"| `{field}` |"))
        assert f"| `{field}` | {value} |" in row
        assert row.rstrip().endswith("| yes |") is (field in moved), row
    assert moved and all(f"| `{f}` |" in text for f in moved)


def test_e2_pair_table_regenerates_byte_identically(tmp_path):
    write_table(score_pairs(), tmp_path)
    assert (tmp_path / "e2_pairs.csv").read_bytes() == (REPO / "report/data/e2_pairs.csv").read_bytes()


def test_e2_coverage_gap_table_regenerates_byte_identically(tmp_path):
    write_coverage_gap(tmp_path)
    assert (tmp_path / "e2_coverage_gap.csv").read_bytes() == (REPO / "report/data/e2_coverage_gap.csv").read_bytes()

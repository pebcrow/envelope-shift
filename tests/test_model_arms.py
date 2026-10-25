"""report/data/model_arms.csv names what actually ran (claim v7).

The table is derived from the `call_config` on the raw rows, so these tests build a
small results tree and check the derivation, and check the committed report against
the two mechanical rules v7 states: no capability adjective the corpus does not
support, and every model id the table can carry named in the prose.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from envelope_shift.analysis import model_arms

REPO = Path(__file__).resolve().parents[1]


def _row(model: str, reasoning: dict, source: str = "backfilled") -> str:
    cfg = {"backend": "openai", "model": model, "reasoning": reasoning, "source": source}
    return json.dumps({"id": "x", "call_config": cfg}) + "\n"


def _call(envelope: str, model: str, sample: int, arm: str = "a", reasoning: dict | None = None) -> str:
    cfg = {"backend": "openai", "model": arm, "reasoning": reasoning or {}, "source": "backfilled"}
    return json.dumps({"envelope_id": envelope, "model": model, "sample": sample, "call_config": cfg}) + "\n"


def _prov(*dirs: str) -> dict:
    """A provenance mapping in which some other entry reads each `results/<dir>/scores.jsonl`."""
    return {"report/data/x.csv": {"inputs": [f"results/{d}/scores.jsonl" for d in dirs]},
            "report/data/model_arms.csv": {"inputs": ["results/"]}}


def _write(root: Path, name: str, text: str) -> None:
    (root / name).parent.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(text)


def test_one_row_per_distinct_model_reasoning_and_source(tmp_path):
    _write(tmp_path, "all/layouts.jsonl",
           _call("e1", "m", 0) + _call("e2", "m", 0) + _call("e1", "n", 0, "b", {"reasoning_effort": "low"})
           + json.dumps({"envelope_id": "e3", "model": "m", "sample": 0, "call_config": {
               "backend": "openai", "model": "a", "reasoning": {}, "source": "recorded"}}) + "\n")
    _write(tmp_path, "all/transport_failures.jsonl", _call("e4", "m", 0))
    _write(tmp_path, "all/scores.jsonl", _call("e1", "m", 0))
    rows = model_arms.summarize(tmp_path, _prov("all"))
    assert [(r["model"], r["reasoning"], r["source"], r["n_rows"]) for r in rows] == [
        ("a", "{}", "backfilled", 3),
        ("a", "{}", "recorded", 1),
        ("b", '{"reasoning_effort": "low"}', "backfilled", 1),
    ]


def test_a_call_held_in_an_analysed_and_an_unanalysed_directory_is_counted_once(tmp_path):
    """results/all pools the per-sweep directories, and nothing cites the per-sweep ones.

    The whole-tree count gives 3 here and the (envelope, arm, sample) dedup gives 2 —
    the unanalysed `cloud` holds a call `all` does not — so this fails against both.
    """
    _write(tmp_path, "all/layouts.jsonl", _call("e1", "m", 0))
    _write(tmp_path, "cloud/layouts.jsonl", _call("e1", "m", 0) + _call("e2", "m", 0))
    _write(tmp_path, "layouts.jsonl", _call("e1", "m", 0))
    (row,) = model_arms.summarize(tmp_path, _prov("all"))
    assert row["n_rows"] == 1


def test_two_distinct_calls_sharing_a_key_in_two_analysed_directories_are_two_calls(tmp_path):
    """An E1 sample and an E2b sample of the same room share (envelope_id, model, sample).

    Deduplicating on that key gives 1 here, so this fails against the 360-count version.
    """
    _write(tmp_path, "all/layouts.jsonl", _call("e1", "m", 0))
    _write(tmp_path, "e2b_cloud/layouts.jsonl", _call("e1", "m", 0))
    (row,) = model_arms.summarize(tmp_path, _prov("all", "e2b_cloud"))
    assert row["n_rows"] == 2


def test_a_directory_no_provenance_entry_reads_is_not_counted(tmp_path):
    _write(tmp_path, "all/layouts.jsonl", _call("e1", "m", 0))
    _write(tmp_path, "smoke/layouts.jsonl", _call("e9", "m", 0) + _call("e9", "n", 0, "b"))
    assert [(r["model"], r["n_rows"]) for r in model_arms.summarize(tmp_path, _prov("all"))] == [("a", 1)]


def test_the_corpus_set_follows_provenance_not_the_generator(tmp_path):
    (tmp_path / "e2b.v2").mkdir()
    prov = _prov("all")
    prov["report/data/y.csv"] = {"inputs": ["results/e2b.v2/", "results/layouts.jsonl"]}
    assert model_arms.analysed_corpora(prov, tmp_path) == ["all", "e2b.v2"]


def test_the_tables_own_inputs_do_not_name_a_corpus(tmp_path):
    prov = {"report/data/model_arms.csv": {"inputs": ["results/smoke/layouts.jsonl"]}}
    assert model_arms.analysed_corpora(prov, tmp_path) == []


def test_scores_are_not_raw_calls(tmp_path):
    _write(tmp_path, "all/layouts.jsonl", _call("e1", "m", 0))
    _write(tmp_path, "all/scores.jsonl", _call("e1", "m", 0))
    (row,) = model_arms.summarize(tmp_path, _prov("all"))
    assert row["n_rows"] == 1


def test_the_same_envelope_and_arm_at_another_sample_is_a_second_call(tmp_path):
    _write(tmp_path, "all/layouts.jsonl", _call("e1", "m", 0) + _call("e1", "m", 1) + _call("e1", "other", 0))
    (row,) = model_arms.summarize(tmp_path, _prov("all"))
    assert row["n_rows"] == 3


def test_rows_without_a_call_config_are_not_invented_an_arm(tmp_path):
    _write(tmp_path, "all/layouts.jsonl", json.dumps({"id": "old"}) + "\n" + _row("a", {}))
    assert [r["model"] for r in model_arms.summarize(tmp_path, _prov("all"))] == ["a"]


def test_the_empty_reasoning_configuration_is_written_out_not_left_blank(tmp_path):
    _write(tmp_path, "all/layouts.jsonl", _row("a", {}))
    model_arms.run(tmp_path, tmp_path / "out", _prov("all"))
    (row,) = csv.DictReader((tmp_path / "out" / "model_arms.csv").open())
    assert row["reasoning"] == "{}"


def _sampled(model: str, sampling: dict | None, observed: str | None = None, envelope: str = "e1", sample: int = 0) -> str:
    cfg = {"backend": "openai", "model": model, "reasoning": {}, "source": "recorded"}
    if sampling is not None:
        cfg["sampling"] = sampling
    if observed:
        cfg["observed"] = {"model": observed, "system_fingerprint": None}
    return json.dumps({"envelope_id": envelope, "model": "arm", "sample": sample, "call_config": cfg}) + "\n"


def test_a_model_run_under_two_sampling_regimes_is_one_row_that_shows_both(tmp_path):
    """One row per (model, reasoning, source, backend) is the frozen v7 grain; the regimes are
    visible in the row's `sampling` cell, with their counts, and n_rows still counts every call."""
    _write(tmp_path, "all/layouts.jsonl", _sampled("m", {"temperature": 0.2}, envelope="e1") + _sampled("m", {"temperature": 0.2}, envelope="e2"))
    _write(tmp_path, "e2b_default/layouts.jsonl", _sampled("m", {}))
    (row,) = model_arms.summarize(tmp_path, _prov("all", "e2b_default"))
    assert row["n_rows"] == 3
    assert row["sampling"] == '{"temperature": 0.2} x2 | {} x1'


def test_a_single_sampling_regime_stands_bare_and_an_unrecorded_one_is_named(tmp_path):
    _write(tmp_path, "all/layouts.jsonl", _sampled("m", {"temperature": 0.2}) + _sampled("n", None))
    rows = {r["model"]: r for r in model_arms.summarize(tmp_path, _prov("all"))}
    assert rows["m"]["sampling"] == '{"temperature": 0.2}'
    assert rows["n"]["sampling"] == "unrecorded"


def test_the_model_that_answered_is_named_beside_the_one_asked_for(tmp_path):
    _write(tmp_path, "all/layouts.jsonl", _sampled("deepseek-v4-flash-proxy", {}, observed="deepseek-flash") + _sampled("q", {}))
    rows = {r["model"]: r for r in model_arms.summarize(tmp_path, _prov("all"))}
    assert rows["deepseek-v4-flash-proxy"]["observed_model"] == "deepseek-flash"
    assert rows["q"]["observed_model"] == ""


def test_a_claude_cli_rows_answering_model_is_read_from_its_own_result_event(tmp_path):
    cli = {"events": [{"type": "system", "subtype": "init"},
                      {"type": "result", "modelUsage": {"claude-opus-5": {"inputTokens": 1}}}]}
    row = {"envelope_id": "e1", "model": "opus", "sample": 0, "cli": cli,
           "call_config": {"backend": "claude_cli", "model": "claude-opus-5",
                           "reasoning": {"effort": "medium"}, "sampling": {}, "source": "recorded"}}
    _write(tmp_path, "all/layouts.jsonl", json.dumps(row) + "\n")
    (out,) = model_arms.summarize(tmp_path, _prov("all"))
    assert (out["observed_model"], out["sampling"]) == ("claude-opus-5", "{}")


def test_the_committed_provenance_declares_the_raw_files_of_the_corpora_the_others_read():
    prov = json.loads((REPO / "report/provenance.json").read_text())
    corpora = model_arms.analysed_corpora(prov, REPO / "results")
    declared = prov["report/data/model_arms.csv"]["inputs"]
    assert corpora, "no analysed corpus"
    assert all(Path(d).parts[1] in corpora and Path(d).suffix == ".jsonl" for d in declared)
    assert not [d for d in declared if Path(d).name == "scores.jsonl"]
    assert {Path(d).parts[1] for d in declared} == set(corpora)


def test_the_committed_report_names_every_committed_model_and_uses_frontier_only_for_higharc():
    committed = list(csv.DictReader((REPO / "report/data/model_arms.csv").open()))
    assert committed, "model_arms.csv is empty"
    prose = {p.name: p.read_text() for p in (REPO / "report").glob("*.md")}
    blob = "\n".join(prose.values())
    for row in committed:
        assert row["model"] in blob, row["model"]
    row_t = re.compile(r"^\|\s*\**Higharc's best frontier text LLM \(Claude Opus 4\.6\)\**\s*\|")
    hits = [(n, line) for n, t in prose.items() for line in t.splitlines()
            if re.search(r"(?i)(?<![0-9A-Za-z_])frontier(?![0-9A-Za-z_])", line)
            and not row_t.match(line) and not line.startswith("Higharc writes:")]
    assert hits == []

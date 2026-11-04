"""The 5.5 replication: the same harness, two newer Claude models, raw data committed.

    uv run python -m envelope_shift.analysis.replication            # check: regenerate, compare
    uv run python -m envelope_shift.analysis.replication --write    # refresh report/data/replication/
    uv run python -m envelope_shift.analysis.replication --build OUT  # write everything into OUT
    uv run python -m envelope_shift.analysis.replication ingest SWEEP_ROOT   # one-off, see below

Unlike the original sweeps, whose raw output under results/ is host-bound and not distributed,
the replication's raw rows are committed under `replication/raw/`. Every table in
`report/data/replication/` therefore regenerates on a fresh clone, from tracked files alone,
and `tests/test_replication.py` checks that it does, byte for byte, on every push.

The pipeline is the original one, unchanged:

1. `replication/corpora.toml` names which raw sweep directories form each pool, exactly as
   `analysis/corpora.toml` does for the original corpus; `envelope-shift pool` concatenates
   and scores them under the CURRENT metrics (navigability included, after the doorway fix).
2. The same analysis modules the report's sections 3 to 7 use write their tables.

`ingest` is how the raw rows got into the repo. A sweep writes the Claude Code CLI's full
stream-json events onto every row; those carry session and message ids, host paths and
account rate-limit state, none of which says anything about the layout. `ingest` keeps, per
row, everything the sweep wrote except `cli.events`, and from the events only what bears on
the condition the row was produced under (the init event's model, tool, MCP, skill and plugin
lists and key source; each assistant message's model, content block types and usage; the
result event's status, usage, per-model usage and cost). Thinking text is never present: the
CLI returns it empty with an opaque signature, and the signature is dropped.
"""

from __future__ import annotations

import argparse
import filecmp
import json
import sys
import tempfile
from pathlib import Path

from .. import pool

REPO = Path(__file__).resolve().parents[3]
RAW = REPO / "replication" / "raw"
MANIFEST = REPO / "replication" / "corpora.toml"
OUT = REPO / "report" / "data" / "replication"
FIGURES = REPO / "report" / "figures" / "replication"
TIERS = ["T0", "T1", "T2", "T3", "T4", "T5"]

# Init-event keys that describe the condition; everything else in that event is host state.
_INIT_KEYS = ("type", "subtype", "model", "tools", "mcp_servers", "slash_commands", "skills",
              "plugins", "apiKeySource", "claude_code_version")
_RESULT_KEYS = ("type", "subtype", "is_error", "num_turns", "duration_ms", "stop_reason",
                "usage", "modelUsage", "total_cost_usd", "result")


def sanitize_events(events: list[dict]) -> list[dict]:
    """The condition-bearing part of a CLI event stream; ids, paths and account state dropped."""
    kept = []
    for e in events:
        kind = e.get("type")
        if kind == "system" and e.get("subtype") == "init":
            kept.append({k: e[k] for k in _INIT_KEYS if k in e})
        elif kind == "assistant":
            m = e.get("message") or {}
            kept.append({"type": "assistant", "message": {
                "model": m.get("model"),
                "content_types": [b.get("type") for b in m.get("content") or []],
                "stop_reason": m.get("stop_reason"),
                "usage": m.get("usage"),
            }})
        elif kind == "result":
            kept.append({k: e[k] for k in _RESULT_KEYS if k in e})
    return kept


def sanitize_row(row: dict) -> dict:
    row = dict(row)
    if isinstance(row.get("cli"), dict):
        row["cli"] = {"argv": row["cli"].get("argv"), "events": sanitize_events(row["cli"].get("events") or [])}
    return row


def ingest(sweep_root: Path, raw: Path = RAW) -> list[Path]:
    """Copy each `<sweep>/<part>/<file>.jsonl` under sweep_root into `raw/<sweep>/<file>.jsonl`,
    sanitized, parts concatenated in a stable order (tiers T0..T5, else by name)."""
    written = []
    for sweep in sorted(p for p in Path(sweep_root).iterdir() if p.is_dir()):
        parts = sorted((p for p in sweep.iterdir() if p.is_dir()),
                       key=lambda p: (TIERS.index(p.name) if p.name in TIERS else 99, p.name))
        for fname in pool.RAW:
            rows = []
            for part in parts:
                f = part / fname
                if f.is_file():
                    rows += [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
            if not rows:
                continue
            dest = raw / sweep.name / fname
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text("".join(json.dumps(sanitize_row(r)) + "\n" for r in rows))
            written.append(dest)
    return written


def build(out_dir: Path, raw: Path = RAW, manifest: Path = MANIFEST) -> list[Path]:
    """Pool and score the committed raw rows, then run every analysis into out_dir."""
    from . import (calibration, e1_degradation, e2b_bestofn, e3_disagreement, e5_brief_coverage, model_arms,
                   t5_decomposition)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        results = Path(tmp)
        for name, sweeps in pool.load_manifest(manifest).items():
            pool.write(raw, results, name, sweeps)
        al, e2b = results / "all", results / "e2b_default"
        e1_degradation.main([str(al / "scores.jsonl"), str(out_dir)])
        t5_decomposition.main([str(al / "layouts.jsonl"), str(out_dir)])
        calibration.main([str(al / "layouts.jsonl"), "--out-dir", str(out_dir)])
        e3_disagreement.main([str(al / "scores.jsonl"), str(out_dir)])
        e2b_bestofn.main([str(e2b / "scores.jsonl"), str(out_dir), "--layouts", str(e2b / "layouts.jsonl")])
        e5_brief_coverage.main(["sweep", str(al / "layouts.jsonl"), str(out_dir)])
        e5_brief_coverage.main(["bestofn", str(e2b / "layouts.jsonl"), str(out_dir)])
        prov = {"replication": {"inputs": ["results/all/layouts.jsonl", "results/e2b_default/layouts.jsonl"]}}
        model_arms.run(results, out_dir, prov)
    return sorted(out_dir.iterdir())


def check(out: Path = OUT) -> list[str]:
    """Every committed table under out that a fresh build does not reproduce byte for byte."""
    with tempfile.TemporaryDirectory() as tmp:
        build(Path(tmp))
        fresh = {p.name for p in Path(tmp).iterdir() if p.suffix in (".csv", ".md")}
        committed = {p.name for p in Path(out).iterdir() if p.suffix in (".csv", ".md")}
        bad = sorted(committed ^ fresh)
        bad += [n for n in sorted(committed & fresh)
                if not filecmp.cmp(Path(tmp) / n, Path(out) / n, shallow=False)]
    return bad


def write(out: Path = OUT, figures: Path = FIGURES) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        for p in build(Path(tmp)):
            if p.suffix not in (".csv", ".md", ".png"):
                continue
            dest = (figures if p.suffix == ".png" else out) / p.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(p.read_bytes())


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--write", action="store_true", help="refresh the committed tables and figures")
    p.add_argument("--build", metavar="OUT", help="write every table and figure into OUT (provenance.json uses this)")
    sub = p.add_subparsers(dest="cmd")
    i = sub.add_parser("ingest", help="sanitize sweep output into replication/raw/")
    i.add_argument("sweep_root")
    args = p.parse_args(argv)
    if args.cmd == "ingest":
        for path in ingest(Path(args.sweep_root)):
            print(f"wrote {path.relative_to(REPO)}")
        return 0
    if args.build:
        build(Path(args.build))
        return 0
    if args.write:
        write()
        print(f"wrote {OUT.relative_to(REPO)} and {FIGURES.relative_to(REPO)}")
        return 0
    bad = check()
    for name in bad:
        print(f"DIFFERS: {name}", file=sys.stderr)
    print("replication tables reproduce" if not bad else f"{len(bad)} table(s) differ")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

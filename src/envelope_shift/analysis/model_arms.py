"""Which models produced the corpus, and under what reasoning configuration (claim v7).

    uv run python -m envelope_shift.analysis.model_arms results/ out/

Reads `call_config` out of the raw records of the corpora the report analyses and
writes one row per distinct (model, reasoning, source, backend) with the number of
calls that carry it, and, beside it, the sampling regime and the model the provider
says answered. Nothing here comes from models.toml: that file says what a sweep
would send today, and the report's founding defect was describing the models from it
(or from memory) while the corpus said otherwise.

`reasoning` is the recorded object as canonical JSON, so an empty configuration
reads `{}` rather than a blank a reader might take for "unknown". `source` says
whether the record was made at call time (`recorded`) or stamped on afterwards by
`run.py backfill-call-config` (`backfilled`); a backfilled row is the current
declaration applied to an old call, not an observation of it.

`sampling` is the recorded sampling object as canonical JSON: `{"temperature": 0.2}`
for a pinned temperature, `{}` for the provider's own default, `unrecorded` where the
row carries none. `observed_model` is what ANSWERED, as against `model`, which is what
was asked for: `call_config.observed.model` where the provider reports one (DeepSeek
answers as `deepseek-flash` to a request for `deepseek-v4-flash-proxy`), else the one
model the CLI's own stream-json result event names for a `claude_cli` row, else empty.
Where one configuration was run under several regimes or answered by several models the
cell lists each, `value x<calls>`, joined by ` | `; a single value stands bare.

THE ROW GRAIN IS THE FROZEN v7 ORACLE'S, NOT A CHOICE OF THIS FILE. v7 keys the table on
(model, reasoning, source, backend) and rejects a configuration listed twice, so two
sampling regimes of one model (DeepSeek: T=0.2 in E1, provider default in E2b) cannot be
two rows without turning v7 red. They are two entries of the one row's `sampling` cell.

WHICH CORPORA. The results/<dir>/ directories that some OTHER entry of
report/provenance.json reads, derived here and never listed by hand: a re-run that
lands in a new directory changes the count by being cited, not by an edit to this
file. Sweeps nothing cites (`smoke/`, the per-arm directories `results/all` pools)
are not counted. The provenance file is read from `--provenance`, else from
`report/provenance.json` under the working directory, else from this checkout.

WHAT COUNTS. Every row of every raw file (`*.jsonl` but `scores.jsonl`) in those
directories is one call, once. It is not deduplicated on (envelope_id, model,
sample): that key is shared by distinct calls (an E2b sample and an E1 sample of the
same room), and folding on it published 360 for a corpus of 304. The column keeps the
name `n_rows` because the v7 oracle reads it by that name.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ._common import write_csv

CONFIG_KEY = "call_config"
FIELDS = ["model", "reasoning", "source", "backend", "sampling", "observed_model", "n_rows"]
OUTPUT = "model_arms.csv"
PROVENANCE = Path("report/provenance.json")
REPO = Path(__file__).resolve().parents[3]


def analysed_corpora(provenance: dict, results: Path) -> list[str]:
    """The `results/<dir>` corpora that entries other than this table's own read from.

    An input `results/<dir>/<file>` names `<dir>`; a bare `results/<name>` names a corpus
    only when it is a directory here (`results/layouts.jsonl` is a pooled file, not one).
    """
    dirs: set[str] = set()
    for output, entry in provenance.items():
        if Path(output).name == OUTPUT:
            continue
        for src in entry.get("inputs") or []:
            parts = Path(src).parts
            if parts[:1] == ("results",) and len(parts) > 1:
                if len(parts) > 2 or (results / parts[1]).is_dir():
                    dirs.add(parts[1])
    return sorted(dirs)


def raw_files(results: Path, corpora: list[str]) -> list[Path]:
    """Every raw record file (`*.jsonl` but `scores.jsonl`) in each corpus, in a stable order."""
    found = [p for d in corpora for p in (results / d).glob("*.jsonl") if p.name != "scores.jsonl"]
    return sorted(p for p in found if p.is_file())


def observed_model(row: dict) -> str:
    """The model that answered this call, or "" where the row records none."""
    cfg = row.get(CONFIG_KEY) or {}
    if (cfg.get("observed") or {}).get("model"):
        return str(cfg["observed"]["model"])
    events = (row.get("cli") or {}).get("events") or []
    used = {m for e in events if isinstance(e, dict) and e.get("type") == "result"
            for m in (e.get("modelUsage") or {})}
    return next(iter(used)) if len(used) == 1 else ""


def sampling(cfg: dict) -> str:
    if "sampling" not in cfg:
        return "unrecorded"
    return json.dumps(cfg["sampling"], sort_keys=True)


def _cell(counts: dict[str, int]) -> str:
    if len(counts) == 1:
        return next(iter(counts))
    return " | ".join(f"{v} x{n}" for v, n in sorted(counts.items()))


def summarize(results: Path, provenance: dict) -> list[dict]:
    """One row per distinct (model, reasoning, source, backend), with its call count."""
    calls: dict[tuple[str, str, str, str], int] = {}
    regimes: dict[tuple[str, str, str, str], dict[str, dict[str, int]]] = {}
    for path in raw_files(results, analysed_corpora(provenance, results)):
        with path.open() as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                cfg = row.get(CONFIG_KEY) or {}
                if not cfg.get("model"):
                    continue
                key = (cfg["model"], json.dumps(cfg.get("reasoning", {}), sort_keys=True),
                       cfg.get("source") or "", cfg.get("backend") or "")
                calls[key] = calls.get(key, 0) + 1
                seen = regimes.setdefault(key, {"sampling": {}, "observed_model": {}})
                for column, value in (("sampling", sampling(cfg)), ("observed_model", observed_model(row))):
                    seen[column][value] = seen[column].get(value, 0) + 1
    return [dict(zip(FIELDS, (*key, _cell(regimes[key]["sampling"]),
                               _cell(regimes[key]["observed_model"]), n)))
            for key, n in sorted(calls.items())]


def load_provenance(path: Path | None) -> dict:
    path = path or (PROVENANCE if PROVENANCE.is_file() else REPO / PROVENANCE)
    return json.loads(path.read_text())


def run(results: Path, out_dir: Path, provenance: dict) -> list[dict]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = summarize(Path(results), provenance)
    write_csv(out_dir / OUTPUT, FIELDS, rows)
    return rows


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("results", help="canonical results/ directory")
    p.add_argument("out_dir", help="directory for model_arms.csv")
    p.add_argument("--provenance", type=Path, help="provenance.json naming the analysed corpora")
    args = p.parse_args(argv)
    rows = run(Path(args.results), Path(args.out_dir), load_provenance(args.provenance))
    print(f"model arms: {len(rows)} distinct configurations -> {args.out_dir}/model_arms.csv")
    for r in rows:
        print(f"  {r['model']:<26} {r['reasoning']:<38} {r['source']:<11} "
              f"{r['sampling']:<24} {r['observed_model']:<20} {r['n_rows']}")


if __name__ == "__main__":
    main()

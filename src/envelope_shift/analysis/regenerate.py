"""The single entry point that re-runs every report/provenance.json entry.

    uv run python -m envelope_shift.analysis.regenerate --results results
    uv run python -m envelope_shift.analysis.regenerate --results results --write

Claim c4 of the report contract says every committed derived table regenerates
byte-identically from the canonical results/ directory by the command its
provenance entry names. This module is how that is checked (and, with --write,
how the committed tables are refreshed after a new sweep).

Each entry names an argv whose first element is `python`, with two placeholders:

    {results}   the canonical results/ directory (--results)
    {out}       a scratch directory this module creates and deletes

A command is run ONCE even when several entries share it — the analysis scripts
write a CSV and a PNG in the same pass — and each entry is then compared against
its own `output` file in that scratch directory.

PNG entries carry `"byte_identical": false`: matplotlib output is not stable
across versions, so a figure is checked for existence only. Every .csv and .md
entry is compared byte for byte, which is the check c4 itself performs.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROVENANCE = "report/provenance.json"


def load_provenance(repo: Path) -> dict[str, dict]:
    return json.loads((repo / PROVENANCE).read_text())


def resolve(command: list[str], results: Path, out: Path) -> list[str]:
    """argv with the placeholders filled and `python` bound to this interpreter."""
    argv = [a.replace("{results}", str(results)).replace("{out}", str(out)) for a in command]
    if argv and argv[0] == "python":
        argv[0] = sys.executable
    return argv


def _groups(prov: dict[str, dict]) -> list[tuple[tuple[str, ...], list[str]]]:
    """[(command, [relative paths it produces])], in provenance order."""
    order: list[tuple[str, ...]] = []
    by_cmd: dict[tuple[str, ...], list[str]] = {}
    for rel, entry in prov.items():
        key = tuple(entry["command"])
        if key not in by_cmd:
            by_cmd[key] = []
            order.append(key)
        by_cmd[key].append(rel)
    return [(k, by_cmd[k]) for k in order]


def stale_scores(results: Path) -> list[Path]:
    """Every scores.jsonl under `results` that its own layouts no longer produce.

    THE HOLE THIS CLOSES (2026-09-20). Claim c4 says every committed
    derived table regenerates from results/. It does — from `scores.jsonl`, which
    is itself derived, is gitignored, and has NO provenance entry, so nothing
    regenerated or compared it. On 2026-09-20 every scores.jsonl in the canonical
    tree was stale: 238 of 240 rows in results/all alone, 149 of them in
    navigability, three phase-1 metric fixes that had never reached a published
    number. c4 was GREEN throughout, because it recomputed the tables from the
    stale scores and compared them against tables generated from the same stale
    scores. Green in, green out.

    A derived file that feeds the published tables but is checked by nothing is
    the same shape as the defect this whole rebuild exists to refuse, one level
    further out. So: rescore from the raw record and compare bytes.
    """
    from ..run import score_rows, scores_path, serialize_scores

    stale: list[Path] = []
    for layouts in sorted(results.rglob("layouts.jsonl")):
        committed = scores_path(layouts, "default")
        if not committed.is_file():
            continue
        if committed.read_text() != serialize_scores(score_rows(layouts, "default")):
            stale.append(committed)
    return stale


def regenerate(repo: Path, results: Path, write: bool = False) -> list[str]:
    """Re-run every entry. Returns the relative paths that did NOT reproduce."""
    prov = load_provenance(repo)
    bad: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp)
        for i, (command, rels) in enumerate(_groups(prov)):
            out = scratch / f"g{i:02d}"
            out.mkdir()
            argv = resolve(list(command), results, out)
            proc = subprocess.run(argv, cwd=repo, capture_output=True, text=True)
            if proc.returncode != 0:
                print(f"FAIL  {' '.join(command)}\n{proc.stderr.strip()[-2000:]}")
                bad.extend(rels)
                continue
            for rel in rels:
                entry = prov[rel]
                produced = out / entry.get("output", Path(rel).name)
                committed = repo / rel
                if not produced.exists():
                    print(f"FAIL  {rel}: the command produced no {produced.name}")
                    bad.append(rel)
                    continue
                if write:
                    committed.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(produced, committed)
                    print(f"WROTE {rel}")
                    continue
                if not entry.get("byte_identical", True):
                    print(f"SKIP  {rel} (not byte-stable; existence checked)")
                    continue
                if not committed.exists():
                    print(f"FAIL  {rel}: not committed")
                    bad.append(rel)
                elif committed.read_bytes() != produced.read_bytes():
                    print(f"FAIL  {rel}: regenerated bytes differ from the committed file")
                    bad.append(rel)
                else:
                    print(f"OK    {rel}")
    return bad


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="envelope-shift regenerate", description=__doc__.splitlines()[0])
    p.add_argument("--results", default="results", help="canonical results/ directory")
    p.add_argument("--repo", default=str(REPO), help="repository root holding report/provenance.json")
    p.add_argument("--write", action="store_true", help="overwrite the committed tables instead of checking")
    p.add_argument("--skip-score-check", action="store_true",
                   help="do not verify that each scores.jsonl is current with its layouts "
                        "(rescoring the whole tree is slow; skip only when you just did it)")
    args = p.parse_args(argv)

    repo = Path(args.repo).resolve()
    results = Path(args.results).resolve()
    if not results.is_dir():
        print(f"no results directory at {results}", file=sys.stderr)
        return 2
    if not args.skip_score_check:
        stale = stale_scores(results)
        if stale:
            print("STALE SCORES — regenerating from these would publish pre-fix numbers, and "
                  "claim c4 cannot see it (scores.jsonl has no provenance entry):",
                  file=sys.stderr)
            for path in stale:
                print(f"  {path}", file=sys.stderr)
            print("\nrescore first:", file=sys.stderr)
            for path in stale:
                print(f"  python -m envelope_shift.run score "
                      f"{path.with_name('layouts.jsonl')}", file=sys.stderr)
            return 1

    bad = regenerate(repo, results, args.write)
    prov = load_provenance(repo)
    if args.write:
        print(f"\nwrote {len(prov) - len(bad)} of {len(prov)} derived files")
    elif bad:
        print(f"\n{len(bad)} of {len(prov)} did not regenerate identically: {bad}")
    else:
        print(f"\nall {len(prov)} derived files regenerate from {results}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

"""The original sweeps' raw output, published: sanitize it, commit it, and check the report from it.

    uv run python -m envelope_shift.analysis.original sanitize results   # on the host holding results/
    uv run python -m envelope_shift.analysis.original                    # check: rebuild, compare

Until v1.2.0 the raw output behind sections 3 to 7 lived only in a gitignored `results/` tree
on one host, so "every table regenerates from the raw data" could be checked there and nowhere
else. This module closes that gap the way the replication did (see `replication.py`):

`sanitize` copies, from a canonical `results/` tree, exactly the sweeps the report analyses (the
`all` pool of `analysis/corpora.toml`, plus `e2b_default`) into `original/raw/<sweep>/`. It keeps
every field the scorer and the analyses read, reduces each Claude Code CLI event stream to its
condition-bearing part (`replication.sanitize_events`), and refuses to finish if any written line
still matches a leak pattern (a UUID-shaped id, a host path, a mailbox, an API-key prefix or the
internal project name). It never reads or writes anything outside those sweeps.

The default action builds a scratch `results/` tree from `original/raw/` alone (pool, then score
under the current metrics) and runs every `report/provenance.json` entry that reads `results/`
against it, comparing each committed table byte for byte. CI runs it on every push
(`pytest -m original`).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

from .. import pool
from .replication import sanitize_row

REPO = Path(__file__).resolve().parents[3]
RAW = REPO / "original" / "raw"
E2B = "e2b_default"

_LEAKS = re.compile(
    "[0-9a-f]{8}-[0-9a-f]{4}-" + r"[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"  # session / event ids
    + "|/" + r"(?:home|Users|root|tmp)/"                                    # host paths
    + r"|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.(?:com|org|net|io|ai|dev)\b"   # mailboxes
    + "|s" + r"k-[A-Za-z0-9_-]{16,}"                                        # API keys
    + "|peb" + "crow-agent",                                                # internal repo name
    re.I,
)


def sweeps() -> list[str]:
    """The sweep directories the report analyses, in pool order, then E2b."""
    return [*pool.load_manifest(REPO / "analysis" / "corpora.toml")["all"], E2B]


def leaks(text: str) -> list[str]:
    """`line N: <kind of match>` for every line of text matching a leak pattern. The matched
    text itself is not echoed, so a report of leaks does not leak."""
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        m = _LEAKS.search(line)
        if m:
            s = m.group(0)
            kind = ("uuid" if "-" in s and len(s) == 36 else "path" if s.startswith("/")
                    else "mailbox" if "@" in s else "key" if s.lower().startswith("sk-") else "name")
            out.append(f"line {n}: {kind}")
    return out


def sanitize(results: Path, raw: Path = RAW) -> list[Path]:
    """Copy the analysed sweeps from `results` into `raw`, sanitized. Raises on any leak."""
    written, found = [], []
    for sweep in sweeps():
        src = Path(results) / sweep
        if not (src / pool.LAYOUTS).is_file():
            raise FileNotFoundError(f"{src / pool.LAYOUTS} is missing; is {results} the canonical results/ tree?")
        for fname in pool.RAW:
            f = src / fname
            if not f.is_file():
                continue
            rows = [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
            text = "".join(json.dumps(sanitize_row(r)) + "\n" for r in rows)
            dest = raw / sweep / fname
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text)
            written.append(dest)
            found += [f"{dest.relative_to(raw)} {hit}" for hit in leaks(text)]
    if found:
        raise ValueError("possible leaks remain; nothing should be committed until they are resolved:\n  "
                         + "\n  ".join(found))
    return written


def build(out: Path, raw: Path = RAW) -> Path:
    """A scratch results/ tree (all/ and e2b_default/, pooled and scored) from the committed rows."""
    out = Path(out)
    pool.write(raw, out, "all", sweeps()[:-1])
    pool.write(raw, out, E2B, [E2B])
    return out


def reads_results(rel: str, entry: dict) -> bool:
    return any(src.startswith("results/") for src in entry.get("inputs") or [])


def check(raw: Path = RAW) -> list[str]:
    """Every provenance entry that reads results/ and does not reproduce from the committed rows."""
    from .regenerate import regenerate

    with tempfile.TemporaryDirectory() as tmp:
        return regenerate(REPO, build(Path(tmp) / "results", raw), only=reads_results)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("sanitize", help="copy the analysed sweeps from a results/ tree into original/raw/")
    s.add_argument("results")
    args = p.parse_args(argv)
    if args.cmd == "sanitize":
        try:
            paths = sanitize(Path(args.results))
        except (ValueError, FileNotFoundError) as exc:
            print(exc, file=sys.stderr)
            return 1
        for path in paths:
            print(f"wrote {path.relative_to(REPO)}")
        print("no leak pattern found; next: uv run python -m envelope_shift.analysis.original")
        return 0
    bad = check()
    print("every results/ table reproduces from original/raw/" if not bad else f"{len(bad)} differ: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

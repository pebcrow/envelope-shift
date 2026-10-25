"""The failure kind: whether a layout is missing because the model failed or the wire did.

A `Layout` with `parse_ok=False` is missing for one of two reasons that must never
be pooled. A PARSE failure is a model outcome: the reply arrived and was not
schema-valid JSON. A TRANSPORT failure is no observation at all: the call never
returned (a dead server, exhausted retries), so it says nothing about the model.
Counting the second as the first published a dead local server as the peak of the
degradation ladder.

The kind is first-class data on `Layout.failure_kind` and on every score row.
Records written before that carry it only as the `call:` / `parse:` prefix of
`error`; `kind_from_error` recovers it from there and is the one place that rule
lives, so the read path and the backfill cannot disagree.

Transport failures are recorded in `transport_failures.jsonl` beside
`layouts.jsonl`, not in it: `layouts.jsonl` is what models said. The score step
reads both, so a transport failure is counted, never dropped.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

TRANSPORT = "transport"
PARSE = "parse"
FailureKind = Literal["transport", "parse"]

_PREFIXES = {"call:": TRANSPORT, "parse:": PARSE}

TRANSPORT_FILE = "transport_failures.jsonl"


def kind_from_error(error: str | None) -> str | None:
    """The kind an `error` string records, or None if it names neither."""
    for prefix, kind in _PREFIXES.items():
        if (error or "").startswith(prefix):
            return kind
    return None


def transport_path(layouts: Path) -> Path:
    """The sibling file holding the transport failures of a sweep."""
    return layouts.with_name(TRANSPORT_FILE)


def row_key(rec: dict) -> tuple:
    return rec["envelope_id"], rec["model"], rec.get("sample", 0)


def _lines(path: Path) -> list[str]:
    return [ln for ln in path.read_text().splitlines(keepends=True) if ln.strip()] if path.is_file() else []


def read_raw(layouts: Path) -> list[dict]:
    """Every raw record of a sweep: what models said, then what never got asked."""
    return [json.loads(ln) for p in (layouts, transport_path(layouts)) for ln in _lines(p)]


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def backfill_kinds(layouts: Path) -> tuple[int, int]:
    """Give a pre-`failure_kind` layouts.jsonl its kinds, and move transport rows out.

    Deterministic: the kind is read off the `call:` / `parse:` prefix already on
    every failed row, and a failed row with neither is refused, not guessed at.
    Transport rows move to `transport_failures.jsonl` (deduplicated on
    (envelope_id, model, sample), so a re-run changes nothing). Rows that need no
    change are kept byte-for-byte. Returns (rows given a kind, rows moved).
    """
    kept: list[str] = []
    moved: list[dict] = []
    kinded = 0
    for line in _lines(layouts):
        rec = json.loads(line)
        if not rec.get("parse_ok", True):
            kind = kind_from_error(rec.get("error"))
            if kind is None:
                raise ValueError(f"{layouts}: failed row {row_key(rec)} has neither a call: nor a parse: error")
            if rec.get("failure_kind") != kind:
                rec["failure_kind"] = kind
                line = json.dumps(rec) + "\n"
                kinded += 1
            if kind == TRANSPORT:
                moved.append(rec)
                continue
        kept.append(line)
    if moved:
        tpath = transport_path(layouts)
        have = {row_key(json.loads(ln)) for ln in _lines(tpath)}
        fresh = [rec for rec in moved if row_key(rec) not in have]
        with tpath.open("a") as f:
            f.writelines(json.dumps(rec) + "\n" for rec in fresh)
        _atomic_write(layouts, "".join(kept))
    elif kinded:
        _atomic_write(layouts, "".join(kept))
    return kinded, len(moved)


def backfill_scores(layouts: Path) -> int:
    """Carry the kind into every scores*.jsonl beside `layouts`, by the raw-row join key.

    A failed score row is joined to its raw row on (envelope_id, model, sample)
    (now unique) and takes that row's kind; a failed score row with no
    raw row is refused. Returns the number of score rows changed.
    """
    kinds = {}
    for rec in read_raw(layouts):
        if not rec.get("parse_ok", True):
            kinds[row_key(rec)] = rec.get("failure_kind") or kind_from_error(rec.get("error"))
    changed = 0
    for path in sorted(layouts.parent.glob("scores*.jsonl")):
        out: list[str] = []
        dirty = False
        for line in _lines(path):
            row = json.loads(line)
            if not row.get("parse_ok", True) and row.get("failure_kind") is None:
                kind = kinds.get(row_key(row))
                if kind is None:
                    raise ValueError(f"{path}: failed score row {row_key(row)} matches no classified raw row")
                row["failure_kind"] = kind
                line = json.dumps(row) + "\n"
                dirty = True
                changed += 1
            out.append(line)
        if dirty:
            _atomic_write(path, "".join(out))
    return changed

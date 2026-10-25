"""Tracked text carries no personal path, personal mailbox, internal repo name or recorded id.

A guard alongside test_no_host_identifiers, written for the public release: it scans what git
tracks (not the working tree's untracked files) under report/, src/ and tests/ for a home
directory prefix and a personal mailbox domain, the whole tree for one internal repo name, and
the test fixtures for anything shaped like a UUID, which is how a recorded session or event id
would leak in with a captured response.

Each forbidden string is assembled from two parts so this file does not match its own scan.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

_PERSONAL = ("/" + "home/", "@" + "gmail")
_INTERNAL = "pebcrow" + "-agent"
_UUID = re.compile("[0-9a-f]{8}-[0-9a-f]{4}-" + r"[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def _tracked(*roots: str) -> list[Path]:
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z", "--", *roots], check=True, capture_output=True,
    ).stdout
    return [REPO / p for p in out.decode().split("\0") if p]


def _text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
        return None  # binary, or deleted in the working tree


def _hits(paths: list[Path], match) -> list[str]:
    found = []
    for path in paths:
        text = _text(path)
        if text is None:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if match(line):
                found.append(f"{path.relative_to(REPO)}:{n}")
    return found


def test_no_personal_path_or_mailbox_under_report_src_and_tests():
    paths = _tracked("report", "src", "tests")
    assert len(paths) >= 20, f"scanned only {len(paths)} files: the guard is close to vacuous"
    assert _hits(paths, lambda line: any(s in line for s in _PERSONAL)) == []


def test_no_internal_repo_name_anywhere_tracked():
    paths = _tracked()
    assert len(paths) >= 20
    assert _hits(paths, lambda line: _INTERNAL in line) == []


def test_no_uuid_in_test_fixtures():
    paths = _tracked("tests/fixtures")
    assert paths, "no tracked fixtures: the guard is vacuous"
    assert _hits(paths, lambda line: _UUID.search(line) is not None) == []

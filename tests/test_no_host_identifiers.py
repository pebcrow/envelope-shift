"""No tracked file carries a host home path or a personal email address.

This repository's standing invariant is zero such strings reachable from any ref:
it is meant to be published, and they identify the machine and the person it was
built on. On 2026-09-21 a worker's tests/test_pool.py defaulted to a host path; no
check scanned tracked content, and it landed in two commits before review caught
it. The integrate gate runs this suite on the tree it is about to
push, so this test turns the invariant into a refusal instead of a review item.

It scans the final tree only. A leak added and then removed inside one branch
still reaches history; scanning history is a gate-side job, not a unit test's.

The forbidden strings are assembled at runtime so that this file never contains
them literally and does not trip its own scan or the history invariant.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

_HOME = "/" + "home" + "/"
_FORBIDDEN = re.compile(
    re.escape(_HOME) + r"[a-z_][a-z0-9_-]*"  # a host home directory
    + "|"
    + "@" + "(?:g" + "mail|pebcrow)" + r"\.com"  # a personal or company mailbox
)


def _tracked_files(repo: Path) -> list[Path]:
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z"],
        check=True, capture_output=True,
    ).stdout
    return [repo / p for p in out.decode().split("\0") if p]


def leaks(repo: Path) -> list[str]:
    """Every file:line of a tracked file that matches the forbidden pattern."""
    found = []
    for path in _tracked_files(repo):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue  # binary, or deleted in the working tree
        for n, line in enumerate(text.splitlines(), 1):
            m = _FORBIDDEN.search(line)
            if m:
                found.append(f"{path.relative_to(repo)}:{n}: {m.group(0)}")
    return found


def test_no_tracked_file_carries_a_host_path_or_email():
    hits = leaks(REPO)
    assert not hits, "host identifiers in tracked files:\n" + "\n".join(hits)


def test_the_scan_names_a_planted_leak(tmp_path: Path):
    """Positive control: a tracked file with a host path is caught and named."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "clean.py").write_text("RESULTS = 'results/'\n")
    (tmp_path / "leak.py").write_text("x = 1\nRESULTS = '" + _HOME + "someone/results'\n")
    (tmp_path / "mail.md").write_text("contact: someone" + "@" + "g" + "mail.com\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)

    hits = leaks(tmp_path)

    assert [h.split(":")[0] + ":" + h.split(":")[1] for h in hits] == ["leak.py:2", "mail.md:1"]

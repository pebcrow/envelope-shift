"""Ensure local process artifacts cannot be published by accident."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ARTIFACTS = (".pipelined.toml", "OUTCOME.json", "RESULT.md")


def _git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True)


def test_process_artifacts_are_untracked_and_ignored():
    if _git("rev-parse", "--is-inside-work-tree").returncode:
        pytest.skip("not inside a git checkout")

    tracked = set(_git("ls-files").stdout.decode().splitlines())
    forbidden = set(ARTIFACTS) | {p for p in tracked if p.startswith("docs/plans/")}
    assert not tracked & forbidden

    for path in (*ARTIFACTS, "docs/plans/x.md"):
        assert not _git("check-ignore", "--quiet", path).returncode, path

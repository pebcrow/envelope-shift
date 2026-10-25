"""No comment still describes the removed 1e-6 ft navigability clamp.

Navigability once clamped a zero straight-line distance to a tiny epsilon, which
inflated the detour factor by ~1e6. That clamp is gone; the per-pair
detour ceiling is now params.nav_detour_cap. Comments that still describe the old
clamp mislead a reader into looking for code that does not exist.

Each phrase is assembled from two parts so this file does not match its own scan.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

_STALE = ("clamped to " + "1e-6", "clamps a zero " + "straight-line")


def stale_mentions(repo: Path) -> list[str]:
    """Every file:line under src/ and tests/ that carries a stale clamp phrase."""
    found = []
    for root in ("src", "tests"):
        for path in sorted((repo / root).rglob("*")):
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, IsADirectoryError):
                continue  # a directory, or a binary such as a .pyc
            for n, line in enumerate(text.splitlines(), 1):
                if any(p in line for p in _STALE):
                    found.append(f"{path.relative_to(repo)}:{n}")
    return found


def test_no_comment_describes_the_removed_clamp():
    assert stale_mentions(REPO) == []

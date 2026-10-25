"""Offline per-arm summary table from a scores.jsonl file.

    uv run envelope-shift summary results --out report/summary.md
    uv run envelope-shift summary results/scores.jsonl
    uv run envelope-shift summary results --pool all --out report/summary.md
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

METRICS = ["coverage", "navigability", "overlap_clearance", "exp_isovist_area_mean"]


def _is_valid(v) -> bool:
    """Return True when v is a finite numeric value (not bool, not None, not NaN/inf)."""
    if isinstance(v, bool):
        return False
    if not isinstance(v, (int, float)):
        return False
    try:
        return math.isfinite(v)
    except OverflowError:
        return False


def _is_nonfinite_numeric(v) -> bool:
    """Return True when v is a numeric value that is non-finite (NaN, inf, or overflow).

    None, bools, strings return False (not counted as non-finite).
    Integers too large for float (e.g. 10**400) raise OverflowError on math.isfinite,
    so we catch it here.
    """
    if isinstance(v, bool):
        return False
    if not isinstance(v, (int, float)):
        return False
    try:
        return not math.isfinite(v)
    except OverflowError:
        return True


def _mean_cell(rows: list[dict], metric: str) -> str:
    """Arithmetic mean of *metric* over rows with parse_ok and a valid value."""
    vals = [r[metric] for r in rows if r.get("parse_ok") is True and _is_valid(r.get(metric))]
    if not vals:
        return "\u2014 (n=0)"
    return f"{sum(vals) / len(vals):.1f} (n={len(vals)})"


def _resolve_path(results: Path, raw_results: str, pool: str | None) -> Path:
    """Find the scores.jsonl: pool dir, fallback, or exit."""
    if not results.exists():
        msg = f"results path not found: {raw_results}"
        print(msg, file=sys.stderr)
        raise SystemExit(2)
    if results.is_file():
        return results
    # directory: try pool dir first, then fallback
    pool_path = results / pool / "scores.jsonl" if pool else None
    if pool_path and pool_path.is_file():
        return pool_path
    fallback = results / "scores.jsonl"
    if fallback.is_file():
        return fallback
    parts = []
    if pool:
        parts.append(f"{results / pool}/scores.jsonl")
    parts.append(f"{results}/scores.jsonl")
    msg = f"no scores.jsonl under {raw_results} (tried {', '.join(parts)})"
    print(msg, file=sys.stderr)
    raise SystemExit(2)


def read_rows(path: Path) -> tuple[list[dict], int, int]:
    """Read all JSON lines from a scores.jsonl file.

    Returns (rows, malformed_count, nonblank_count).
    Reads as bytes and decodes each line individually so one bad line
    never aborts the run. Blank lines are ignored.
    Uses json.loads (C decoder) which accepts NaN/Infinity by default
    so that non-finite numerics are parsed and counted.
    """
    data = path.read_bytes()
    if data.startswith(b'\xef\xbb\xbf'):
        data = data[3:]
    rows: list[dict] = []
    malformed = 0
    nonblank = 0
    for raw_line in data.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        nonblank += 1
        try:
            obj = json.loads(line.decode("utf-8"))
        except (ValueError, RecursionError):
            malformed += 1
            continue
        if not isinstance(obj, dict):
            malformed += 1
            continue
        rows.append(obj)
    return rows, malformed, nonblank


def build_markdown(
    path: Path,
    rows: list[dict],
    skipped: int,
    *,
    malformed_count: int = 0,
    nonfinite_count: int = 0,
) -> str:
    """Build the markdown summary from parsed rows."""
    # Group by arm (model field), sorted alphabetically
    arms: dict[str, list[dict]] = {}
    for r in rows:
        arm = str(r.get("model") or "(none)")
        arms.setdefault(arm, []).append(r)

    lines = ["# envelope-shift summary", ""]
    lines.append(f"Source: {path} | {len(rows)} rows")
    lines.append("")

    # Table header
    lines.append("| arm | coverage | navigability | overlap_clearance | exp_isovist_area_mean (exploratory, unvalidated) |")
    lines.append("|---|---|---|---|---|")

    for arm in sorted(arms):
        cell_values = [_mean_cell(arms[arm], m) for m in METRICS]
        lines.append(f"| {arm} | {' | '.join(cell_values)} |")

    lines.append("")
    lines.append(
        "Note: exp_isovist_area_mean is exploratory and unvalidated against human preference "
        "(report section 7)."
    )
    if skipped > 0:
        lines.append(
            f"Note: skipped {skipped} ({malformed_count} malformed lines, {nonfinite_count} non-finite values)."
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    import argparse

    p = argparse.ArgumentParser(
        prog="envelope-shift summary",
        description="per-arm summary table from a scores.jsonl file",
    )
    p.add_argument("results", help="results directory or scores.jsonl file")
    p.add_argument("--out", default="report/summary.md", help="output markdown path")
    p.add_argument("--pool", default="all", help="pool name (default: all; falls back to RESULTS/scores.jsonl)")
    args = p.parse_args(argv)

    raw_results = args.results
    path = _resolve_path(Path(args.results), raw_results, args.pool)

    try:
        rows, malformed_count, nonblank_count = read_rows(path)
    except OSError as e:
        msg = f"cannot read results file: {path}: {e}"
        print(msg, file=sys.stderr)
        raise SystemExit(2)

    if nonblank_count == 0:
        msg = f"results file is empty: {path}"
        print(msg, file=sys.stderr)
        raise SystemExit(2)

    # Count non-finite values for the four METRICS across all parsed rows
    nonfinite_count = 0
    for r in rows:
        for m in METRICS:
            v = r.get(m)
            if _is_nonfinite_numeric(v):
                nonfinite_count += 1

    skipped = malformed_count + nonfinite_count

    md = build_markdown(path, rows, skipped, malformed_count=malformed_count, nonfinite_count=nonfinite_count)

    if skipped > 0:
        print(f"skipped {skipped} ({malformed_count} malformed lines, {nonfinite_count} non-finite values)",
              file=sys.stderr)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)
    print(out)


if __name__ == "__main__":
    main()

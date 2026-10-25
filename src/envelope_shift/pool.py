"""Pool sweep directories into the corpus the report analyses.

    uv run envelope-shift pool                       # rebuild results/all from analysis/corpora.toml
    uv run envelope-shift pool --results results --pool all --no-score
    uv run envelope-shift pool --out /tmp/pooled     # read results/, write /tmp/pooled/<pool>/

`analysis/corpora.toml` names, per pool, the sweep directories (relative to results/) whose
raw files are concatenated, in order, into results/<pool>/. The pool is concatenation and
nothing else: a row is copied byte for byte from the sweep that made it, so a pooled row can
never say more than its source did. Scores are then DERIVED from the pooled layouts by the
same `score_rows` `envelope-shift score` uses, so they cannot disagree with them.

Before this existed results/all was assembled by hand, off-repo. Nothing said which sweeps it
held, in which order, or whether a re-pool would give the same file back.
"""

from __future__ import annotations

import argparse
import tempfile
import tomllib
from pathlib import Path

from .failure import TRANSPORT_FILE

LAYOUTS = "layouts.jsonl"
MANIFEST = Path("analysis/corpora.toml")
REPO = Path(__file__).resolve().parents[2]
RAW = (LAYOUTS, TRANSPORT_FILE)


def load_manifest(path: Path) -> dict[str, list[str]]:
    """{pool name: [sweep dir, ...]} from the manifest, refusing an empty or malformed pool."""
    pools = tomllib.loads(Path(path).read_text()).get("pools") or {}
    out: dict[str, list[str]] = {}
    for name, spec in pools.items():
        sweeps = spec.get("sweeps")
        if not isinstance(sweeps, list) or not sweeps or not all(isinstance(s, str) for s in sweeps):
            raise SystemExit(f"{path}: pool {name!r} needs a non-empty `sweeps` list of directory names")
        if len(set(sweeps)) != len(sweeps):
            raise SystemExit(f"{path}: pool {name!r} names a sweep twice; its rows would be counted twice")
        out[name] = list(sweeps)
    return out


def _read(path: Path) -> str:
    return path.read_text() if path.is_file() else ""


def concatenate(results: Path, sweeps: list[str]) -> dict[str, str]:
    """{raw file name: text} — each sweep's file, in manifest order.

    A sweep with no layouts.jsonl is an error, not an empty contribution: a listed directory
    that quietly adds nothing is how a pool loses an arm. transport_failures.jsonl is optional
    (most sweeps have none), and a sweep's file is always a whole number of lines.
    """
    pooled = {name: "" for name in RAW}
    for sweep in sweeps:
        d = Path(results) / sweep
        if not (d / LAYOUTS).is_file():
            raise FileNotFoundError(f"pool sweep {sweep!r} has no {LAYOUTS} under {results}")
        for name in RAW:
            text = _read(d / name)
            if text and not text.endswith("\n"):
                raise ValueError(f"{d / name} does not end in a newline; concatenating would fuse two rows")
            pooled[name] += text
    return pooled


def build(results: Path, sweeps: list[str], score: bool = True) -> dict[str, str]:
    """The three files of results/<name>/, as text. Pure: writes nothing."""
    from .run import score_rows, serialize_scores

    pooled = concatenate(results, sweeps)
    if score:
        # score_rows reads layouts.jsonl and the transport file beside it, so give it a scratch
        # directory holding exactly the pooled bytes rather than a path in results/.
        with tempfile.TemporaryDirectory() as tmp:
            for fname, text in pooled.items():
                (Path(tmp) / fname).write_text(text)
            pooled["scores.jsonl"] = serialize_scores(score_rows(Path(tmp) / LAYOUTS, "default"))
    return pooled


def write(results: Path, out_root: Path, name: str, sweeps: list[str], score: bool = True) -> Path:
    files = build(results, sweeps, score)
    out = Path(out_root) / name
    out.mkdir(parents=True, exist_ok=True)
    for fname, text in files.items():
        (out / fname).write_text(text)
    return out


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="envelope-shift pool", description=__doc__.splitlines()[0])
    p.add_argument("--results", default="results", help="canonical results/ directory")
    p.add_argument("--out", default=None, help="write results/<pool>/ under this directory instead (default: --results)")
    p.add_argument("--manifest", type=Path, default=None,
                   help=f"pool manifest (default: {MANIFEST} under the working directory, else this checkout)")
    p.add_argument("--pool", default=None, help="pool to build (default: every pool in the manifest)")
    p.add_argument("--no-score", action="store_true", help="skip scores.jsonl (it is slow)")
    args = p.parse_args(argv)
    manifest = args.manifest or (MANIFEST if MANIFEST.is_file() else REPO / MANIFEST)
    pools = load_manifest(manifest)
    if args.pool is not None:
        if args.pool not in pools:
            raise SystemExit(f"{manifest} has no pool {args.pool!r}; it has {sorted(pools)}")
        pools = {args.pool: pools[args.pool]}
    for name, sweeps in pools.items():
        out = write(Path(args.results), Path(args.out or args.results), name, sweeps, not args.no_score)
        print(f"pooled {' + '.join(sweeps)} -> {out}")

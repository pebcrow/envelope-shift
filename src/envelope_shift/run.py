"""Sweep models x envelopes, score, write results.

    uv run envelope-shift sweep --models local opus --out results/
    uv run envelope-shift sweep --models local --temperature 0.8 --samples 4 --tier T0 --out results/
    uv run envelope-shift sweep --models opus sonnet --sampling default --samples 16 --out results/ --resume
    uv run envelope-shift score results/layouts.jsonl
    uv run envelope-shift score results/layouts.jsonl --params strict
    uv run envelope-shift pool
    uv run envelope-shift dump-envelopes
    uv run envelope-shift params [--params strict]

Every number in the report comes from a results file this script wrote.
Layouts are persisted raw so scoring can be re-run after a metric change
without re-querying any model.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

from .arm import arm_label, base_model, backfill_layouts
from .envelopes import dump, load_all
from .failure import TRANSPORT, backfill_kinds, backfill_scores, read_raw, row_key, transport_path
from .generate import LOCAL, ModelSpec, generate, load_models
from .metrics import score_all
from .params import DEFAULT, PARAM_SETS, STRICT
from .schema import Envelope, Layout


def parse_model(arg: str, models: dict[str, ModelSpec] | None = None) -> ModelSpec:
    """A name from models.toml, else 'local' | 'anthropic:<model>' | 'openai:<model>[@<base_url>]'."""
    if models is None:
        models = load_models()
    if arg in models:
        return models[arg]
    if arg == "local":
        return LOCAL
    backend, _, rest = arg.partition(":")
    model, _, base_url = rest.partition("@")
    if backend == "anthropic" and model:
        return ModelSpec(name=model, backend="anthropic", model=model, api_key_env="ANTHROPIC_API_KEY")
    if backend == "openai" and model:
        return ModelSpec(name=model, backend="openai", model=model, base_url=base_url or None)
    known = ", ".join(sorted(models)) or "none"
    raise SystemExit(f"unknown model spec {arg!r} (models.toml names: {known})")


def _read_rows(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()] if path.is_file() else []


def _repair_tail(path: Path) -> None:
    """Drop a half-written last line, so the next append cannot fuse onto it.

    A sweep killed mid-write (a usage limit is not the only way to die) leaves a row that
    does not parse; without this the next row would be glued to it and the corpus unreadable.
    Only an UNPARSEABLE tail is dropped: a complete row is never touched.
    """
    if not path.is_file() or not path.stat().st_size:
        return
    lines = path.read_text().splitlines(keepends=True)
    try:
        json.loads(lines[-1])
    except json.JSONDecodeError:
        path.write_text("".join(lines[:-1]))
    else:
        if not lines[-1].endswith("\n"):
            path.write_text("".join(lines) + "\n")


def _resume_state(layouts_path: Path, keys: set[tuple]) -> set[tuple]:
    """The keys of this sweep that already have a response row, and so are skipped.

    A key whose only rows are transport failures is NOT done: it is retried. Its stale
    failure rows are dropped as the retry starts, because the retry's own outcome replaces
    them; leaving them would count a call that later succeeded as a transport failure too
    (n_transport in e1_degradation). Rows for keys outside this sweep are untouched.
    """
    _repair_tail(layouts_path)
    done = {row_key(r) for r in _read_rows(layouts_path)} & keys
    tpath = transport_path(layouts_path)
    if tpath.is_file():
        _repair_tail(tpath)
        kept = [r for r in _read_rows(tpath) if row_key(r) not in keys]
        tpath.write_text("".join(json.dumps(r) + "\n" for r in kept))
    return done


def cmd_sweep(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    envs = load_all()
    if args.tier:
        envs = [e for e in envs if e.atypicality.tier.value in args.tier]
    if args.envelopes:
        envs = [e for e in envs if e.id in args.envelopes]
    models = load_models()
    specs = [parse_model(m, models) for m in args.models]
    if args.temperature is not None and args.sampling:
        raise SystemExit("--temperature and --sampling default contradict each other")
    if args.temperature is not None:
        specs = [replace(spec, temperature=args.temperature) for spec in specs]
    if args.sampling == "default":
        # E2b's definition: N samples at the provider's own sampling, no temperature sent.
        specs = [replace(spec, temperature=None) for spec in specs]
    layouts_path = out / "layouts.jsonl"
    done: set[tuple] = set()
    if args.resume:
        planned = {(env.id, arm_label(spec.name, not args.no_inventory), k)
                   for spec in specs for env in envs for k in range(args.samples)}
        done = _resume_state(layouts_path, planned)
        print(f"resume: {len(done)} of {len(planned)} keys already have a response row", file=sys.stderr)
    with layouts_path.open("a") as f:
        for spec in specs:
            for env in envs:
                for k in range(args.samples):
                    if (env.id, arm_label(spec.name, not args.no_inventory), k) in done:
                        continue
                    t0 = time.time()
                    layout = generate(env, spec, include_inventory=not args.no_inventory)
                    rec = layout.model_dump(mode="json")
                    rec.update(
                        # The arm is part of the raw record's identity: `model` is the same
                        # label the score step writes, so the two files join without a rule.
                        model=arm_label(layout.model, not args.no_inventory),
                        sample=k,
                        seconds=round(time.time() - t0, 2),
                        include_inventory=not args.no_inventory,
                        temperature=spec.temperature,
                        # Claim v6: the condition this row was produced under, recorded at
                        # call time. `temperature` above is the SPEC's value and is a lie on
                        # the anthropic backend, which never sends one; call_config records
                        # what was actually sent, and is what the report must cite.
                        call_config=spec.call_config("recorded"),
                    )
                    if rec.get("cli") is None:
                        del rec["cli"]  # only claude_cli rows carry one; the rest keep their shape
                    # What the provider says answered sits beside what was asked for
                    # (call_config.model stays the requested id). Additive: no response, no block.
                    if (observed := rec.pop("observed", None)) is not None:
                        rec["call_config"]["observed"] = observed
                    if layout.failure_kind == TRANSPORT:
                        # No reply arrived, so this says nothing about the model:
                        # kept beside layouts.jsonl, never in it (see failure.py).
                        with transport_path(layouts_path).open("a") as g:
                            g.write(json.dumps(rec) + "\n")
                    else:
                        f.write(json.dumps(rec) + "\n")
                        f.flush()
                    status = "ok" if layout.parse_ok else f"FAIL {layout.error}"
                    print(f"{spec.name:>24} {env.id:<28} s{k} {status}", file=sys.stderr)
    print(f"wrote {layouts_path}")


def scores_path(layouts: Path, params_name: str) -> Path:
    """scores.jsonl for the default set, scores_<name>.jsonl otherwise, so
    rescoring under another parameter set never overwrites the default run."""
    suffix = "" if params_name == "default" else f"_{params_name}"
    return layouts.with_name(f"scores{suffix}.jsonl")


def score_rows(layouts: Path, params_name: str = "default") -> list[dict]:
    """Score every raw record of a sweep. Pure: reads, returns, writes nothing.

    Split out of `cmd_score` so the same scoring can be re-run WITHOUT
    touching the canonical results/ — which is what lets `analysis.regenerate`
    tell a current scores.jsonl from a stale one. Nothing else derives the report's
    numbers, so this is the one definition of "what the scores should be".
    """
    envs = {e.id: e for e in load_all()}
    return [score_record(rec, envs, params_name) for rec in read_raw(layouts)]


def score_record(rec: dict, envs: dict[str, Envelope], params_name: str = "default") -> dict:
    """The scores.jsonl row for one raw layout record."""
    env: Envelope = envs[rec["envelope_id"]]
    layout = Layout.model_validate({k: rec[k] for k in Layout.model_fields if k in rec})
    include_inventory = rec.get("include_inventory", True)
    row = {
        "envelope_id": env.id,
        "room_type": env.room_type.value,
        "tier": env.atypicality.tier.value,
        # A model prompted without the inventory is a different arm of the
        # experiment; the label is shared with layouts.jsonl (see arm.py).
        "model": arm_label(layout.model, include_inventory),
        "include_inventory": include_inventory,
        "sample": rec.get("sample", 0),
        "parse_ok": layout.parse_ok,
        "failure_kind": layout.failure_kind,
        "n_entities": len(layout.entities),
        "params": params_name,
    }
    if layout.parse_ok:
        row.update(score_all(env, layout.entities, PARAM_SETS[params_name]))
    return row


def serialize_scores(rows: list[dict]) -> str:
    """The exact bytes `score` writes, so a comparison is byte-for-byte."""
    return "".join(json.dumps(row) + "\n" for row in rows)


def cmd_score(args: argparse.Namespace) -> None:
    src = Path(args.layouts)
    params_name = getattr(args, "params", "default")
    dst = scores_path(src, params_name)
    rows = score_rows(src, params_name)
    dst.write_text(serialize_scores(rows))
    print(f"scored {len(rows)} layouts -> {dst}")


def cmd_pool(args: argparse.Namespace) -> None:
    from .pool import main as pool_main

    argv = ["--results", args.results]
    if args.out is not None:
        argv += ["--out", args.out]
    if args.manifest is not None:
        argv += ["--manifest", str(args.manifest)]
    if args.pool is not None:
        argv += ["--pool", args.pool]
    if args.no_score:
        argv.append("--no-score")
    pool_main(argv)


def cmd_backfill_arms(args: argparse.Namespace) -> None:
    for path in map(Path, args.layouts):
        print(f"{path}: {backfill_layouts(path)} rows qualified")


def cmd_backfill_failure_kinds(args: argparse.Namespace) -> None:
    for path in map(Path, args.layouts):
        kinded, moved = backfill_kinds(path)
        scored = backfill_scores(path)
        print(f"{path}: {kinded} rows given a kind, {moved} transport rows moved out, {scored} score rows given a kind")


def row_sampling(rec: dict) -> dict:
    """The sampling a backfilled row can honestly claim, read from the ROW, not models.toml.

    The sweep writes the temperature it used onto the row itself (`--temperature 0.8` rows
    say 0.8). A number is {"temperature": x}; None is {} (none sent). A row with no
    `temperature` field never recorded one, and models.toml describes what a sweep would send
    TODAY, so no numeric temperature is asserted for it: it is marked unrecorded instead.
    """
    if "temperature" not in rec:
        return {"temperature": None, "recorded": False}
    return {} if rec["temperature"] is None else {"temperature": rec["temperature"]}


def cmd_backfill_call_config(args: argparse.Namespace) -> None:
    """Stamp `call_config` onto raw rows written before it existed (claim v6).

    Marked `source: "backfilled"`, never `"recorded"`. These rows were produced before the
    sweep recorded anything, so their configuration can only be reconstructed from
    models.toml — the weaker evidence this claim exists to distinguish from the stronger
    kind. Collapsing the two would defeat the point, so the distinction is in the data and
    the report has to say which arms are which.

    The spec is resolved from the row's own arm label through `arm.base_model`: the arm is
    the prompt condition, not a different model. An arm with no models.toml entry is
    REFUSED rather than guessed at, in the same spirit as failure.py refusing a failed row
    whose kind cannot be recovered. The one field the spec does NOT supply is `sampling`,
    which comes from the row's own temperature (see `row_sampling`).

    Rows that already carry a config, and rows needing no change, are kept byte-for-byte,
    so a re-run is a no-op (the discipline arm.backfill_layouts already follows).
    `--restamp` additionally rewrites the `sampling` of rows whose config is `backfilled`,
    to correct a stamp written before sampling was read from the row. It touches nothing
    else in the config and NEVER a `recorded` row.
    """
    models = load_models()
    for path in map(Path, args.raw):
        if not path.is_file():
            print(f"{path}: not present, skipped")
            continue
        out: list[str] = []
        stamped = restamped = total = 0
        for line in path.read_text().splitlines(keepends=True):
            if line.strip():
                total += 1
                rec = json.loads(line)
                cfg = rec.get("call_config")
                if not cfg:
                    label = str(rec.get("model") or "")
                    name = base_model(label)
                    spec = models.get(name)
                    if spec is None:
                        raise SystemExit(
                            f"{path}: no models.toml entry for arm {label!r} (model "
                            f"{name!r}); refusing to guess what it sent"
                        )
                    rec["call_config"] = {**spec.call_config("backfilled"), "sampling": row_sampling(rec)}
                    line = json.dumps(rec) + ("\n" if line.endswith("\n") else "")
                    stamped += 1
                elif args.restamp and cfg.get("source") == "backfilled" and cfg.get("sampling") != row_sampling(rec):
                    cfg["sampling"] = row_sampling(rec)
                    line = json.dumps(rec) + ("\n" if line.endswith("\n") else "")
                    restamped += 1
            out.append(line)
        if stamped or restamped:
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text("".join(out))
            tmp.replace(path)
        print(f"{path}: {stamped} of {total} rows stamped, {restamped} re-stamped")


# A committed layout file, so `score-layout` works on a fresh clone with no results/ and no model.
SMOKE_LAYOUTS = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "layouts_smoke.jsonl"


def cmd_score_layout(args: argparse.Namespace) -> None:
    """Score ONE raw layout record and print its metrics. Offline: reads, prints, writes nothing."""
    records = read_raw(Path(args.layouts))
    if not 0 <= args.row < len(records):
        sys.exit(f"{args.layouts}: no row {args.row} (it has {len(records)})")
    row = score_record(records[args.row], {e.id: e for e in load_all()}, args.params)
    width = max(len(k) for k in row)
    for k, v in row.items():
        print(f"{k:<{width}}  {round(v, 4) if isinstance(v, float) else v}")


def cmd_dump(_: argparse.Namespace) -> None:
    print(f"wrote {dump()} envelope files")


def cmd_summary(args: argparse.Namespace) -> None:
    from .summary import main as summary_main

    summary_main(["--pool", args.pool, "--out", args.out, args.results])


def params_table(name: str) -> str:
    """The disclosure table for one parameter set, as markdown.

    Every field of params.Params is listed — a value cannot be used anywhere
    without appearing here — and the third column marks the fields STRICT
    changes, so one table answers both "what did you choose" and "what did
    the calibration variant move".
    """
    params = PARAM_SETS[name]
    moved = {f for f, _, _ in DEFAULT.diff(STRICT)}
    lines = ["| parameter | value | differs under STRICT |", "|---|---|---|"]
    for k, v in params.as_table():
        lines.append(f"| `{k}` | {v} | {'yes' if k in moved else ''} |")
    return "\n".join(lines) + "\n"


def cmd_params(args: argparse.Namespace) -> None:
    name = getattr(args, "params", "default")
    table = params_table(name)
    out_dir = getattr(args, "out_dir", None)
    if out_dir:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"params_{name}.md"
        path.write_text(table)
        print(f"wrote {path}")
        return
    print(table, end="")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="envelope-shift")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sweep")
    s.add_argument("--models", nargs="+", required=True)
    s.add_argument("--out", default="results")
    s.add_argument("--tier", nargs="*", help="restrict to tiers, e.g. T0 T5")
    s.add_argument("--envelopes", nargs="*", help="restrict to envelope ids, e.g. t0_office_10x11")
    s.add_argument("--samples", type=int, default=1)
    s.add_argument("--temperature", type=float, default=None, help="override each spec's temperature")
    s.add_argument(
        "--sampling", choices=["default"], default=None,
        help="'default': the provider's own sampling, no temperature sent, row records sampling {}",
    )
    s.add_argument("--no-inventory", action="store_true", help="omit expected inventory from the prompt")
    s.add_argument(
        "--resume", action="store_true",
        help="skip (envelope, arm, sample) keys already in layouts.jsonl; retry those with only transport failures",
    )
    s.set_defaults(fn=cmd_sweep)

    s = sub.add_parser("score")
    s.add_argument("layouts")
    s.add_argument(
        "--params", choices=sorted(PARAM_SETS), default="default",
        help="parameter set; non-default sets write scores_<name>.jsonl",
    )
    s.set_defaults(fn=cmd_score)

    s = sub.add_parser("score-layout", help="offline: score one raw layout record and print its metrics")
    s.add_argument("layouts", nargs="?", default=str(SMOKE_LAYOUTS),
                   help="layouts.jsonl (default: the committed smoke fixture)")
    s.add_argument("--row", type=int, default=0, help="0-based record index (default 0)")
    s.add_argument("--params", choices=sorted(PARAM_SETS), default="default")
    s.set_defaults(fn=cmd_score_layout)

    s = sub.add_parser("backfill-arms", help="qualify model with the arm in old layouts.jsonl files")
    s.add_argument("layouts", nargs="+")
    s.set_defaults(fn=cmd_backfill_arms)

    s = sub.add_parser(
        "backfill-failure-kinds",
        help="give old layouts.jsonl/scores.jsonl their failure kind; move transport failures to transport_failures.jsonl",
    )
    s.add_argument("layouts", nargs="+")
    s.set_defaults(fn=cmd_backfill_failure_kinds)

    s = sub.add_parser(
        "backfill-call-config",
        help="stamp call_config onto raw rows written before it existed (source: backfilled)")
    s.add_argument("raw", nargs="+", help="layouts.jsonl / transport_failures.jsonl paths")
    s.add_argument(
        "--restamp", action="store_true",
        help="also correct the sampling of rows already stamped `backfilled` (never `recorded`)")
    s.set_defaults(fn=cmd_backfill_call_config)

    s = sub.add_parser("pool", help="rebuild results/<pool>/ from analysis/corpora.toml")
    s.add_argument("--results", default="results", help="canonical results/ directory")
    s.add_argument("--out", default=None, help="write results/<pool>/ under this directory instead (default: --results)")
    s.add_argument("--manifest", type=Path, default=None)
    s.add_argument("--pool", default=None, help="pool to build (default: every pool in the manifest)")
    s.add_argument("--no-score", action="store_true", help="skip scores.jsonl (it is slow)")
    s.set_defaults(fn=cmd_pool)

    sub.add_parser("dump-envelopes").set_defaults(fn=cmd_dump)
    s = sub.add_parser("params")
    s.add_argument("--params", choices=sorted(PARAM_SETS), default="default")
    s.add_argument("--out-dir", help="write params_<set>.md here instead of printing")
    s.set_defaults(fn=cmd_params)

    s = sub.add_parser("summary", help="offline: per-arm summary table of the four metrics")
    s.add_argument("results", help="results directory or scores.jsonl file")
    s.add_argument("--out", default="report/summary.md", help="output markdown path")
    s.add_argument("--pool", default="all", help="pool name (default: all; falls back to RESULTS/scores.jsonl)")
    s.set_defaults(fn=cmd_summary)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()

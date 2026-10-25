"""Regenerate tests/fixtures/{layouts,scores}_tiny.jsonl deterministically.

    uv run python -m envelope_shift.analysis.make_tiny_fixture

Two synthetic "models" x six tiers x two rooms, plus samples 1..3 for two T5
rooms so E2b has best-of-N groups. Entities are placed pseudo-randomly from
the room's inventory with a fixed seed; a few rows are parse failures. The
scores file is produced by the real `run.cmd_score`, so its row schema is
whatever the pipeline writes, not a hand copy of it.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import tempfile
from pathlib import Path

from ..envelopes import load_all
from ..inventory import inventory_for
from ..run import cmd_score
from ..schema import Entity, Envelope, Layout

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures"
MODELS = ["synthetic-a", "synthetic-b"]
SEED = 20260908
ROOMS_PER_TIER = 2
T5_EXTRA_SAMPLES = 3
FAIL_EVERY = 7  # every 7th layout is a parse failure


def _entities(env: Envelope, rng: random.Random, n: int) -> list[Entity]:
    types = sorted(inventory_for(env.room_type).expected_types())
    out = []
    for _ in range(n):
        out.append(
            Entity(
                type=rng.choice(types),
                wall=rng.randrange(env.n_walls),
                t=round(rng.uniform(0.1, 0.9), 2),
                offset=0.0,
                width=round(rng.uniform(1.5, 5.0), 1),
                depth=round(rng.uniform(1.5, 3.0), 1),
                height=round(rng.uniform(2.0, 3.0), 1),
            )
        )
    return out


def build_layouts() -> list[dict]:
    rng = random.Random(SEED)
    envs = load_all()
    by_tier: dict[str, list[Envelope]] = {}
    for e in envs:
        by_tier.setdefault(e.atypicality.tier.value, []).append(e)
    chosen = [e for tier in sorted(by_tier) for e in by_tier[tier][:ROOMS_PER_TIER]]

    recs: list[dict] = []
    i = 0
    for model in MODELS:
        for env in chosen:
            n_samples = 1 + (T5_EXTRA_SAMPLES if env.atypicality.tier.value == "T5" else 0)
            for k in range(n_samples):
                i += 1
                if i % FAIL_EVERY == 0:
                    layout = Layout(envelope_id=env.id, model=model, parse_ok=False, failure_kind="parse",
                                    raw="not json", error="parse: synthetic parse failure")
                else:
                    layout = Layout(envelope_id=env.id, model=model,
                                    entities=_entities(env, rng, rng.randint(2, 6)), raw="[...]")
                rec = layout.model_dump(mode="json")
                rec.update(sample=k, seconds=round(rng.uniform(0.5, 3.0), 2), include_inventory=True)
                recs.append(rec)
    return recs


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(FIXTURES))
    args = p.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    recs = build_layouts()
    with tempfile.TemporaryDirectory() as td:
        layouts = Path(td) / "layouts.jsonl"
        layouts.write_text("".join(json.dumps(r) + "\n" for r in recs))
        cmd_score(argparse.Namespace(layouts=str(layouts)))
        shutil.copy(layouts, out / "layouts_tiny.jsonl")
        shutil.copy(layouts.with_name("scores.jsonl"), out / "scores_tiny.jsonl")
    print(f"wrote {len(recs)} rows to {out}/{{layouts,scores}}_tiny.jsonl")


if __name__ == "__main__":
    main()

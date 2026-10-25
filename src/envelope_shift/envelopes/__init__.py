"""The tiered test set.

Envelopes are authored as Python factories so the set is reproducible from
code and every geometric choice is reviewable in a diff. `dump()` writes one
JSON file per room under envelopes/data/<tier>/ for anyone who would rather
read JSON; `load_all()` reads back from the factories, not the JSON, so the
code is the source of truth.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..schema import Envelope, Tier
from . import t0_calibration, t1_proportion, t2_nonconvex, t3_nonorthogonal, t4_vertical, t5_program

_MODULES = [t0_calibration, t1_proportion, t2_nonconvex, t3_nonorthogonal, t4_vertical, t5_program]

DATA_DIR = Path(__file__).parent / "data"


def load_all() -> list[Envelope]:
    out: list[Envelope] = []
    for m in _MODULES:
        out.extend(m.build())
    ids = [e.id for e in out]
    assert len(ids) == len(set(ids)), "duplicate envelope ids"
    return out


def by_tier(tier: Tier) -> list[Envelope]:
    return [e for e in load_all() if e.atypicality.tier == tier]


def dump(root: Path = DATA_DIR) -> int:
    n = 0
    for env in load_all():
        d = root / env.atypicality.tier.value
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{env.id}.json").write_text(json.dumps(env.model_dump(mode="json"), indent=2) + "\n")
        n += 1
    return n

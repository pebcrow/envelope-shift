"""Coverage: Cov = (1/N) * sum[item_score + group_score - extraneous_penalty].

Reimplemented from the published formula. Scored 0..100.

- item_score for an Item line: min(count_present / count_required, 1)
- group_score for a Group line: 1 if any alternative present, else 0
- extraneous_penalty: params.coverage_extraneous_penalty per entity type that
  is neither in the inventory nor tolerated. Counted once per type, not per
  instance, so a model is not punished more for two extra chairs than one.

Because the published formula sums penalties inside the same (1/N) average,
extraneous items subtract from the mean directly. That is the property the
report examines: a valid, desirable element outside the expected inventory
lowers the score exactly as a missing required element would.

Brief-aware coverage (`coverage_brief`, report section 11) is this harness's proposed fix,
not part of the published method. It scores the same formula against an inventory that
the room's brief has amended, in one of two modes:

- "tolerate": the brief's program types are no longer extraneous. Removes the penalty.
- "require":  each program type becomes a required inventory line (count 1). Removes the
              penalty AND makes ignoring the brief cost what omitting a standard line costs.

Where the brief declares no program, both modes return exactly the published score. The
program list is `Atypicality.declared_extraneous`, written by hand per brief and held out
of every prompt; nothing else about the inventory changes (no synonyms, no substitutions).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace

from ..inventory import Inventory, Item, inventory_for
from ..params import DEFAULT, Params
from ..schema import Entity, Envelope


@dataclass(frozen=True)
class CoverageResult:
    score: float
    item_scores: dict[str, float]
    group_scores: dict[str, float]
    extraneous_types: tuple[str, ...]
    missing: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "coverage": self.score,
            "extraneous_types": list(self.extraneous_types),
            "missing": list(self.missing),
        }


BRIEF_MODES = ("tolerate", "require")


def coverage(env: Envelope, entities: list[Entity], params: Params = DEFAULT) -> CoverageResult:
    return _score(inventory_for(env.room_type), entities, params)


def brief_inventory(env: Envelope, mode: str = "require") -> Inventory:
    """The room type's inventory, amended by the envelope's declared program."""
    if mode not in BRIEF_MODES:
        raise ValueError(f"mode must be one of {BRIEF_MODES}, not {mode!r}")
    inv = inventory_for(env.room_type)
    program = [t for t in (env.atypicality.declared_extraneous or []) if t not in inv.expected_types()]
    if not program:
        return inv
    if mode == "tolerate":
        return replace(inv, tolerated=inv.tolerated | frozenset(program))
    return replace(inv, lines=inv.lines + tuple(Item(t) for t in program))


def coverage_brief(env: Envelope, entities: list[Entity], params: Params = DEFAULT,
                   mode: str = "require") -> CoverageResult:
    """Coverage against the brief-amended inventory (see the module docstring)."""
    return _score(brief_inventory(env, mode), entities, params)


def _score(inv: Inventory, entities: list[Entity], params: Params) -> CoverageResult:
    present = Counter(e.type for e in entities)

    item_scores: dict[str, float] = {}
    group_scores: dict[str, float] = {}
    missing: list[str] = []
    total = 0.0

    for line in inv.lines:
        if isinstance(line, Item):
            s = min(present.get(line.type, 0) / line.count, 1.0)
            item_scores[line.type] = s
            if s < 1.0:
                missing.append(line.type)
        else:
            s = 1.0 if any(present.get(a, 0) > 0 for a in line.alternatives) else 0.0
            group_scores[line.name] = s
            if s == 0.0:
                missing.append(line.name)
        total += s

    expected = inv.expected_types()
    extraneous = tuple(sorted(t for t in present if t not in expected))
    total -= params.coverage_extraneous_penalty * len(extraneous)

    score = max(100.0 * total / inv.n, 100.0 * params.coverage_clamp_min)
    return CoverageResult(
        score=min(score, 100.0),
        item_scores=item_scores,
        group_scores=group_scores,
        extraneous_types=extraneous,
        missing=tuple(missing),
    )

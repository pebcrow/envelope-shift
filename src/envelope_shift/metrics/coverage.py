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
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from ..inventory import Group, Item, inventory_for
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


def coverage(env: Envelope, entities: list[Entity], params: Params = DEFAULT) -> CoverageResult:
    inv = inventory_for(env.room_type)
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

"""The arm label: the one place a model name is qualified by how it was prompted.

A model prompted WITHOUT the expected inventory is a different arm of the
experiment from the same model prompted with it. The label that tells them
apart, `<model>-noinv`, is the `model` field of BOTH layouts.jsonl (written by
`run.py sweep`) and scores.jsonl (written by `run.py score`), so a score row
joins to exactly one raw row on (envelope_id, model, sample). Every writer and
reader derives it here; nothing re-derives the suffix on its own.
"""

from __future__ import annotations

import json
from pathlib import Path

NOINV_SUFFIX = "-noinv"


def arm_label(model: str, include_inventory: bool) -> str:
    """`model` for the inventory-supplied arm, `model-noinv` for the withheld one.

    Idempotent, so a layouts.jsonl written before the label moved into the raw
    record (bare model + include_inventory=false) and one written after
    (already suffixed) both resolve to the same label.
    """
    if include_inventory or model.endswith(NOINV_SUFFIX):
        return model
    return f"{model}{NOINV_SUFFIX}"


def base_model(label: str) -> str:
    """The model behind an arm label: the inverse of `arm_label`.

    The arm is the PROMPT condition, not a different model, so `glm-noinv` and `glm`
    are the same models.toml entry. Lives here for the same reason `arm_label` does —
    nothing should re-derive the suffix on its own.
    """
    return label.removesuffix(NOINV_SUFFIX)


def backfill_layouts(path: Path) -> int:
    """Qualify `model` in a layouts.jsonl written before the arm was part of the record.

    The value is recovered, not invented: `include_inventory` was written on every
    row, and the mapping is `arm_label`, the one the score step already applied.
    Rows that need no change are kept byte-for-byte; a re-run changes nothing.
    Returns the number of rows rewritten.
    """
    changed = 0
    out: list[str] = []
    for line in path.read_text().splitlines(keepends=True):
        if line.strip():
            rec = json.loads(line)
            if "include_inventory" not in rec:
                raise ValueError(f"{path}: row without include_inventory, arm not recoverable")
            label = arm_label(rec["model"], rec["include_inventory"])
            if label != rec["model"]:
                rec["model"] = label
                line = json.dumps(rec) + ("\n" if line.endswith("\n") else "")
                changed += 1
        out.append(line)
    if changed:
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text("".join(out))
        tmp.replace(path)
    return changed

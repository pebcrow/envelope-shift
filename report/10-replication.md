# 10. Replication on the 5.5 models

> **Status: CURRENT.** Every figure in this section was scored under the current
> metrics, after the doorway fix, and its raw model output is committed under
> [`replication/raw/`](../replication/raw). Every table below regenerates on a
> fresh clone with `uv run python -m envelope_shift.analysis.replication`, and CI
> checks that it does, byte for byte.

The original study ran five arms: a local open-weights model (`local`, Qwen3
30B-A3B), two proxied cloud models and two Claude models of the previous generation
(`opus`, `sonnet`: Claude Opus 5 and Sonnet 5). Section 5's finding rests on all
five, but the cheap arms did most of the early work, and their raw output never
left the machine it ran on.

In November 2026 the same harness was pointed at the current Claude models,
`claude-opus-5-5` and `claude-sonnet-5-5` (labelled `opus55` and `sonnet55`),
with nothing else changed: the same 48 envelopes and briefs, the same prompt,
the same transport (the Claude Code command line, tools off), effort `medium`,
provider-default sampling, one reply per envelope with and without the
inventory, and 16 samples per E2 room for best-of-N. 
[`report/data/replication/model_arms.csv`](data/replication/model_arms.csv)
records 160 calls per model and that the model which answered every call is the
one requested. Higharc's post names Claude Opus 4.6 as the best general-purpose text
model, so a current Opus is the arm a reader of that post would most want to see.

The question was simple: is section 5 a property of the metric, or of the
particular models that happened to be run? If coverage really penalises the
brief, a stronger model that follows the brief more faithfully should be
penalised the same way, not less.

## 10.1 The T5 finding holds

With the inventory supplied, both 5.5 arms score between 96.875 and 100.0 on
coverage on every tier from T0 to T4
([`e1_degradation.csv`](data/replication/e1_degradation.csv)). At T5 the score
falls, and the decomposition says where the points go
([`t5_common_rooms.csv`](data/replication/t5_common_rooms.csv), the seven rooms
both arms parsed; the original arms' rows are from
[`report/data/t5_common_rooms.csv`](data/t5_common_rooms.csv)):

| arm | rooms | coverage | missing | declared program | synonym | other |
|---|---|---|---|---|---|---|
| opus (Opus 5, original) | 7 | 77.2 | 0.0 | 10.6 | 9.0 | 3.1 |
| **opus55** (Opus 5.5) | 7 | 78.7 | 0.0 | 10.6 | 7.1 | 3.6 |
| sonnet (Sonnet 5, original) | 7 | 84.8 | 0.0 | 10.6 | 4.6 | 0.0 |
| **sonnet55** (Sonnet 5.5) | 7 | 83.4 | 0.0 | 10.6 | 2.4 | 3.6 |

The missing column is 0.0 again. Neither newer model leaves out a single
inventory line on any T5 room; every point of the fall is the extraneous penalty,
and the declared-program part, the penalty on what the brief asked for, is the
same 10.6 for all four Claude arms. The newer models land within two points of
their predecessors.

The rows ([`t5_by_envelope.csv`](data/replication/t5_by_envelope.csv)) are the
same story room by room:

- **The laundry kitchen.** Both place the washer and dryer the brief asks for and
  score 90.0.
- **The nursery.** Both place the crib and changing table and name the glider
  `glider_chair`: 50.0.
- **The aging-in-place bath.** `opus55` places grab bars, `sonnet55` a shower
  bench: 92.8571 each.
- **The work nook.** Both place the built-in desk; `opus55` also writes
  `desk_chair` and adds a wall shelf, 50.0; `sonnet55` scores 66.6667.
- **The workshop garage.** `sonnet55` furnishes it as a workshop, with the table
  saw and dust collector the brief declares and a band saw and drill press besides,
  and scores 0.0000. `opus55`'s reply did not parse (one validation error), and is
  counted as a parse failure, not dropped
  ([`e1_degradation.csv`](data/replication/e1_degradation.csv), T5).

Including the garage, `sonnet55`'s T5 mean is 73.0060 over 8 rooms
([`t5_decomposition.csv`](data/replication/t5_decomposition.csv)). That is the
lowest T5 coverage of any Claude arm in either run, earned by the most complete
workshop.

## 10.2 Selecting on coverage

Best-of-N by coverage over 16 samples per E2 room
([`e2b_bestofn.csv`](data/replication/e2b_bestofn.csv), the `ALL` rows):

| arm | selected entropy | random one-per-room mean | random p05 | share of random draws at or below |
|---|---|---|---|---|
| opus55 | 4.2939 | 4.4027 | 4.2957 | 0.0465 |
| sonnet55 | 4.1043 | 4.2149 | 4.1043 | 0.0755 |

Both newer arms' coverage-selected sets are less varied than a random pick of one
sample per room, the direction section 5.3 found for two of its three arms. The
original Opus arm showed no detectable difference; `opus55` sits at the random
draws' fifth percentile. With random tie-breaking the shares are 0.0390 and
0.0925. This is four rooms and one pool per arm, and these shares are not
p-values: the replication confirms the direction, not a size.

## 10.3 What else the current scoring shows

**Calibration still does not reproduce the published band.** With the inventory
supplied, both arms score 100.0 coverage at T0 and 94.3 and 94.8 navigability
against the published 76.4 and 45.7
([`calibration_t0_summary.md`](data/replication/calibration_t0_summary.md)).
Section 4's restriction stands unchanged: every result is relative. This is the
expected outcome, since the gap was attributed to the harness (its inventory
tables, its clearances, a prompt that hands over the list), not to the models.

**Navigability, now current.** These are the first sweep navigability figures in
the report scored after the doorway fix. Withholding the inventory still drops T0
coverage to 54.2 (`opus55-noinv`) and 42.6 (`sonnet55-noinv`), the section 4
control, while navigability barely moves.

**Metric disagreement recurs.** [`e3_disagreement.csv`](data/replication/e3_disagreement.csv)
flags nine layouts. Two `opus55` garages score 100.0 coverage with navigability
near a third (`t2_garage_notch`, 32.8614; `t3_garage_taper`, 33.3333), the
section 6 pattern: a complete inventory in a room that is barely walkable.

## 10.4 What this does and does not add

It adds a second, independent draw on the section 5 finding from two newer
models, and a corpus anyone can rescore: the original sweeps' raw output is not
distributed, the replication's is. It does not change any section 8 limitation:
the arms are still general-purpose models prompted through a command line, not
Higharc's model; the inventory tables and every unpublished parameter are still
this harness's own; one reply per room is still one reply per room. A model that
improved in every way a user would care about scored the same on the metric,
which is itself the point. The problem section 5 describes is in the reward, and a
better policy does not make it go away. Section 11 tries a fix to the reward
instead.

**Transport note.** The command line used here carries a larger fixed preamble
than the isolated one the original arms ran through; the init event kept on every
committed row shows no tools, MCP servers or skills loaded. The prompt is built by
the same code for the same envelope and arm, and its `prompt_sha256` is on every
row.

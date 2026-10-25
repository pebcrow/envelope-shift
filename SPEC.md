# envelope-shift — working spec

> **Historical.** This is the working spec the project started from, kept for
> the record. Its figures and experiment statuses predate the rebuild, and some
> of its plans were dropped. [`report/`](report/README.md) is authoritative,
> including the [status of results](report/README.md#status-of-results).

Source facts verified 2026-09-06 against the published post
(https://www.higharc.com/blog/ai-layout-at-higharc-tokenizing-buildings, April 2026,
Manuel Rodriguez Ladrón de Guevara): metric formulas, the (e, t, δ, s, ρ) entity
parameterization, 3,500 homes / 75,720 rooms, 50 held-out test rooms, the results
table, and the stated limitations (vertical constraints, MEP, cross-room propagation)
all match the original draft of this spec. The job posting's language ("RL-based
approaches for generative architectural design", "define construction-domain
benchmarks, build ground-truth datasets, establish eval pipelines") is also verified.

## Amendments to the original draft

These change the framing and the experiment list; the repo layout and metric
definitions are otherwise as drafted.

**A1. Frame it as the benchmark the posting asks for, not a test of their claims.**
The posting literally lists "define construction-domain benchmarks ... establish
eval pipelines" as the job. The artifact should read as a sample of that work:
"here is the OOD evaluation you will need when you move from room furnishing to
whole-home generation with RL." Same experiments, but the report's opening
paragraph is about their *next* problem, not their current numbers. The author of
the post is a licensed architect with a PhD in computational design; he knows
coverage is a conformity metric. Telling him so is not the contribution. Building
the harness that measures the consequence is.

**A2. Add E2b: coverage-as-reward, measured rather than argued.**
Draw N samples per T5 envelope from one model at temperature ~0.8. Select best-of-N
by coverage. Compare the selected set to the unselected pool on entity-type
diversity (unique types, entropy) and on the experience axis. This is a one-step
RL-lite loop and it turns "the gradient points at the corpus mean" from a paragraph
into a plot. Cheap: 3 rooms × 16 samples on the local box is free.

**A3. Calibration will not match, and that is a finding.**
First T0 run with the local Qwen3-30B and the inventory in the prompt: coverage 100
on 8/8, navigability ~100, OC 0–19. Published frontier-LLM baseline: 76.4 / 45.7 /
7.4. The gap is driven by unpublished choices: their inventory tables are
evidently richer than ours (a production kitchen has far more than 9 entities),
their targets/clearances stricter, and their prompt may not have handed over the
inventory. Report this as the reproducibility gap it is, sweep the parameters that
close it, and use the *relative* degradation across tiers as the result, not the
absolute numbers.

**A4. Elevation.** The published `s_q` is width/height/depth; wall-hung casework
needs an elevation to be scored fairly. Added `elevation` to Entity; elevated
entities do not block paths and only overlap what they share vertical range with.
Disclosed in the parameter table.

**A5. Author the envelopes as code, not JSON.** Reproducible, diffable, and the
JSON is a dump. Fill each tier to 8 in a second pass; T0 is complete, T1–T5 have
exemplars.

**A6. Section 10 of the report (the Pebcrow numbers) needs the real figures.** The
"nine of ten passing, zero of ten did what was asked" line must trace to a real
artifact in the harness notes before it goes in. If it cannot, cut the numbers and
keep the observation.

## Deliverables

1. **Repo** (this). Public, MIT. README leads with the affiliation disclaimer.
2. **Report**, 8–15 pages, in `report/`. Sections as drafted:
   what this is → why OOD evaluation matters → method + parameter table →
   calibration (A3) → degradation (E1) → coverage as reward (E2 + E2b) →
   metric disagreement (E3) → fourth axis, unvalidated (E4) → what this does
   not show → note from an adjacent domain.

## Experiments

| id  | question | needs model? | status |
|-----|----------|--------------|--------|
| E1  | do the three metrics degrade across tiers, and unevenly? | yes | tiers filled; analysis/e1_degradation.py; awaiting wave-2 sweeps |
| E2  | does a valid, better-to-live-in T5 layout score below a conventional one? | no | DONE: 4 pairs, conventional wins 4/4 (aging-in-place bath 100 vs 16.7); report/figures/e2_*.png |
| E2b | does best-of-N by coverage collapse diversity? | yes (local ok) | analysis/e2b_bestofn.py ready; awaiting e2b-samples job |
| E3  | where do cov / nav / OC disagree? | reuses E1 | first example already in hand: T0 kitchen, cov 100 nav 100, visibly bad |
| E4  | does the experience axis correlate with the three? | reuses E1 | analysis/e4_correlation.py ready; awaiting wave-2 sweeps |

## Test set ladder

| tier | what | count | done |
|------|------|-------|------|
| T0 | rectangular, typical | 8 | 8 |
| T1 | proportion / scale | 8 | 8 |
| T2 | non-convex | 8 | 8 |
| T3 | non-orthogonal | 8 | 8 |
| T4 | sloped ceiling | 8 | 8 |
| T5 | unconventional program | 8 | 8 |

## Out of scope

IFC/gbXML, 3D beyond the ceiling plane, training or fine-tuning, reimplementing
GBM, any claim about GBM's performance, a web UI.

## Standards

Every number in the report traces to a script here. Every unpublished parameter is
in `params.py` and printed by `envelope-shift params`. Negative results get the
same prominence as positive ones. Nothing claims to measure human preference.

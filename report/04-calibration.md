# 4. Calibration: we do not reproduce the published band

> **Status.** Coverage and overlap & clearance figures here are HELD: the
> arithmetic reproduces. HELD is not a claim that overlap & clearance is a valid
> measure here; see section 8 on its dependence on the placement convention.
> Navigability figures are STALE: they predate the doorway fix and have not
> been rescored ([status of results](README.md#status-of-results)).

T0 exists to be reproduced. It is eight rectangular, typical rooms — the most
in-distribution material this repo contains — so if the harness were calibrated
against the published one, T0 is where the two would agree. They do not, and
that gap is the most important methodological fact in the report. Every figure below is a cell in
[`report/data/calibration_t0_summary.md`](data/calibration_t0_summary.md), which
rescores the committed T0 layouts and ends with the published band.

| arm | coverage | navigability | overlap & clearance |
|---|---:|---:|---:|
| deepseek | 100.0 | 98.4 | 12.9 |
| glm | 100.0 | 86.0 | 10.0 |
| local | 95.7 | 93.5 | 11.2 |
| opus | 100.0 | 98.4 | 0.0 |
| sonnet | 100.0 | 95.2 | 1.0 |
| Higharc's best frontier text LLM (Claude Opus 4.6) | 76.4 | 45.7 | 7.4 |

Every arm handed the inventory scores 95.7 or better on coverage (`local` over 7
rooms: one reply did not parse) and 86.0 or better on navigability, against a published 76.4 and 45.7. Overlap & clearance
is the one axis in the neighbourhood, and it splits by model: the two Claude arms
score 0.0 and 1.0, the others between 10.0 and 12.9. Three likely contributors
to the coverage and navigability gap are below. None of them is a defect in the
published work, and the section's data does not show that together they explain
the gap:

1. **Our inventory tables are thinner than a production set.** Coverage is the
   fraction of an expected inventory that appears, and a shorter list is an
   easier list. Ours are hand-authored (section 3).
2. **Our targets and clearances are looser.** Navigability depends entirely on
   how wide the walking body is and how close to a fixture counts as arriving,
   and both were our choice. The sweep below shows that they carry a lot, but
   not the whole gap: under STRICT, which tightens both, every
   inventory-supplied arm's T0 navigability stays above the published 45.7, the
   lowest being `glm` at 61.4.
3. **Our prompt hands the model the inventory.** Withhold it and the same arms
   fall to between 30.5 (`glm-noinv`) and 62.2 (`opus-noinv`) coverage — cells
   in the same table. On these rooms, coverage tracks closely whether the model
   was handed the list.

None of the three covers overlap & clearance. Why the Claude arms score 0.0
and 1.0 against a published 7.4 while the others score more is unexplained;
section 8 notes that this split has not been separated from how each arm reads
the placement convention.

The consequence is a restriction on every claim here: **absolute scores here are not comparable with
the published ones, so every result that follows is relative** — across tiers,
across arms, and between the two layouts of a paired envelope. Nothing
downstream needs the absolute numbers.

The caveat cuts both ways, and the counter-evidence is theirs, not ours: the
published in-distribution coverage result is ninety-eight point two per cent — a
figure from the post itself, not from this harness — which already sits within
two points of the ceiling. One reading is that a near-ceiling coverage score
on typical rooms need not be an artifact of a thin inventory table, since their
own reported number is already close to it on a richer one. The comparison does
not settle it: that figure belongs to a supervised decoder on its own corpus,
their best text-LLM figure is 76.4, and every
inventory-supplied arm here scores 95.7 or better, so the thin table and the
supplied inventory may still be doing much of the work.

## Tightening the parameters: what moves and what cannot

The STRICT set of section 3 doubles the extraneous penalty, widens the walking
body and halves the reach; rescoring the same T0 layouts under it gives
[`report/data/calibration_t0_delta.csv`](data/calibration_t0_delta.csv) and the
strict half of the summary.

Navigability responds hard. Under STRICT the `glm` arm's T0 mean falls from
86.0 to 61.4 and `deepseek`'s from 98.4 to 90.0, with individual rooms moving
further: `t0_sbed_11x12` under `glm` goes from 97.8103 to 0.0000, and
`t0_kitchen_12x14` under `deepseek` from 98.7211 to 65.9670 (the per-room
tables,
[`report/data/calibration_t0_default.csv`](data/calibration_t0_default.csv) and
[`report/data/calibration_t0_strict.csv`](data/calibration_t0_strict.csv)).
On that room, half a foot of reach and a quarter foot of body radius are the
difference between a walkable room and an unwalkable one.

**Coverage moves by 0.0000 on every room in every inventory-supplied arm.**
Doubling the penalty for extraneous entities changes nothing at T0, because a
model handed the inventory for an ordinary room emits nothing extraneous to
penalize. The delta table's `-noinv` rows are the control: withhold the list
and coverage does move, because then there is something to penalize. The
extraneous penalty is inert on typical rooms and bites only when the model
emits something off the list — which, section 5 shows, is exactly what a model
does when a brief asks for an unconventional program.

Each door-to-target pair's detour factor is capped (`nav_detour_cap`, in the
section 3 table), which keeps navigability inside its declared range whatever the
geometry; the summary table's `off_scale` column counts rows outside it, and
reads 0 on every row.

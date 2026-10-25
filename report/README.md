# Report — envelope-shift

An out-of-distribution test of the published evaluation method, and what it
finds when a validity check is asked to carry a reward: off the published
distribution, coverage penalises an arm for following the brief. Read section 8
before quoting anything from it: this harness does not reproduce the published
band, so every result here is relative rather than absolute.

The repo's [top-level README](../README.md) is the short version.

## Status of results

An adversarial review of the first full draft found that three of its four
headline results were wrong. The report was rewritten around what survived, and
nothing has been re-run or rescored since the last fixes, by choice. Each result
carries one of three labels, and each affected section repeats its label at the
top.

**HELD: the arithmetic reproduces from the data.** Every committed table under
[`data/`](data) regenerates by the command its provenance entry names: the
parameter tables and the two E2 tables from code alone, every other table from
the raw sweep output. The adversarial review reproduced the first draft's
numbers from the raw rows, and every table was regenerated after the fixes.
The surviving finding rests on these tables: coverage, used as a reward,
penalises an arm for furnishing what the brief asked for
([section 5](05-coverage-as-reward.md)). Coverage, overlap & clearance and the
selection experiment are HELD throughout (for overlap & clearance, see section 8
on the placement convention), and so are the hand-authored E2 pairs
on all four axes: that table is computed from code alone and still regenerates
byte for byte under the fixed metrics.

**INVALIDATED: claims of the first draft, withdrawn.**

- *Coverage saturates.* The model was handed the answer list, and the
  unconventional brief never reached it. The brief now reaches every arm and the
  answer key is held out; no section makes the claim, and
  [`e1_saturation.csv`](data/e1_saturation.csv) is kept as data only.
- *Parse failures rise with difficulty.* The failures were a dead local server,
  counted as model errors. Transport failures are now their own kind, the
  per-tier parse-failure counts in
  [`e1_degradation.csv`](data/e1_degradation.csv) show no trend, and the section
  that made the claim was cut.
- *Navigability reimplements the published formula.* The path and the straight
  line were measured between different points, so the detour term was zero in
  most rows and the metric was in effect a success rate. Both distances now span
  the same two points, a per-pair cap keeps the score in its declared range, and
  the sweeps were rescored after both fixes.

**STALE: navigability from the model sweeps.** A later fix changed how a fixture
standing on a doorway is scored: it used to count as a reached target with a
zero-length path, and now that door-to-target pair counts as unreached
(`nav_door_on_target_reached`, [section 3](03-method.md)). The sweeps have not
been rescored since, so every navigability figure derived from them, in
sections 4, 5.1, 6 and 7, predates the fix and may move when they are. The
hand-authored navigability figures in section 5.2 are current.

## Contents

1. [What this is](01-what-this-is.md) — a test of the published method off its
   distribution, and the result in one paragraph.
2. [Why out-of-distribution evaluation](02-why-ood.md) — what held-out-from-the-
   same-corpus cannot tell you, and why a reward changes the metric's job.
3. [Method, and every parameter we had to invent](03-method.md) — the tiers,
   the five arms as they ran, and the full disclosed parameter table.
4. [Calibration: we do not reproduce the published band](04-calibration.md) —
   the reproducibility gap, and the restriction it puts on everything after.
5. [Coverage as a reward (T5, E2, E2b)](05-coverage-as-reward.md) — where the
   T5 coverage fall comes from, the four paired layouts, and best-of-N selection.
6. [Where the metrics disagree (E3)](06-disagreement.md) — perfect coverage on a
   room with no walkable path.
7. [A fourth axis, unvalidated (E4)](07-fourth-axis.md) — isovist and daylight
   measures, advisory and never a gate.
8. [What this does not show](08-what-this-does-not-show.md) — the limitations,
   at full strength.
9. [A note from an adjacent domain](09-adjacent-domain.md) — the same failure
   mode in browser-game generation, without numbers.

Plots live in [`figures/`](figures); the tables every section cites live in
[`data/`](data).

## Derived data — `report/data/` and `report/provenance.json`

Every number the report's sections quote must be a cell in a committed table
under `report/data/` that the section names by path. `report/provenance.json` is
the manifest: one entry per committed derived table (and per figure), naming the
exact argv that produces it and the `results/` inputs that argv reads.

Two placeholders appear in every command:

| placeholder | meaning |
|---|---|
| `{results}` | the canonical `results/` directory (gitignored, so host-bound) |
| `{out}` | a scratch directory the runner creates; nothing is written into the tree |

Check that every entry still reproduces its committed file, byte for byte:

    uv run python -m envelope_shift.analysis.regenerate --results results

Refresh the committed tables after a new sweep, then review the diff:

    uv run python -m envelope_shift.analysis.regenerate --results results --write

### Two kinds of number that no table can hold

Two quantities in the sections are written out in words rather than as digits,
and both are deliberate rather than stylistic.

- **Figures quoted from the published Higharc post** — the in-distribution
  coverage result in sections 4 and 8. It is theirs, not ours; it is not the
  output of anything in this repo, so there is no derived table it could be a
  cell of, and it is attributed to the post in the sentence that uses it.
- **Counts of rows rather than values** — "sixty layouts are flagged, eleven
  with the `nav<50` tag" in section 6. The count is obtained by counting
  the rows of `data/e3_disagreement.csv`, which the section names; it is not a
  cell in it.

Everything else in the report is a digit and is a cell in a table the same
section cites by path. A number that could not be traced was removed rather than
disguised. Section 9 carries no numbers at all: its sources are private.

`.png` entries carry `"byte_identical": false` — matplotlib output is not stable
across versions, so figures are checked for existence only. Every `.csv` and `.md`
entry is compared byte for byte.

### What each table is for

| table | result it carries |
|---|---|
| `model_arms.csv` | every arm as it ran: model id, reasoning configuration, sampling, the model the provider reported answering, and the call count, derived from each raw row's `call_config` |
| `t5_decomposition.csv` | per arm, the T5 coverage gap split into missing lines, declared-program penalty, synonym penalty and other penalty; floor-clamped rows counted and excluded |
| `t5_common_rooms.csv` | the same decomposition restricted to the T5 rooms every arm has an unclamped parsed row for, with each arm's excluded rooms and why (clamped or parse failure) |
| `t5_by_envelope.csv` | the T5 rows behind the decomposition: per envelope and arm, coverage and the types in each bucket |
| `e1_degradation.csv` | the per-tier table: per tier and arm, the three metric means with bootstrap CIs and the row, parse and failure counts behind them; each tier also carries an `all arms` rollup row (its metric means mix prompt conditions, and the figure leaves it out) |
| `e1_saturation.csv` | coverage pooled over every parsed layout, inventory-supplied against inventory-withheld: n, mean, range and the count scoring exactly 100.0. Built for the withdrawn "coverage saturates" claim; no section cites it |
| `e3_disagreement.csv` | layouts where the three published metrics disagree about the same room |
| `e4_correlation.csv` | Spearman rho of each experience measure against each published metric |
| `e2b_bestofn.csv` | best-of-N selection by coverage over up to 16 parsed samples per room against pool diversity, per arm at provider-default sampling; each `ALL` row adds a same-size baseline, the type entropy of 2000 seeded random one-per-room selections |
| `e2_pairs.csv` | the four hand-authored T5 pairs on all four axes, plus the turning-circle check |
| `e2_coverage_gap.csv` | where each E2 pair's coverage gap comes from: unsatisfied inventory lines versus each off-inventory type, and whether the envelope declares that type |
| `calibration_t0_default.csv`, `calibration_t0_strict.csv` | T0 rooms rescored under each parameter set |
| `calibration_t0_delta.csv` | STRICT minus DEFAULT, per room |
| `calibration_t0_summary.md` | per-arm T0 means under both sets against the published band; `off_scale` counts rows whose navigability left the metric's declared -35..100 |
| `params_default.md`, `params_strict.md` | every field of `params.Params`, STRICT-changed fields marked |

## Figures

`report/figures/` holds the plots. `e2_*.png` come from
`envelope_shift.experiments.e2_pairs`; the rest come from the `analysis/` script
that also writes the matching table. `figures.py` renders individual layouts.

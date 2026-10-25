# envelope-shift

**Affiliation disclaimer.** This is an independent reimplementation, from a
public engineering post, of the three evaluation metrics Higharc published for
their Generative Building Model
([Production-grade AI layout: Generative Building Model](https://www.higharc.com/blog/ai-layout-at-higharc-tokenizing-buildings),
April 2026). The author has **no affiliation** with Higharc, no access to their
model, their corpus or their inventory tables, and makes no claim whatever about
what their model would score on anything in this repo. GBM was never run here
and could not be. The original post is unusually detailed and generous, and it
is the reason this project is possible at all.

## What it is

envelope-shift is a stress test for the room-layout scoring metrics used in home
design software. It gives AI models unusual room briefs (a kitchen that is also
the laundry, a bathroom for aging in place, a nursery, a bedroom with a work
nook) and scores the layouts they return with the three published metrics:
coverage, navigability, and overlap & clearance. The test set is a ladder of six
tiers of eight rooms each, from ordinary rectangles up to ordinary geometry with
an unconventional program. Its one surviving finding is that **coverage, used as
a reward, penalises a model for furnishing what the brief asked for.**

[![the aging-in-place pair](report/figures/e2_t5_pbath_aging_in_place.png)](report/figures/e2_t5_pbath_aging_in_place.png)

The sharpest case is a hand-authored, fully valid primary bath designed for
aging in place: coverage scores the conventional layout **71.4** and the
unconventional one **7.1**. It docks the unconventional layout once for the
bathtub, shower stall and linen cabinet it gives up, and again for the roll-in
shower, shower bench and grab bars it puts there instead, which coverage scores
as *extraneous* ([section 5](report/05-coverage-as-reward.md),
[`e2_pairs.csv`](report/data/e2_pairs.csv)).

## Status of results

Read this before quoting anything. The report says plainly what held, what was
shown wrong and what is out of date; the full list is in
[report/README.md, "Status of results"](report/README.md#status-of-results).

- **Held:** the coverage-as-reward finding ([section 5](report/05-coverage-as-reward.md)).
  Every committed table regenerates from the raw data, and an adversarial review
  reproduced the numbers.
- **Invalidated:** three headline results of the first draft: "coverage
  saturates", "parse failures rise with difficulty" and "navigability
  reimplements the published formula". Each was traced to a defect in the
  experiment, not in the arithmetic, and withdrawn.
- **Stale:** navigability figures from the model sweeps predate the last
  navigability fix and have not been re-run.

## Quickstart

Offline: no model, no API key, no `results/` directory. It needs
[uv](https://docs.astral.sh/uv/) and Python 3.12.

```bash
uv sync
uv run pytest -q                                   # the test suite
uv run envelope-shift params                       # the chosen-parameters table
uv run envelope-shift params --params strict --out-dir /tmp/params
uv run envelope-shift score-layout                 # score one committed layout, print its metrics
```

About nine tests skip on a fresh clone, and `uv run pytest -q -rs` prints why:
they re-derive tables from `results/`, the raw model output, which is not
distributed. [docs/offline.md](docs/offline.md) has the details.

The commands that call a model or read `results/` are below for completeness.
This release does not re-run them.

```bash
uv run envelope-shift sweep --models local opus sonnet --out results
uv run envelope-shift score results/layouts.jsonl
uv run python -m envelope_shift.analysis.regenerate --results results
uv run envelope-shift summary results --out report/summary.md
```

`local` targets an OpenAI-compatible server at `localhost:8000`. `opus` and
`sonnet` reach Claude through the Claude Code command line (`claude_cli` in
`models.toml`); set `ENVELOPE_SHIFT_CLAUDE_CMD` to the launcher prefix. Keys come
from the environment, or from the optional key file named by
`ENVELOPE_SHIFT_KEYFILE`. Layouts are stored raw, so metrics can be re-run after
a change without re-querying a model.

## Read the report

**[`report/`](report/README.md)** is the write-up, in nine short sections:

| | |
|---|---|
| [1. What this is](report/01-what-this-is.md) | a test of the published method off its distribution |
| [2. Why out-of-distribution](report/02-why-ood.md) | what held-out-from-the-same-corpus cannot tell you |
| [3. Method and parameters](report/03-method.md) | the tiers, the arms as they ran, and every constant we had to invent |
| [4. Calibration](report/04-calibration.md) | we do not reproduce the published band, and why that restricts everything |
| [5. Coverage as reward](report/05-coverage-as-reward.md) | the surviving finding: T5, the paired layouts, best-of-N selection |
| [6. Metric disagreement](report/06-disagreement.md) | where the three axes contradict each other |
| [7. A fourth axis](report/07-fourth-axis.md) | isovist and daylight measures, explicitly unvalidated |
| [8. What this does not show](report/08-what-this-does-not-show.md) | the limitations, at full strength |
| [9. A note from an adjacent domain](report/09-adjacent-domain.md) | the same failure mode, seen elsewhere |

Every number in the report is a cell in a committed table under
[`report/data/`](report/data), named in the sentence that uses it and
regenerable by the command in `report/provenance.json`.

## Why this exists: a PebCrow Guild exercise

envelope-shift was one of the first projects used to exercise the PebCrow Guild,
a private framework that reproduces with AI agents the layered rigor of a real
engineering organization: prototype teams, hardening teams, research,
independent review, and layers of accountability. An orchestrator dispatches and
audits work; leads own an epic; workers each build one tracked work item; fresh
reviewers who did not do the work review it. Work is governed by contracts:
claims frozen before work begins, each backed by a runnable oracle, and a land
gate that refuses to merge unless the checks pass. Lessons from every project
are folded forward into later Guild operations.

The project was chosen on purpose: a small, single-purpose repo in a domain the
author does not work in, residential architecture. The question was whether
coordinated agents could turn that into something a specialist would take
seriously, and where the machinery would break.

It broke in an instructive place. The first full artifact passed its contract
with every claim green, and four adversarial reviewers, told that finding a flaw
was success, found in one round that three of its four headline results were
invalid. Every number reproduced from the raw data; the experiment did not
measure what it claimed. The contract had passed it because every claim tested
bookkeeping (numbers trace to tables, tables regenerate, sections exist, tests
pass) and none asked whether the experiment measured what it said it did. The
artifact was perfectly traceable, perfectly reproducible and wrong: the same
failure the report describes in coverage, reproduced by the process that
produced the report. The deepest defects predated the Guild, in the hand-written
scaffold, but every worker inherited them and none questioned its inputs. A
stronger worker would have passed the same claims.

What worked was the adversarial review, which found everything in one round, and
the audit guards: a frozen claim could not be silently amended. The rebuild added
validity claims, which ask whether the independent variable reaches the system
under test, beside the bookkeeping ones, and the report was rewritten around the
one result that survived. The lessons (validity claims, an inputs audit in every
worker brief, opening the raw row before believing a number, attacking a spec
before freezing it, prose review before an empirical epic closes) now shape how
later Guild projects run. [docs/guild-case-study.md](docs/guild-case-study.md)
is the full retrospective.

## Limitations

[Section 8](report/08-what-this-does-not-show.md) has them at full strength. In
short: eight rooms per tier, with one reply per room per arm (7 or 8 parsed); the envelopes are synthetic; the inventory tables
and every unpublished parameter are this harness's own, so absolute scores are
not comparable with the published ones; the arms are general-purpose models run
under different transports and sampling, not Higharc's model; overlap &
clearance depends on how an arm reads the placement convention; the fourth axis
is unvalidated; and nothing was re-run after the last fixes, so sweep
navigability is stale. The author has no professional expertise in architecture.
Treat this as a well-evidenced warning about one metric used as a reward, not a
verdict on anyone's system.

## What is here

```
src/envelope_shift/
  schema.py         envelope + wall-referenced entity, mirroring the published (e, t, δ, s, ρ)
  geometry.py       exact shapely polygons: footprints, door clearance, free floor, headroom
  params.py         every parameter the published work does not specify, in one table
  inventory.py      expected inventory per room type, with alternative groups
  metrics/          coverage, navigability, overlap & clearance, and the exploratory experience axis
  envelopes/        the tiered test set, authored as code; data/ holds JSON dumps
  analysis/         one script per result, each writing a table under report/data/
  experiments/      the hand-authored paired layouts (E2)
  generate.py       prompt a model (OpenAI-compatible, Anthropic, or the Claude Code CLI), parse a layout
  run.py            sweep, score, score-layout, params, summary
report/             the write-up, its derived tables, and its figures
docs/               offline use and the Guild case study
tests/
```

`SPEC.md` is the original working spec, kept for history; `report/` is
authoritative. [CHANGELOG.md](CHANGELOG.md) records the releases.

## License

MIT, copyright Pebcrow Inc. See [LICENSE](LICENSE).

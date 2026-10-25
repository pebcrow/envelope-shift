# 1. What this is

In April 2026 Higharc published an unusually generous engineering account of
their Generative Building Model: a decoder trained on 3,500 homes and 75,720
rooms that tokenizes a building and emits furnished room layouts, evaluated on
50 held-out rooms against three metrics — coverage, navigability, and overlap &
clearance. The post gives the metric formulas, the entity parameterization, the
corpus sizes, the results table, and an honest list of what the model does not
yet handle. That transparency is why this project exists; almost none of it
would have been possible against a paper reporting one aggregate score.

This repo is not an audit of that work, and it is not a scoreboard. It is a
test of the published *method* off its own distribution — the job their posting
describes as "define construction-domain benchmarks, build ground-truth
datasets, establish eval pipelines" — aimed at the *next* problem rather than
the current numbers. The posting names reinforcement learning for generative
architectural design, and whole-home generation from natural language; both
take a metric that today certifies a layout and ask it to rank one. Section 2 is
why that matters.

## The result, in one paragraph

Off the published distribution, coverage — the metric a layout generator would
most naturally be trained or selected against — penalises an arm for following
the brief. With the room's inventory supplied, every arm scores near the top of
the scale on the ordinary and geometrically awkward tiers. On the tier whose
brief asks for an unconventional program, the score falls: never for a missing
line, always as the extraneous-entity penalty, levied on the washer and dryer
the laundry kitchen asked for, the desk the work nook asked for, the grab bars
the aging-in-place bath asked for, and on synonyms. On the rooms every arm
completed, the arms rank roughly inversely to how much of the program they
furnished, with a tie. Hand-authored layouts show the same mechanism in two of
four rooms, and selecting samples by coverage picks less diverse layouts than
chance for two of three arms. Section 5 carries all three.

What is in here: the three published metrics, reimplemented from the post
alone; a tiered set of envelopes and briefs that walks away from the typical
production home one axis at a time, scored across five arms (section 3) — arms,
not models, because they also differ in thinking, sampling and transport;
and a fourth, explicitly unvalidated, experience axis (section 7).

Read section 4 before quoting anything: this harness does not reproduce the
published band, so every result is relative rather than absolute. Section 8 is
the limitations, at full strength, and the
[status of results](README.md#status-of-results) says which results held, which
were withdrawn and which figures are stale.

# 3. Method, and every parameter we had to invent

This harness asks what happens off the published evaluation's distribution, so
almost none of it is a reimplementation. What it reuses is the metric
definitions — coverage, navigability and overlap & clearance, with the entity
parameterization and the published detour weight exactly as the post states
them. Everything else had to be chosen, and section 4 is what those choices
cost.

## The ladder

Six tiers of eight envelopes each, authored as Python so a tier's defining
property is stated once, in diffable code. T0 is rectangular, typical, and
exists to calibrate; T1 varies proportion and scale; T2 is non-convex; T3
non-orthogonal; T4 adds a sloped ceiling; T5 keeps the geometry ordinary and
makes the *program* unconventional — a nursery, a laundry-in-kitchen, a bedroom
with a work nook, a primary bath for aging in place.

## The arms

Five arms, named by what ran and cited from
[`report/data/model_arms.csv`](data/model_arms.csv), which is derived from each
raw row's own `call_config` and counts every call.

- `claude-opus-5` and `claude-sonnet-5` (labelled `opus` and `sonnet` in every
  table) ran with extended thinking at effort `medium`, reached through the
  Claude Code command line on a subscription, with tools switched off. The
  command line adds a fixed preamble of a few hundred tokens that no other arm
  receives. The effort level is *attested* by the invocation, not observed in
  the reply; what the reply does show is that thinking ran on every row.
- `deepseek-v4-flash-proxy` (`deepseek`) ran with thinking disabled. Its
  provider's catalog dropped that id in September 2026, and the proxy now
  answers it as `deepseek-flash`, which is the model the table records as
  observed.
- `glm-5-3-proxy` (`glm`) ran at `reasoning_effort` `low` and answers as
  `glm-5.3`.
- `qwen3-30b-a3b` (`local`) is a local open-weights model with no reasoning
  configuration.

The proxy and local arms sample at temperature 0.2; the Claude arms run at the
provider's default, because the Claude command line accepts no temperature.
Every arm except `local` also runs with the expected inventory withheld (the
`-noinv` suffix). The table counts 160 calls each for `opus`, `sonnet` and
`deepseek`, 96 for `glm` and 48 for `local`.

The sweep asks each arm for one reply per envelope. A reply that does not parse
as schema-valid JSON is counted as a parse failure, not dropped; a call that
fails in transport never reached a model, so it is excluded from the parse rate,
and retries are not counted as replies. Each parsed layout is scored on the
three published axes and on an exploratory, unvalidated experience axis
(section 7).

The corpus analysed here is a re-run. The original proxy sweep never
transmitted the brief — the model saw the envelope and the room type, but not
the program the tier was built around. Every row analysed here was re-checked
against the prompt this code builds for its envelope and arm, brief included,
and nothing from the original proxy corpus is quoted.

E2b (section 5) draws 16 samples per envelope from `deepseek`, `opus` and
`sonnet`, all at the provider's default sampling, and
[`report/data/e2b_bestofn.csv`](data/e2b_bestofn.csv) records them. It uses the
provider default rather than 0.2 because the Claude arms cannot be set to
anything else, and a selection experiment compares like with like only if every
arm samples the same way.

One amendment to the published parameterization was unavoidable. The size triple
is width, height and depth with no vertical position, which scores wall-hung
casework as though it sat on the floor — upper cabinets block a walking path and
overlap the counter beneath. Entities therefore carry an `elevation`, elevated
ones do not block paths, and two overlap only where they share vertical range.

## The parameter table

Every constant the published work does not specify lives in one module, printed
by `envelope-shift params`, so a value cannot be used without being disclosed
here. Every value below is a cell in
[`report/data/params_default.md`](data/params_default.md) or
[`report/data/params_strict.md`](data/params_strict.md). STRICT is the tightened
set section 4 sweeps; it changes only unpublished parameters, never a formula.

| parameter | DEFAULT | under STRICT | what it sets |
|---|---|---|---|
| `coverage_extraneous_penalty` | 0.5 | 1.0 — changed under STRICT | cost of an extraneous entity type |
| `coverage_clamp_min` | 0.0 | unchanged | floor on a room's coverage |
| `nav_detour_weight` | 0.35 | unchanged | published; detour term's weight |
| `nav_grid_ft` | 0.5 | unchanged | A\* grid pitch, feet |
| `nav_body_radius_ft` | 0.75 | 1.0 — changed under STRICT | walking body radius, feet |
| `nav_door_inset_ft` | 0.5 | unchanged | where a path starts inside a door |
| `nav_reach_ft` | 1.0 | 0.5 — changed under STRICT | distance at which a target counts as reached |
| `nav_detour_cap` | 1.0 | unchanged | ceiling on one pair's detour factor; keeps navigability inside its declared range |
| `nav_door_on_target_reached` | False | unchanged | whether a pair counts as reached when the target covers the door's start point |
| `oc_w_entity_overlap_fraction` | 0.25 | unchanged | weight on pairwise overlap |
| `oc_w_global_overlap_area` | 0.25 | unchanged | weight on total overlapping area |
| `oc_w_door_clearance_intrusion` | 0.25 | unchanged | weight on door swing intrusion |
| `oc_w_wall_bounds_violation` | 0.25 | unchanged | weight on leaving the envelope |
| `oc_overlap_eps_sqft` | 0.01 | unchanged | touching versus overlapping, square feet |
| `walk_clear_elevation_ft` | 4.0 | unchanged | height above which an entity stops blocking |
| `vertical_tolerance` | 0.0 | unchanged | headroom slack before a violation, T4 only |
| `exp_sample_grid_ft` | 1.0 | unchanged | experience sampling pitch, feet |
| `exp_isovist_rays` | 180 | unchanged | rays cast per isovist |
| `exp_isovist_max_ft` | 60.0 | unchanged | isovist ray length cap, feet |

Four of these are guesses about intent rather than engineering choices — the
magnitude of the extraneous penalty, the four overlap & clearance weights, the
body radius and the reach distance. The published formulas name them all and fix
none; section 4 is what happens when you move three.

Coverage also needs an expected inventory per room type, and the published work
does not publish its tables. Ours are hand-authored and certainly thinner than a
production set — the largest single reason the absolute numbers here are not
comparable with theirs. Section 4 takes it up first, section 8 at full
strength.

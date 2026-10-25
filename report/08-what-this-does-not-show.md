# 8. What this does not show

Every restriction below is load-bearing. They are collected here at full
strength rather than distributed as footnotes, because several of them bound the
results more tightly than the results themselves are interesting.

**No claim whatever is made about the Generative Building Model.** GBM was
never run here. It could not be — there is no access to the model, the
weights, the API, or the corpus. This report makes no claim about how GBM
would score on these envelopes, on the paired layouts, or anywhere else; nothing
here is evidence either way, and no sentence should be read as if it were.
Every arm scored here is a general-purpose language model prompted to emit a
layout, which is a different system solving a different problem, and the
comparison that matters is between arms and between tiers within this harness,
never against a published number.

**The author has no professional expertise in architecture.** What is here was
learned from the published post and public sources. The geometry and the metric
work are mechanical and checkable; the architectural judgements are not. That
the hand-authored aging-in-place bathroom is better to live in is a claim about
how people use rooms, not a measurement, and an architect might reasonably
disagree with the inventories, the tier boundaries, or which rooms count as
atypical. Read the geometry as verified and the architecture as an outsider's.

**The inventory tables are ours, not theirs.** Coverage scores a layout against
an expected inventory, and the published work does not publish its tables. Ours
are hand-authored and certainly thinner than a production set, which makes
coverage easier to satisfy on ordinary rooms and is the first reading anyone
should give a near-ceiling score. The counter-evidence is theirs rather than ours — the
published in-distribution coverage figure is ninety-eight point two per cent,
already within two points of the ceiling on a richer table — but that is a
second reading.

**The absolute numbers are not comparable with the published ones.** Section 4
is the calibration gap in detail: this harness does not reproduce the published
band at T0, the most in-distribution material it contains. Every result here is
therefore relative — across tiers, across arms, or between the two layouts of a
paired envelope — and any absolute figure quoted from this report against a
figure from the post is a misuse of both.

**Every unpublished parameter was chosen by us.** The published formulas name
the body radius, the reach, the extraneous penalty and the overlap & clearance
weights and fix none of them. All are in the section 3 table; section 4 shows
that moving three of them moves navigability by tens of points.

**The counts are small and the intervals are wide.** Each tier-and-arm cell of
[`report/data/e1_degradation.csv`](data/e1_degradation.csv) has 8 replies, one
per room, of which 7 or 8 parsed, with no retries and no best-of-N anywhere
except the E2b pool. Its means and bootstrap intervals are computed over the
parsed layouts.
The T5 decomposition ([`t5_decomposition.csv`](data/t5_decomposition.csv)) rests on 7 rooms
for four arms and 8 for `deepseek`; [`t5_common_rooms.csv`](data/t5_common_rooms.csv) holds a
common 7. The bootstrap
intervals are correspondingly wide, and at T5 they overlap for every pair of
arms but `local` against `glm` and `opus`. No tier-to-tier step is offered as a
trend; the T5 result is offered because its mechanism can be read row by row,
not because the means are precise.

**The arms did not run under identical conditions.** The two Claude arms reach
their models through the Claude Code command line, which adds a fixed preamble
the proxy and local arms never see. They sample at the provider's default,
because that command line accepts no temperature, while the proxy and local
arms sample at a fixed low temperature. Their reasoning effort is attested by
the invocation rather than observed in the reply: the reply shows that thinking
ran, not at what effort. So every comparison here is between arms, not models.

**One model id was re-aliased under us.** The DeepSeek arm was requested as
`deepseek-v4-flash-proxy`; its provider's catalog dropped that id during the
work, and the proxy answered it with a different model id, which section 3 and
the arms table record. The arm is what answered, not what was requested.

**The synonym map is a judgement.** Part of the T5 penalty is attributed to
synonyms — a model naming a declared or inventory type in its own words — and
which names count is decided by hand in `analysis/synonyms.toml`, with the
evidence for each mapping and the candidates declined. A stricter or looser map
moves points between the synonym and other columns. It cannot move them into
the missing column, so the finding that the fall is a penalty and not an
omission does not depend on it.

**Clamped rows are left out of the decomposition.** Two workshop-garage layouts
carry enough extraneous types to fall below the coverage floor, and the scorer
holds them at zero. Their parts cannot sum to a clamped score, so the
decomposition excludes them and counts them; including them lowers those two
arms' means further, in the same direction.

**The envelopes are synthetic.** Hand-authored geometry, with no claim that it
represents renovation work or any real housing stock. The tiering is an argued
ordering, not a measured one, and the T5 programs are plausible briefs rather
than sampled ones.

**The experience axis is unvalidated.** It is not validated against human
preference, it is advisory and never a gate, and validating it would require a
preference study this project does not attempt. Section 7 leads with that
sentence for the same reason it is repeated here. Its near-orthogonality to the
three published metrics means only that it is not redundant — orthogonal is not
a synonym for good.

**Overlap & clearance depends on the placement convention.** Every entity is
placed relative to a wall: `t` is the midpoint of its back edge along that wall,
`offset` is its distance from the wall face, rotation turns it about that
midpoint, and `elevation` lifts it off the floor. Overlap & clearance scores the
geometry that convention produces, so an arm that reads it differently, for
instance by centring an entity on `t` or rotating it about its own centre,
produces overlaps and wall violations the metric scores as layout errors. The
arms' split on this axis at T0 (section 4) has not been separated from that
effect. The definitions of the four terms, their equal weights and the touching
tolerance are this harness's own choices as well (section 3).

**Nothing was re-run after the last fixes.** The sweeps were last scored before
a fixture standing on a doorway was made to count as blocking that pair, and by
choice nothing was re-run or rescored for this release. Coverage and overlap &
clearance do not depend on that fix; every navigability figure taken from the
sweeps does, and is stale until the sweeps are rescored. The
[status of results](README.md#status-of-results) lists what held, what was
withdrawn and what is stale.

**The note in section 9 rests on work a reader cannot check.** It describes
measurements from a private repository, so it carries no numbers, and the
limitation is stated there too.

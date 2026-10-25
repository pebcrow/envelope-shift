# envelope-shift as a Guild exercise: a retrospective

envelope-shift is a stress test for room-layout scoring metrics. It gives AI
models unusual room briefs and scores the layouts they return with three metrics
a company published in an engineering post: coverage, navigability, and overlap
& clearance. Its surviving finding is that coverage, used as a reward, penalises
a model for furnishing what the brief asked for. The project is independent and
unaffiliated with the company whose metrics it tests.

This document is about how the project was built and what that process got
right and wrong. It is written as an engineering retrospective: the numbers are
the ones the process recorded, and the failures are stated at the same strength
as the successes.

## Why it was built

The PebCrow Guild is a private framework that reproduces, with AI agents, the
layered rigor of a real engineering organization: prototype teams, hardening
teams, research, independent review, and layers of accountability, of the kind
seen at engineering companies such as SpaceX. The Guild has no connection to any
such company; the resemblance is in the process, not the people. Lessons from
every project are folded forward into later Guild operations, so each project is
both a deliverable and a test of the machinery.

envelope-shift was one of the first projects used to exercise it, and it was
chosen on purpose. It is a small, single-purpose repository in a domain the
author does not work in, residential architecture. The question was whether
coordinated agents could turn that into something a specialist would take
seriously, and where the machinery would break. A small project in an unfamiliar
domain is a hard test of exactly the right kind: nobody involved could catch a
domain error by instinct, so whatever caught errors had to be the process.

A second, later run reused the project to test a "project lead" recipe and the
Guild's retro loop.

## How the Guild ran it

**Roles.** An orchestrator dispatches work and audits it. Leads each own an
epic. Workers each build one tracked work item. Fresh reviewers, who did not do
the work, review it.

**Contracts.** Work is governed by claims frozen before the work begins. Each
claim is a sentence that is either true of the finished repository or not, and
each is backed by a runnable oracle that answers it. The oracles are pinned, so
the workers being judged cannot edit the contract they are judged against. A
land gate refuses to merge any change unless the checks pass.

**Flow.** The scaffold was written by hand in one session, before the Guild
touched the project. Then the claims were frozen with their oracles. Then workers
built in isolated lanes, each landing through the gate, which runs the full test
suite. Then came adversarial review, then rework.

**The numbers.**

- At the end, the epic carried 25 claims: 13 bookkeeping claims, 10 validity
  claims and 2 human-approval claims. All 23 machine-checkable claims were green
  at the end of the rebuild.
- About 40 distinct work items appear in the local development history before
  this release.
- 11 worker lanes landed in a single day of the rebuild, and 8 of them needed no
  intervention beyond review. One lane failed the integrate gate: its own check
  passed and the repository's tests did not. The escalation ladder moved the work
  to a stronger worker, which landed a correct fix with no human involvement.
- The first round of review used 4 adversarial reviewers. The rebuild had 2
  adversarial prose reads and 1 formal prose-review round, which confirmed 4
  caveats and checked 11 sentences as valid.
- The orchestrating session logged about 28 manual interventions in one day.
  Almost all were judgment calls, such as whether a spec could be gamed or
  whether data was still valid, not engineering.
- In the later, smaller run, two leads each landed one slice (an offline summary
  command, then its hardening), with a fresh reviewer per slice. The slices were
  judged by actually running the command. That judge caught a default-input bug
  that the worker's 8 green tests had missed. This repository's history carries
  a fix of that kind: the summary command's `--pool` defaulting to `all` in both
  of its parsers, with a test for the default path.

## What went wrong, and how adversarial review caught it

The first full artifact was judged publishable by its contract, with 12 of 12
claims green. Four adversarial reviewers were then told that finding a flaw was
success and agreeing was failure. In one round they found that three of the four
headline results were invalid:

- **"Coverage saturates" was an artifact.** The model was handed the answer
  list, and the brief for the unconventional-program tier was never sent to the
  model at all.
- **"Parse failures rise with difficulty" was an artifact.** The failures were a
  dead local server, counted as model errors. The real ladder was flat noise.
- **"Navigability reimplements the published formula" was false.** The path and
  the straight-line distance were measured between different points, so the
  detour term was zero in most rows. The metric was in effect a success
  rate.

What held up was the arithmetic: every number reproduced from the raw data to
four decimals. The arithmetic was sound and the experiment was not.

The contract passed the artifact because every claim tested bookkeeping. Numbers
traced to committed tables, tables regenerated byte for byte, sections existed
and fit a word band, tests passed, nothing was published. No claim asked whether
the experiment measured what it said it measured. The artifact was perfectly
traceable, perfectly reproducible and wrong. That is the same failure the report
argues about coverage, a check that is right on its own terms and blind to the
goal, reproduced by the process that produced the report.

Attribution was checked file by file. The deepest defects predate the Guild:
they were in the hand-written scaffold. But every Guild worker inherited them
and none questioned its inputs. Model quality was neither the cause nor the
cure: a stronger worker would have passed the same 12 claims.

Two things worked. The adversarial review found every one of these problems in a
single round. The audit guards held: a frozen claim could not be amended
silently, and attempts to work around the contract were refused rather than
absorbed.

The rebuild fixed each defect at its source, added validity claims beside the
bookkeeping ones, cut the sections that rested on invalid results, and rewrote
the report around the one finding that survived. The report's
[status of results](../report/README.md#status-of-results) records what held,
what was withdrawn and which figures are stale.

## Lessons folded forward

**Validity claims.** An empirical artifact needs claims that the independent
variable actually reaches the system under test, and that the effect is not
explained by a named confound, not only claims about bookkeeping. Here the
independent variable was the brief, and for a whole tier it never reached the
model. This now lives as a claim class in contract design.

**Inputs audit.** Every worker in this project built faithfully on a scaffold
that was wrong. A worker building on existing code must now state one input
assumption it checked. This lives as a field in worker briefs.

**Open the raw row.** All three invalid results were sitting in the raw
records, behind tables that summarized them faithfully. Before believing a
number, read the raw record that produced it. This lives as a standing habit for
orchestrators and leads.

**Attack the spec before freezing it.** The validity oracles went through up to
three adversarial rounds before they were sound. A spec that is frozen first and
attacked later carries its holes into every lane. This lives as a pre-freeze
attack step, adopted as a requirement, with tooling still in progress.

**Prose versus data review.** Green checks did not mean true sentences: a
sentence can cite a real table cell and still claim more than the cell supports.
This lives as a prose-review round before an empirical epic closes. It has run
once for real, and the epic cannot close until a round comes back clean.

**Data invalidation.** Fixed code did not flag the corpora generated before the
fix. This lives as per-row prompt hashes and a stimulus-parity validity claim.
Automatic staleness marking is still a wish, and this release shows why it
matters: its sweep navigability figures are labelled stale by hand.

**Orchestrator theses are not binding without an oracle.** A binding note from
the orchestrator held two errors, and one of them reached a headline. A thesis
handed down in a brief is now a hypothesis unless an oracle backs it. This lives
as a rule on briefs.

**Standing invariants belong in the gate.** Rules that hold for every change,
such as no host paths and no personal emails in tracked files, belong in the land
gate, not in per-landing review. This was added as a gate check after a host
path got past per-landing review.

**Judge first.** Put a runnable thing in front of the real judge before writing
proofs about it; proofs follow and never gate. In the later run, a judge running
the actual command found the bug that green tests had not. This lives as a
binding lead rule.

**Fresh reviewers.** A reviewer who did not write the code reviews every change,
and a regression test must fail for the semantic reason it exists, not because
of a signature error. This lives as review routine.

**Retro loop.** After each run, a fresh agent reviews what happened and files at
most three graded fixes, and the next run measures whether they helped. This
project was its first subject.

**Recorded decisions.** Tier selection is a recorded decision, not a default,
and model names are stated by what actually ran rather than what was requested.

## What this says about the Guild's goal

The Guild's goal is repeatable, layered rigor that turns prototypes into
production-quality output. envelope-shift shows both halves of that sentence.
The prototype layer worked as prototypes do: fast, productive and confidently
wrong in ways it could not see. The bookkeeping layer worked too, and it made the
wrong artifact perfectly reproducible. What turned the artifact into something
worth publishing was the layer above both, independent and adversarial review,
followed by a rebuild that changed what the contract asks.

The lesson is not that the agents were unreliable. They were reliable at
execution. It is that rigor has to be layered on purpose, and that each layer
has to check something the layer below it cannot. A process that only checks its
own bookkeeping will certify its own mistakes. The changes folded forward from
this project are attempts to put that check earlier: in the contract, in the
worker brief and in the habit of opening the raw row, so that less is left for
the adversarial round to find.

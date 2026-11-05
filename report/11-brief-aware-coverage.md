# 11. A proposed fix: brief-aware coverage

> **Status: CURRENT, and a proposal.** Brief-aware coverage is this harness's
> suggestion, not part of the published method. Every figure below regenerates on
> a fresh clone: the pairs from code (`e5_pairs.csv`), the rest from the committed
> section 10 rows (`data/replication/e5_*.csv`).

Sections 5 and 10 show what goes wrong when coverage is used as a reward: it scores
a room against the inventory of its *type*, so the program a brief asks for counts
as extraneous. The obvious repair is to score the room against the inventory of its
*brief*. This section builds that repair in its smallest form and measures it on the
same layouts.

## 11.1 The change

The formula is untouched. Only the inventory it scores against changes, and only
for a room whose brief declares a program
([`metrics/coverage.py`](../src/envelope_shift/metrics/coverage.py),
`coverage_brief`). Two modes are compared:

- **tolerate:** the brief's program types are no longer extraneous. This removes
  the penalty.
- **require:** each program type becomes a required inventory line. This removes
  the penalty, and leaving the program out now costs what leaving out a standard
  line costs.

Nothing else moves: no synonym map, no substitutions, no new parameters. Where a
brief declares no program, both modes are the published score exactly. On every
T0 to T4 row of the replication, 32 per tier, the largest difference from published
coverage is 0 in both modes
([`e5_identity.csv`](data/replication/e5_identity.csv)).

The program list is each envelope's `declared_extraneous`, written by hand and held
out of every prompt. That is the open engineering question this section does not
answer: in production, the list has to come from the brief itself.

## 11.2 The hand-authored pairs

[`report/data/e5_pairs.csv`](data/e5_pairs.csv). In each pair, fulfilment is the
share of the brief's program present: 0.0 for every conventional layout, 1.0 for
every unconventional one.

| envelope | layout | published | tolerate | require |
|---|---|---|---|---|
| t5_kitchen_laundry | conventional | 70.7 | 70.7 | 58.9 |
| t5_kitchen_laundry | unconventional | 52.7 | 62.7 | **68.9** |
| t5_sbed_worknook | conventional | 100.0 | 100.0 | 50.0 |
| t5_sbed_worknook | unconventional | 50.0 | 100.0 | **100.0** |
| t5_pbath_aging_in_place | conventional | 71.4 | 71.4 | 50.0 |
| t5_pbath_aging_in_place | unconventional | 7.1 | 28.6 | **50.0** |
| t5_pbed_nursery | conventional | 100.0 | 100.0 | 50.0 |
| t5_pbed_nursery | unconventional | 50.0 | 100.0 | **100.0** |

Two results, and the first is the more useful:

1. **Removing the penalty is not enough.** Under *tolerate*, the layout that ignores
   the brief still wins the kitchen and the bath and ties the other two. It never
   loses. A reward that only stops punishing the brief gives an optimizer no reason
   to follow it.
2. **Requiring the program flips the incentive.** Under *require*, the layout that
   follows the brief wins three pairs and ties the bath.

The bath ties because of the inventory, not the brief. The standard primary-bath
table expects a tub or shower stall, a shower and a linen cabinet, and it does not
know that a roll-in shower is a shower. That is a vocabulary fix to the table and
is deliberately left out here, so the effect of the brief alone stays readable.

## 11.3 On the models' own layouts

Over the 31 parsed T5 rows of the replication, the Spearman correlation of each
variant with fulfilment
([`e5_t5_correlation.csv`](data/replication/e5_t5_correlation.csv)):

| variant | correlation with fulfilment |
|---|---|
| published | -0.2051 |
| tolerate | 0.0132 |
| require | 0.3221 |

Published coverage leans against following the brief, *tolerate* is indifferent
to it, and *require* leans towards it. Thirty-one rows is a small sample, so read
these as signs, not sizes.

Best-of-16 selection, repeated under each variant
([`e5_bestofn.csv`](data/replication/e5_bestofn.csv), the `ALL` rows), gives the
mean fulfilment of the selected sample:

| arm | pool mean | selected by published | by tolerate | by require |
|---|---|---|---|---|
| opus55 | 0.5833 | 0.5833 | 0.5833 | 0.5833 |
| sonnet55 | 0.5625 | 0.5000 | 0.5833 | 0.6667 |

For `opus55` nothing changes, because every one of its samples for a room furnishes
the same program: there is nothing for selection to choose between. For `sonnet55`
the whole difference is one room. On the aging-in-place bath, selection by published
coverage keeps a sample with none of the program (fulfilment 0.0000), and selection
by *require* keeps one with two thirds of it (0.6667), against a pool mean of 0.2500.
That is one room, not a trend. It is, though, exactly the situation a reward exists
for: a pool that disagrees about the brief, and a metric that decides which way the
policy moves.

## 11.4 What this does and does not claim

It claims that the defect in section 5 is local and cheap to repair: one change to
the inventory a room is scored against, invisible wherever there is no brief, flips
the sign of the incentive on the rooms that have one. It also claims that the
weaker repair, simply forgiving the program, is not a repair for a reward.

It does not claim that this is the right reward. Fulfilment here is exact type
names, so a model that writes `glider_chair` for `glider` is counted as not
furnishing it under every variant. Requiring each program type at the same weight
as a standard line is a choice, like every other unpublished parameter (section 3).
The program list was written by hand. And nothing here, as everywhere in this report,
says anything about GBM. A closed-vocabulary model would avoid the synonym problem,
but it would still need its program read from the brief.

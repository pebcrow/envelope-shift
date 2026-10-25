# 2. Why out-of-distribution evaluation, and why now

The published evaluation holds out 50 rooms from the same corpus of production
homes the decoder learned from. For the question it asks — did this model learn
the distribution it was trained on, well enough to furnish a room a builder
would accept — that is the correct test, and the reported numbers mean what they
say. Nothing here proposes replacing it. The reason to build something beside it
is that the two next steps of section 1 leave that distribution, in different
directions.

## The input moves

Natural-language briefs leave the corpus, and renovation and infill work produce
envelopes a catalog of new-build plans has never had to furnish: rooms that are
not rectangles, not orthogonal, not flat-ceilinged, or entirely ordinary in
shape while being asked to hold a program nobody built a template for. A metric
validated on held-out production rooms has no evidence either way about those.
It may be perfectly fine; the point is that in-distribution evaluation cannot
tell you, because every room it has ever scored came from the same place as the
training data.

So atypicality here is a property of the *input* — the envelope and the brief —
never of the model's answer, which is what makes the ladder a measurement of the
metric's scope rather than of model failure.

## The metric's job changes

The sharper reason is reinforcement learning. A validity check and a reward are
not the same instrument even when they are the same formula: a check has to be
right about the layout in front of it, a reward has to *separate* the layouts in
front of it, and a metric can do the first perfectly while being unable to do
the second at all.

The failure a reward can have that a check cannot is pointing the wrong way.
A check is only asked about the layouts in front of it, and in-distribution
those are the layouts the check was built around. A reward is asked about every
layout an optimizer can reach, including the ones a brief legitimately asks for
and the corpus never contained. If the metric reads what the brief asked for as
an error, the gradient points away from the brief and toward whatever the
metric treats as normal — and in-distribution evaluation, where the brief and
the corpus agree, is the one place that cannot show it.

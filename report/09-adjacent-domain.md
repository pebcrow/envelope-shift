# 9. A note from an adjacent domain

A form-validity checker that cannot see value is not a homebuilding problem. It
is what happens to any automated gate that scores whether an artifact is
well-formed and is then read as scoring whether it is good. I have seen it from
the other side, in browser-game generation. The measurements behind this note
live in a private repository a reader cannot check, so its counts and rates are
omitted here on purpose: what follows is the shape of the finding, not its
numbers.

An earlier go/no-go ran a small batch of prompts through a local generation arm,
a single sample per prompt, with no retries and no best-of-N. The automated gate
passed almost all of them, and it is a real gate: a headless browser load with
page and console error capture, a constraint lint, a visual-overlay probe, and a
structural check for size, closing tags and game-loop wiring. A hand read of
the same artifacts found that none implemented the genre its prompt had asked
for. Most were the same runner-and-dodger fallback shell — a skeleton with
generated glue, not a copied file — and the rest crashed and shipped nothing.

The genre judgement came from reading the artifacts by hand, not from the gate,
and the measurement is narrow: one generation path, whose design forced every
prompt through a fixed skeleton.

The stronger instance is the later one, because there the judge is a shipped
instrument rather than a hand column. A handful of games that had passed the
form-validity gate and been published were rescored by a deterministic
missing-subject gate. It fired on most of them, every firing a true positive
against the bytes, with no false positives on the scored population. One
crossword had published HTML byte-identical to a match-three game. Another
game's requested subjects survived only in its title tag. A third contained no
occurrence of any of its requested subjects anywhere.

None of this is publicly verifiable; it is offered as an analogy, not as
evidence.

The transferable part is not the games. It is that the gate and the goal came
apart without anything in the pipeline noticing, that the gate was correct on
its own terms throughout, and that finding out required a second instrument to
measure the dimension the first did not cover. Coverage, navigability and
overlap & clearance are far better instruments than that game gate ever was. The
argument here is only that they are instruments of the same kind, and the second
has to exist before the first is asked to hand out a reward.

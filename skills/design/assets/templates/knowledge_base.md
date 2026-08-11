# Knowledge base - <experiment name>

The memory of this run. Every strategist reads this before proposing anything,
which is the only thing stopping generation 12 from re-proposing what generation
3 already disproved.

Keep it a **decision log, not a diary**. One entry per strategy attempted. When
it passes ~200 lines, condense dead branches into a single summary line rather
than appending - a knowledge base nobody can read in one pass is a knowledge
base that gets skimmed.

## What we know about the problem

_Filled in during design: where the time goes, what the profile says, what the
domain constrains. Facts, not plans._

- Baseline: `<score>` (noise floor ±`<spread>`)
- Speed-of-light bound (roofline), and how far the baseline sits from it:
- Hot path:
- Known constraints:

## Rival mechanism hypotheses

_Two or three live explanations of where the cost or behaviour comes from.
Design probes to discriminate between them - each probe's outcome should be
incompatible with at least one rival. A single hypothesis becomes a ruling
theory the whole run polishes._

- H1:
- H2:

## Confirmed - reproduced a real gain

One line per strategy:

- `<strategy>` - candidate `<id>`, gain `<number>`. Why it works: `<mechanism>`.

## Rejected - tried, did not help

One line per strategy:

- `<strategy>` - candidate `<id>`, result `<number>`. What it tells us:
  `<inference>`.

The "what it tells us" clause is the valuable one. "Tried loop unrolling, no
change" is worth little; "unrolling did nothing, so the loop is not front-end
bound - look at memory" redirects the next six candidates.

## Dead ends - do not re-propose

- _One line each, with the reason. This section is what makes the run converge
  instead of cycling._

## Open questions

- _Things a measurement could settle but nobody has measured yet._

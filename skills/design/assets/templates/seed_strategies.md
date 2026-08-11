# Seed strategies - <experiment name>

Three to six starting directions, written during design so generation 1 explores
instead of guessing. The idea: priming the search with domain knowledge is the
cheapest quality improvement available, and it costs one conversation.

**Most of these should come from the prior-art search, not from your head.** A
strategist reasoning only from the code in front of it will rediscover the
well-known technique badly, three generations in, and will never propose the
architectural change - because that is not what local reasoning about existing
code produces. Every entry below should cite where it came from.

Make them **genuinely different from each other**, not three phrasings of the
same idea. The point is to plant several lineages, so that when one collapses
the run still has somewhere to go. Include at least one *transfer* - an adjacent
domain's state of the art adapted to this problem - and one *hybrid* that
mix-matches elements from different approaches; that is where invented solutions
usually come from. Generate them by crossing the prior art with the
inventive-principles checklist
(`skills/evolve/references/inventive_principles.md`): the Ideal Final Result and
the four separations, applied to the experiment's stated contradiction.

## Prior art

_Fill this in first. Fastest known implementation of this exact operation; any
library solving it under the same constraints; the adjacent problems whose
techniques transfer; what the literature says the cost currency is; and the
published negative results, which are free evaluations._

One entry per technique found:

- `<source>` - `<technique>`. Would transfer here if: `<condition>`.

## Technique coverage ledger

_Enumerate the **families** of known approaches to this operation - not the
sources, the techniques - and give each one a status. Keep it current for the
whole run; the synthesizer refreshes it, and the closing report quotes it._

The point is that **a blank is visible**. A run reports "we tried twelve
candidates", which sounds thorough and says nothing about whether the obvious
technique was ever considered. This ledger is what lets the owner ask "was X
tested?" and get an answer with evidence instead of a recollection. Every status
must name the candidate id, probe, or constraint behind it.

One numbered entry per technique family:

1. `<technique family>` - status: `confirmed`, `refuted`,
   `excluded by constraint`, `untested`, or `not applicable`. Evidence:
   `<candidate id, probe, or constraint>`.

Statuses, and the distinction that matters:

- **confirmed** - tried, measured, it helps. Cite the candidate and the number.
- **refuted** - tried, measured, it does not help *here*. Cite the number and
  the mechanism, because "did not help" without a reason gets re-proposed.
- **excluded by constraint** - cannot be used: an invariant, the language, the
  target, an owner decision. Cite the constraint. This is not the same as
  refuted and must not be conflated with it - and check the exclusion is not
  broader than its reason (ruling out "lookup tables" because a 40 KB table is
  unacceptable silently rules out a 200-byte one too).
- **untested** - nobody has tried it. **A blank entry is a finding, not an
  oversight to hide.** If the remaining budget will not cover it, say so in the
  final report rather than letting silence imply coverage.
- **not applicable** - the technique solves a different problem. Say why.

Two things to enumerate that runs routinely miss, because local reasoning about
existing code does not produce them: the **textbook answer to the cost currency
you identified** (if the loop is latency-bound, multiple accumulators; if
branch-bound, branchless forms; if front-end bound, unrolling), and the
**structural** alternatives (a different algorithm, a different data layout, a
different place to draw the fast/slow line). Reaching the end of a run without
either tried *or* explicitly excluded means the search only ever polished one
shape.

## Format

### S1 - <short name>

- **Hypothesis**: what change, and why it should help.
- **Expected effect**: rough magnitude, and on which metric.
- **How we'd know**: what the numbers or the profile would show if it worked.
- **Risk**: what it might break, or which invariant it strains.

______________________________________________________________________

### S1 -

### S2 -

### S3 -

______________________________________________________________________

## Explicitly out of bounds

_Approaches the user has ruled out, with the reason - a rewrite in another
language, a dependency they will not take, an unsafe block. Naming them here
stops strategists spending candidates on proposals that would be rejected on
sight._

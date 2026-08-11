# Diagnosing a run

Someone shows you a run that is not going well. Work from the evidence in
`evolution.json` / the dashboard, not from the story they tell you about it.

## Order of investigation

1. **Is anything scoring at all?** Failure rate first. A run where 70% of
   candidates die is not an optimization problem, it is a plumbing problem, and
   the leaderboard is meaningless until it is fixed.
2. **Is the best result real?** Gain vs noise floor, then read the winning diff.
   Do this before diagnosing "plateau" - a plateau after a fake win is a
   different conversation.
3. **Is the population still searching?** Distinct lineages, and whether recent
   strategies differ from earlier ones in substance or only in wording.
4. **Only then, the trajectory.** When improvements stopped, and what the last
   real one was.
5. **What is left in the budget.** Every recommendation is conditional on it.
   Advice to "force novel-policy generations" is useless to a run with three
   candidates remaining - that one needs a restart with a fixed harness, and
   saying "tune it" instead wastes the remaining budget confirming what the data
   already shows.

## Symptoms

For each symptom: the most likely cause, then what to do.

- **High failure rate (>40%).** Cause: strategies too large; the editable region
  lacks the context needed to change it safely; a missing dependency in the
  candidate copy. Do: shrink the strategy scope to one change; widen the evolve
  block to include what must move together; read three failure insights before
  theorizing.
- **Everything scores identically.** Cause: the evaluator is not measuring the
  edited code - wrong path, stale build, cached artifact. Do: deliberately break
  the program; if the score does not move, the harness is disconnected.
- **One huge early win, then nothing.** Cause: the "win" is a measurement
  artifact. Do: re-score that candidate in a fresh checkout; read the diff for a
  shrunk workload or a skipped test.
- **Steady tiny gains, all below noise.** Cause: climbing noise. Do: raise
  repeats until the spread is smaller than the gains you care about, then
  discard the run's conclusions and restart.
- **Plateau with 1–2 lineages.** Cause: population collapse. Do: force
  novel-policy generations; reseed from the original with a stated different
  approach.
- **Plateau with many lineages, low variance in scores.** Cause: the space
  really is exhausted at this granularity. Do: widen the evolve block, change
  the representation, or stop - stopping is a legitimate finding.
- **Reviewer rejects nearly everything.** Cause: review criteria are stricter
  than the objective admits, or the strategist is aiming at a forbidden
  shortcut. Do: read three rejections; if they are all the same class, that
  constraint belongs in the gate where it costs nothing.
- **Scores improve, humans dislike the code.** Cause: maintainability was never
  in the objective. Do: add it as a constraint and rerun; it cannot be patched
  in afterwards.

## Reading the evidence honestly

Tag every claim you make about someone's run:

- `[OBSERVED]` - a value you **read from a specific field**, and could point at.
- `[INFERRED]` - derived from observed values, with the derivation stated.
- `[SPECULATED]` - a hypothesis. Say so; do not launder it into a finding.

The tags are only worth anything if they are earned, and a wrong tag is worse
than no tag: it lends a number the authority of having been checked. Anything
you computed, estimated, eyeballed from a trend, or half-remembered from two
paragraphs ago is `[INFERRED]` at best. Before writing `[OBSERVED]`, be able to
name the field it came from. This failure is not hypothetical - it is the
observed way this convention goes wrong, and it turns a diagnosis into a
confident fiction.

**Check the clock before you use it.** Rates, cadences, stalls and "the run has
been dead for six hours" all rest on timestamps, which are the least trustworthy
field in any run log: they may be synthetic, non-monotonic, written at record
time rather than measurement time, or in a different zone. Sort by them and
confirm they increase before deriving anything from them. If they do not, say so
and drop every throughput claim - an ordering argument from a broken clock is
worse than no argument, because it sounds specific.

Two disciplines that prevent most bad conclusions:

**Null hypothesis first.** Before claiming a mechanism worked, say what the data
would look like if it were absent. "Novel-policy generations produced 3 of the
top 5" means little until you know novel policy ran on half the generations - at
which point it means nothing at all.

**Sample-size floor.** The ~30 floor governs claims about run *dynamics* -
trends across candidates or generations, "novel policy outperforms greedy".
Below it, call the trend a hint and give the n; runs of tens of candidates
support "worth another look", not "we found that". The floor does not govern the
gain claim itself - that is decided by the noise floor and repeats, and a winner
confirmed against both is a result at any candidate count.

## Deciding to stop

Stopping well is most of the skill. Stop when:

- The last improvement above the noise floor was many generations ago and the
  population is diverse - the space is genuinely exhausted at this granularity.
- The gain so far is worth banking and further gains look sub-noise.
- The failure rate says the harness is wrong; fix it and restart rather than
  spending budget on a broken measurement.

Then do the closing ritual, which is not optional if anyone is going to act on
the result: re-measure the winner in a clean checkout **and report the gain from
those fresh measurements, never from the score that won selection** - that is
the split-sample rule (`fitness_design.md` § *Selection bias*) - score it on
held-out inputs, read the diff line by line, and write down the gain **with its
noise floor** next to it.

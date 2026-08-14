# Designing the fitness function

The fitness function is the whole experiment. Everything else is machinery for
climbing it, so a flaw here is not a bug you fix later - it is the thing the run
will spend its entire budget exploiting.

## The one convention: always maximize

Fix the direction once, at the evaluator, by negating anything you want small:

```python
score = -median_nanoseconds     # minimize latency
score = -bytes_of_binary        # minimize size
score = -rmse                   # minimize error
```

Every downstream part - leaderboards, parent selection, plateau detection - then
works without a per-experiment sign flag. The alternative (a `direction` field
honored in six places) is a bug that only shows up as "the run got steadily
worse and nobody noticed for an hour".

## Correctness is a gate, not a term

The tempting design is one score with a correctness penalty:

```python
score = speedup - 100 * tests_failed     # don't
```

It looks equivalent and is not. A weighted penalty is a *price*, and a search
process will pay it whenever the speedup exceeds it. Make correctness
categorical instead:

```
tests fail  → score is null, program is dead, record why
tests pass  → score is the measurement
```

Null rather than a large negative number, too. Sentinel values like `-1e12` leak
into means, medians and plots, and then someone reports an average.

Run the *project's own* test suite, not a reimplementation. A bespoke check
written for the experiment is a second thing that can be wrong, and it will be
wrong in the direction that lets candidates through.

## Partial credit - when the objective *is* coverage

The gate above is binary on purpose: a wrong answer is dead. But some objectives
are genuinely a coverage fraction - a solver that handles more instance classes,
a parser that accepts more of a corpus, a heuristic that satisfies more
constraints. Scoring those all-or-nothing starves the search of gradient: every
candidate scores zero until one leaps the whole distance, which is not how
search finds anything. There, score the fraction:

```python
score = cases_passed / cases_total     # over a FIXED case set
```

Rules to follow:

- The case set is **fixed and lives outside the evolve block**. A fraction over
  a shrinkable denominator is the shrink-the-work hack with a percent sign on
  it.
- Hard invariants stay a gate - no crash, well-formed output, no timeout.
  Partial credit applies only to the dimension where partial success is
  genuinely worth something to the user.
- Expect plateau-by-easy-cases: candidates harvest the easy cases, then stall.
  Stage the cases by difficulty or weight the hard ones, and record in the
  knowledge base *which* cases the frontier is stuck on - that is the run
  telling you where the problem actually lives.
- Never use partial credit to soften a correctness gate that should be binary.
  "Passes 96% of the tests" on code that must be correct is not an optimization
  result; it is a bug report.

## What to measure, per goal

- **Speed** - score: negated median wall time or cycles over N repeats. The
  trap: one sample; measuring a warm cache; the compiler eliding dead work.
- **Memory** - score: peak RSS, or allocation count. The trap: steady-state peak
  hides transient spikes.
- **Size** - score: stripped binary or section bytes. The trap: measuring the
  debug build.
- **Accuracy** - score: error on a **held-out** set. The trap: evaluating on the
  data the candidate can read.
- **Combinatorial quality** - score: the objective itself (density, count,
  cost). The trap: accepting infeasible solutions the checker doesn't test.
- **Throughput** - score: ops/sec at fixed input. The trap: letting the
  candidate shrink the input.

## Composite objectives

When two things matter, prefer a **constraint plus a single objective** over a
weighted sum: "minimize time *subject to* memory ≤ 2× baseline" is far harder to
game than `0.7*time + 0.3*memory`, because a weighted sum always has a corner
where one term collapses and the other pays for it. Express the constraint as
part of the gate.

If the trade-off curve itself is the deliverable - the owner cannot state a
bound because the exchange rate between the two axes is exactly what they want
to see - declare an objective tuple instead of a scalar (`objectives.axes` in
`experiment.json`; the design skill and the evaluator contract carry the
mechanics). Selection then runs on noise-aware Pareto dominance and `best`
returns the front for the owner to pick the knee. Two disciplines come with it:
cap the tuple at two (at most three) axes and keep everything else a guard,
because a front the owner is meant to read must be readable; and confirm only
the *picked* point(s) with the split-sample ritual, not every front member - a
holdout applied across the whole front rebuilds the multiple-comparisons problem
it exists to solve.

**But do record and surface the extra metrics.** Counter-intuitively,
*measuring* several metrics tends to improve the one you actually select on:
programs that excel under different criteria have structurally distinct logic,
so showing a variety of "good" programs to the strategists stimulates more
varied candidates. So the rule is not "measure one thing" - it is **select on
one scalar, but measure and show many**. The extra metrics pay for themselves as
diversity pressure and as evidence at review time, and because nothing selects
on them, they are not something a candidate can trade against.

## Evaluate in stages, not all at once

Do not run the full benchmark on every candidate. Most candidates are broken or
obviously worse, and finding that out is cheap:

- **Stage 1** - the correctness gate plus a fast, low-repeat measurement on a
  small input. Most candidates die here, at a fraction of the cost.
- **Stage 2** - the real benchmark at full repeats, only for what survives.

Generalize it into an **evaluation cascade**: test cases of increasing
difficulty, where a candidate advances only if it does well enough on all
earlier stages, and every new candidate is evaluated at small scale first to
filter out faulty programs cheaply.

The budget you save is not a nice-to-have. Redirected into repeats on the
survivors, it is usually what makes the difference between a noise floor wider
than the effect and one narrow enough to resolve it.

**Validate the screen before you trust it.** Staging only helps if the cheap
stage *ranks candidates the same way* the expensive one does. Where it does not

- a small input that fits in cache when the real one does not, a short run that
  misses the behaviour you care about - the cascade confidently discards your
  best candidates and you never find out, because they were never measured
  properly. This is the documented failure mode of every multi-fidelity method:
  they are *worse than no staging at all* when low-fidelity performance does not
  predict high-fidelity performance, because they spend the budget confidently
  on the wrong survivors. Score ~10 candidates on both stages once and check the
  rank correlation. Twenty minutes, and it is the difference between a cascade
  that multiplies your budget and one that quietly throws away the answer.

A cascade can be mis-tuned in both directions: too small a first-stage budget
prematurely kills good candidates, too large a one runs poor candidates for
longer than it takes to know. For a run of tens of candidates, plain two-stage
screening is the right default - the elaborate hedging schemes buy insurance you
pay for and rarely need.

**With a fixed budget and more than a handful of candidates, drop the worst
rather than measuring everyone equally.** Two short, proved schemes:

- **Successive rejects** - split the budget into *K*−1 phases and eliminate the
  empirically worst candidate at the end of each, so survivors accumulate
  progressively more measurements. Half a page of code, and it spends the budget
  where the decision is still open.
- **A capped race** - drop any candidate whose mean falls more than
  `√(2·log(nK/δ)/t)` below the leader, and continue until one survives. **The
  cap is not optional**: when the two best candidates have near-equal true
  means, a race never terminates on its own.

Both beat spending the budget uniformly, and both beat the classic bandit
algorithms here - see the note on bandits under *Selection bias* below.

## Noise: the invisible ceiling

Timing measurements on a shared laptop routinely vary 5–15% run to run. If your
evaluator returns one sample, a hill-climber will happily climb noise for hours
and hand you a "12% improvement" that vanishes on re-measurement.

The fix is cheap and non-negotiable for anything timing-based:

- Take **≥5 repeats** and record the **median**, plus the spread.
- **Define the noise floor once, as a spread, not a difference.** It is the
  spread of repeated *evaluations* of the unmodified seed - at least three, one
  of them in a fresh process minutes later, because back-to-back runs share a
  thermal state and a page cache and measure within-session noise only. The gap
  between just two baseline runs is one draw from that distribution and
  understates it about half the time. Take the wider of the within- and
  between-session figures, and re-establish it when the session changes. **Any
  improvement smaller than the noise floor has not been demonstrated.**
- Record the spread in each candidate's metrics too; the report takes the wider
  of the baseline floor and what candidates actually show.
- Re-measure the final winner in a fresh process before believing it.
- Quiet the machine as much as is practical: fixed CPU governor, no build
  running in the background, pinned core if the platform allows.

When the floor is stubbornly wide, or when repeated baselines *drift* in one
direction as the machine warms, stop measuring absolutes. Time the candidate and
the untouched reference back to back in the same process on the same input,
alternate the order across repeats, and score the **ratio**. Drift and
background load hit both arms and divide out. This routinely turns a ~7% floor
into a sub-1% one - the difference between an experiment that can resolve a real
3% win and one that cannot. Absolute timing has the additional hazard that it
silently favours whichever candidates ran while the box was cold, so part of
every score is a timestamp.

State the noise floor in every result you report. "+3.1% (noise floor ±4%)" is a
real non-result; "+3.1%" is a claim you cannot defend.

**The floor also sizes the budget, before any of it is spent.** The spread of a
median shrinks roughly as 1/√repeats, so resolving the smallest gain worth
acting on (δ, pre-registered - `pre_mortem.md`) against a per-repeat spread σ
costs on the order of (σ/δ)² repeats per evaluation. If that, times the
candidate count, overruns the budget, the run cannot answer the question as
framed - and the correct response is to change the measurement (the ratio
above), the input, or the question, not to run it anyway and argue about the
result.

## Selection bias: the maximum of N noisy scores is inflated

This is not a risk, it is arithmetic, and it gets worse as the run gets bigger.
Forty candidates is forty chances for a mediocre program to draw a lucky
measurement, and the leaderboard is sorted partly by who got luckiest. Plan the
correction before the run, not after the celebration.

**The fix, and it has a proof behind it: select on one measurement set, report
from another.** Collect two disjoint sets per candidate, (a) and (b). Choose the
winner by `argmax` over set (a), then **report that winner's score from set
(b)**. That estimator is still biased, but it *provably never overestimates* the
true maximum. (It is the same construction as double Q-learning, the
reinforcement-learning cure for the same maximization bias.)

This is the formal warrant for "re-score the winner on fresh measurements", and
it also settles the *right* way to do it: not "re-run the winner and average
everything together" - averaging the confirmation back into the selection data
throws the guarantee away - but "choose on one set, report the other".

**How much inflation to expect.** For N roughly independent trials with normally
distributed scores,

```
E[max] ≈ mean + √var · ( (1−γ)·Φ⁻¹(1−1/N) + γ·Φ⁻¹(1−1/(N·e)) ),  γ ≈ 0.5772
```

Plug in your noise floor and your candidate count and you get a concrete number
for how much of your best score is selection luck. **N is bracketed, not known**

- the formula assumes independent trials, and children of one parent are not
  independent, so the candidate count overstates N while the lineage count
  understates it. Compute the correction at both ends and quote the range; when
  the verdict flips between them, use the candidate count, because the
  flattering end of the bracket is the one that ships a fake win.

**Confirm once, on the single winner.** A confirmation stage does not rescue you
if you run it per candidate: apply a holdout twenty times and false positives
are no longer unlikely, they are expected. Re-confirming every promising
candidate just rebuilds the multiple-comparisons problem inside the stage that
exists to solve it.

**And do not compute per-candidate p-values.** Testing 40 candidates against one
baseline and reporting the max inflates the false-positive rate; the usual
answer is to raise the significance hurdle for the number of trials *attempted*
(which, unlike in most fields, an evolutionary run actually knows). You almost
never want this machinery. Use the split-sample confirmation on the winner, and
reach for a false-discovery-rate correction (Benjamini–Hochberg) only if you are
reporting several survivors as a set - Bonferroni is needlessly severe for that
job.

**Do not reach for UCB or Thompson sampling to pick candidates.** Three
independent reasons: they minimize *cumulative* regret while you want one good
final recommendation (a different objective, with different optimal strategies);
successive halving empirically beats them on exactly this shape of problem; and
their confidence arguments assume a fixed, stationary arm set, while your
candidate pool is regenerated every generation. Keep bandits, if at all, for the
*meta* level - which mutation policy or prompt template to draw next - where the
arm set is small and stable.

## Held-out inputs

Split the benchmark inputs the way you would split a dataset: the evaluator
scores on one set, and you keep a second set the loop never sees. At the end,
re-score the winner on the held-out set. A candidate that wins on one and not
the other did not find an optimization, it found your benchmark.

A held-out set survives one decision. If the outcome table sends you back to fix
the benchmark and rerun (`pre_mortem.md`), draw a fresh held-out set for the
rerun - a holdout consulted on every iteration has become part of selection,
which is exactly the leak it existed to prevent.

Randomize what you safely can per evaluation - seeds, input order, generated
data - with a fixed distribution rather than fixed values. Special-casing a
distribution is much harder than special-casing a constant.

**Record the seed with the score.** Data regenerated per evaluation and then
forgotten makes the evaluation unreproducible: nobody can re-derive the number
later, and a suspicious result cannot be re-run on the input that produced it. A
fixed default seed plus the seed actually used, stored in the candidate's
metrics, costs one field.

## Sanity checks before you spend the budget

Run these four, in this order. Each has caught a broken experiment:

1. **Score the unmodified seed.** That is the baseline. Record it in
   `experiment.json`; every later claim is relative to it.
2. **Score the seed again.** The difference between the two runs is your noise
   floor, before any candidate exists.
3. **Score something deliberately broken** - return a constant, delete the loop
   body. It must be rejected by the gate. If it scores well, the gate is not
   connected to the thing you care about, and you have just saved yourself a
   day.
4. **Score something known to be better** - any change you are confident
   improves the metric. The harness must register it as a win above the noise
   floor. Check 3 proves the harness can say no; this proves it can say yes. A
   harness that rejects everything looks rigorous, is worthless, and hides until
   the budget is gone. When the space is unmapped enough that no known
   improvement exists, invert it: inject a **calibrated regression** - a
   busy-wait or an extra pass that should cost ~10% - and confirm the harness
   resolves a loss of about that size. It tests the same property, resolution of
   a real effect of known size, and it is always constructible.

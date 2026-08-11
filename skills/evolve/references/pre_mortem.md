# Planning the experiment: what will go wrong, and what you'll conclude

Two questions, asked *before* the budget is spent, prevent most wasted runs:

1. **It is three days later and the result is garbage. Why?**
2. **For each outcome the run could produce, what will we conclude?**

The first is a pre-mortem. The second is pre-registration. Neither takes more
than twenty minutes, and skipping them is why so many runs end in an argument
about what the number meant rather than a decision.

______________________________________________________________________

## 1. The pre-mortem

Imagine the run finished and the result is worthless. Write down the reasons.
The list below is what that exercise usually turns up; work through it and keep
the ones that apply.

### Systemic - the experiment answers the wrong question

- **The metric is a proxy nobody actually wants.** You optimized p50 latency and
  the complaint was p99. You optimized the microbenchmark and the batch didn't
  move. State the *user-visible* quantity and how your metric connects to it; if
  you cannot draw that line in one sentence, you are about to optimize an
  artifact.
- **Amdahl was never checked.** If the target is 18% of total time, the whole
  exercise is capped at 1.22× no matter how good the search is. Compute the
  ceiling before committing budget, and tell whoever asked. The roofline is the
  same question asked of the hardware - bandwidth × bytes moved, issue width ×
  irreducible instructions; a baseline already near that bound makes the
  experiment unwinnable as framed.
- **The unit of analysis is wrong.** Measuring per call when the caller batches,
  per document when cost is per byte, per request when the tail is what hurts.
- **Uncontrolled co-variation.** The candidate changed the algorithm *and* the
  data layout *and* the allocation pattern. It got faster; nobody can say which
  part did it, so nothing transfers to the next problem.
- **No stopping rule.** Without one agreed in advance, a run stops when someone
  gets bored, and "we ran out of patience" gets reported as "the space is
  exhausted".
- **The metric moves mid-run.** Someone adds a term, or fixes the benchmark,
  halfway. Every score before and after is now incomparable, and the leaderboard
  silently mixes them.
- **The budget is spent before the harness is validated.** The single most
  expensive mistake available. Validate first - baseline, baseline again, broken
  candidate, known-good candidate - and only then spend.
- **The winner is unmergeable.** Nobody set a constraint on diff size,
  readability, API stability or `unsafe`, so the best candidate is a 400-line
  unreviewable win that will never land.

### Measurement - the number does not mean what it says

- **No noise floor.** The first thing to establish and the most commonly
  skipped. Measure the *same* program twice before believing any difference.
- **Drift.** Repeated baselines trending one way as the machine warms means
  every score is partly a timestamp, and candidates evaluated late are
  penalized. Score a paired ratio against the reference instead.
- **Dead-code elimination.** The result is never consumed and the compiler
  deletes the work. Consume it, checksum it, assert on it.
- **Caching across measurements.** Memoization, a warm page cache, a JIT that
  has already specialized. Fresh process, fresh input, or a probe that detects
  the second-call collapse.
- **Module-cache reuse.** Score several candidates in one process and the
  language's import cache serves the first candidate's code forever. The symptom
  is dozens of different candidates all scoring within noise.
- **Timer resolution and overhead.** At a few hundred nanoseconds, the clock
  read is a measurable fraction of what you are timing. Measure a batch.
- **Measurement bias from the environment.** Code layout, link order,
  environment-variable size and directory depth can shift performance by more
  than the effect being studied - enough to reverse a conclusion, on every
  architecture and compiler it has been tested on. Score a paired ratio, or
  randomize the irrelevant details across measurements so their effect becomes
  noise instead of a systematic offset. See `perf_harnesses.md`.
- **Selection on noise.** Taking the max over N noisy candidates is biased
  upward by construction; the more candidates, the worse. This one is guaranteed
  to happen - it is not a risk, it is arithmetic - so plan the confirmation
  stage now.

______________________________________________________________________

## 2. Pre-registration: decide the interpretation first

Fill this in before the run. It takes ten minutes and it is the difference
between a result and a debate.

For each outcome the run can produce: what we conclude, then what we do.

1. **Gain ≫ noise floor, holds on held-out and on the worst input shape.**
   Conclude: real improvement. Then: review the diff, merge, record the
   mechanism.
2. **Gain > noise but fails held-out or one shape.** Conclude: overfit to the
   benchmark profile. Then: fix the benchmark to include that shape, rerun
   **with a fresh held-out set**.
3. **Gain inside the noise floor.** Conclude: no demonstrated improvement. Then:
   report the non-result; do not rerun hoping.
4. **No gain, diverse population, budget spent.** Conclude: space exhausted at
   this granularity. Then: widen the evolve block or change representation.
5. **No gain, one lineage.** Conclude: search collapsed, question unanswered.
   Then: fix diversity and rerun - this is not evidence about the problem.
6. **High failure rate.** Conclude: harness or scope problem. Then: fix it;
   discard the run's conclusions.
7. **Implausibly large gain.** Conclude: measurement bug until proven otherwise.
   Then: investigate before telling anyone.

Two commitments worth writing down explicitly, because they are the ones people
renege on under pressure:

- **The smallest gain worth acting on.** If a 2% win would not change any
  decision, say so now - then a run that produces 2% is a non-result by prior
  agreement, not by post-hoc disappointment. This number also sizes the budget:
  with the noise floor it fixes the repeats each evaluation needs
  (`fitness_design.md` § *Noise*), and if that is unaffordable the run is
  unwinnable as framed - knowable now, for free.
- **What would make us abandon the approach.** Name it in advance. Otherwise a
  run that should have stopped at 40 candidates runs to 400, because each
  individual decision to continue looked reasonable.

______________________________________________________________________

## 3. Reading the result properly

When the number arrives, the useful question is not "is it good" but **"what
else would produce this number?"** Work through:

- **The null.** What would the trajectory look like if every candidate were
  functionally identical and only noise varied? Greedy selection over noise
  produces a rising curve that flattens - which is exactly what a successful run
  also looks like. Distinguish them with the noise floor, not the shape. For a
  result anyone will act on, measure the null instead of imagining it: score a
  dozen copies of the unmodified seed and plot the running max. That curve is
  what selection-on-noise produces here, on this machine, and the real run has
  to clear *it*, not zero.
- **The base rate.** On problems chosen because they were amenable, and with an
  industrial compute budget behind it, this class of system *matches* the known
  state of the art roughly three times as often as it beats it. Matching is the
  normal outcome, not the disappointing one. Calibrate expectations to that
  rather than to whatever headline result prompted the run.
- **The mechanism.** A win you cannot explain is a win you cannot defend or
  transfer. If nobody can say *why* it is faster - in terms of cache misses,
  instruction count, allocations, algorithmic complexity - treat it as
  provisional and go find out.
- **The counterfactual cost.** Would an afternoon with a profiler have found it?
  If yes, the conclusion includes that, and it should change how the next
  problem is approached.

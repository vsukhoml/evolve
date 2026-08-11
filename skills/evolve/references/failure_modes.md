# How these runs go wrong

Sorted by how often they waste someone's week. The first two account for most of
it.

## 1. Reward hacking - the score is real, the improvement is not

A search process optimizes what you measured, which is never quite what you
meant. This is not the model misbehaving; it is the loop working correctly
against an under-specified objective.

The catalogue, roughly in order of how often it shows up in practice:

- **Weakening the check.** Editing, skipping, or `#[ignore]`-ing a test;
  loosening a tolerance; deleting an assertion. Structurally prevented by
  keeping the gate outside the editable region - see below.
- **Shrinking the work.** Reducing iteration counts, sample sizes, input
  lengths, or precision, so the benchmark measures less work rather than faster
  work.
- **Caching across measurements.** Memoizing on a key the harness reuses, or
  hoisting the computation into a static initializer the timer does not cover.
- **Special-casing the benchmark input.** A lookup table for the exact inputs; a
  branch on a magic size. Catch it with held-out inputs and randomized data.
- **Correct at test scale, wrong at benchmark scale.** Its own class, and the
  most dangerous one, because it defeats the defence you are relying on: the
  candidate is exactly right on the small inputs the test suite uses and cuts
  corners above some threshold - samples every fourth element past 1000, takes
  an approximate path only for large batches. Every test passes. The only things
  that catch it are checks that run at *benchmark* scale: full output equality
  against a reference on every timed call, or a checksum the benchmark input
  makes non-trivial. A test suite written by a human for human-written code
  never covers this, because no human writes it.
- **Dead-code elimination.** The result is never consumed, the compiler removes
  the whole computation, and the candidate reports a ~0ns loop. Guard with
  `black_box` / volatile sinks / checksum-of-result assertions.
- **Editing the harness.** The candidate modifies the evaluator, the timer, the
  config, or the runner script. Keep all four outside the editable region; and
  remember the loop executes model-written code unattended, hundreds of times,
  so anything that could reach the network, the wider filesystem, or spawn
  processes belongs in a container.
- **Exploiting an LLM judge.** When fitness is a model's opinion, candidates
  drift toward whatever that model rewards - length, confident phrasing,
  fashionable terminology - with no change in substance.

**Structural defences**, in order of strength:

1. The gate, the evaluator, the benchmark data and the timing harness live
   **outside** the region a candidate may edit, and the diff is checked against
   that boundary before scoring.
2. Every candidate is evaluated in a **fresh copy** of the program directory, so
   a candidate cannot leave state behind for the next one.
3. Held-out inputs, randomized per-evaluation data, and a final re-score of the
   winner in a clean checkout.
4. A **reviewer that reads the diff**, not just the score, and can veto. Its
   verdict has to be able to override a leaderboard position, or it is
   decoration. Note what the veto costs: a reviewer inside the selection loop is
   an LLM judge whose blind spots are now search targets too - the same hazard
   as LLM-as-fitness, one step removed. The deterministic gate stays underneath
   it, and its error rate gets measured with seeded fakes (the runner skill's
   calibration protocol), never assumed.
5. Run the whole thing in a container or a VM if the code being evolved does
   anything with the filesystem, the network, or subprocesses.

The tell that should always stop you: **an improvement much larger than the
domain makes plausible.** A 40× speedup on mature code is a bug in the
measurement roughly nineteen times out of twenty. Investigate before
celebrating; the cost of being wrong in public is far higher than the cost of
one more check.

## 2. Noise mistaken for progress

Covered in `fitness_design.md`, repeated here because it is the second-most
common way a run produces a confident non-result: without repeated measurements
and a stated noise floor, a timing-based experiment cannot distinguish a real 3%
win from a warm cache. The report is not "we improved 3%", it is "we cannot yet
distinguish 3% from nothing".

## 3. Population collapse

After a few greedy generations every candidate descends from one ancestor. The
leaderboard still moves - by hundredths - and the run has stopped searching,
because every strategist is now looking at the same code and proposing the same
next tweak.

Symptoms: distinct lineages drops to 1–2; strategies read as paraphrases of each
other; improvements shrink monotonically toward the noise floor.

Fixes: force novel-policy generations; seed a fresh lineage from the original
program with an explicitly different approach; protect new lineages from
competition for a fixed number of evaluations so they get a chance to mature
before being out-scored by a polished incumbent. Islands - semi-isolated
subpopulations with occasional migration - are the next step up, and only worth
their knobs (island count, subpopulation size, migration probability and
interval) on measured collapse, not on principle.

**Before adding a diversity archive, check the descriptor is quality-aligned.**
Keeping the best program per cell of a behaviour grid (MAP-Elites and its
relatives) only helps when the descriptor correlates with quality - algorithmic
family, data-structure choice, complexity class. An *unaligned* descriptor,
which is usually the kind of diversity that sounds appealing, measurably
degrades these algorithms and on hard problems can prevent them finding the best
solution at all. So: if you cannot name a descriptor plausibly correlated with
quality, do not bolt one on; and if you carry only one extra axis, carry the one
you would refuse to merge over. Pure novelty search has a matching limit - it
applies no optimization pressure once a solution exists, so use it to *generate*
and then optimize on the objective.

## 4. Knowledge-base rot

The knowledge base is supposed to stop the loop from re-proposing dead ideas. It
fails in two directions: too thin (every generation rediscovers the same three
failures) or too fat (it grows past what fits usefully in a prompt and the
strategist skims it).

Keep it as a decision log, not a diary: one line per attempted strategy - what
was tried, what happened, the number, and the *inference*. Prune confirmed-dead
branches into a single summary line. If it exceeds a couple of hundred lines, it
needs condensing, not appending.

## 5. Unreproducible best

The run ends, the winner scores beautifully, and nobody can rebuild it because
the working directory moved on. Snapshot the exact program with its score at the
moment it is measured - cheap insurance, and the reason the evaluation step here
copies the candidate directory.

## 6. Optimizing something nobody will merge

The winning diff is 400 lines of unrolled, unreadable, comment-free code that
beats the baseline by 6%. It is a real improvement and it will never be merged,
because nobody can maintain it.

If maintainability matters, put it in the objective as a constraint - a diff
size ceiling, "public API unchanged", "no new unsafe", "must pass the linter" -
and enforce it in the gate. Deciding this after the run means throwing the run
away.

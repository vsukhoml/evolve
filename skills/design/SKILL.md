---
name: design
description: >-
  Turn a natural-language optimization goal into a complete, self-contained
  evolutionary optimization experiment - spec, seed program with EVOLVE-BLOCK
  markers, evaluator harness, correctness gate, knowledge base, and an
  evolution database - verified by scoring a baseline and proving the gate
  rejects a deliberately broken candidate. Language-agnostic (Rust, C/C++, Go,
  Python, anything with a benchmark). Use this skill when the user says
  "design an experiment", "set up an experiment to optimize X", "I want to
  evolve this function", "build me a harness to search for a faster
  implementation", or hands over code plus a target metric and asks how to
  score candidates. Produces the directory that evolve:runner then
  drives. For advice on whether to run one at all, use evolve instead.
---

# Experiment design

You turn a goal into an experiment directory that another skill can run
unattended for hours. Everything that would otherwise be an argument at 2am -
what counts as correct, what the number means, what a candidate may edit - gets
decided here and written down.

## The three phases

**Phase 0 (Frame)** interrogates the problem itself. It ends when the problem
statement has survived `references/problem_framing.md` and the conclusions are
written down - or when the conclusion is that this is the wrong problem, which
ends the engagement successfully and cheaply. **Phase 1 (Clarify)** is
conversation. It ends when `experiment.json` exists. **Phase 2 (Build)** needs
no further input; if you find yourself wanting to ask something, Phase 1 was not
finished. It ends when the seven sanity checks pass.

Do not create code files during Phases 0 and 1. The spec is the contract between
the phases, and writing code before it exists is how experiments end up
measuring something nobody agreed to.

______________________________________________________________________

## Phase 0 - Frame

Before clarifying *how to measure*, establish *that this is the thing worth
measuring*. The most expensive failure in this work is upstream of any harness -
a well-designed experiment answering a question nobody needed answered - and no
downstream check can catch it. Work through `references/problem_framing.md` with
the user; five questions carry most of the weight:

- **What is the problem behind the request?** "Make X faster" is a chosen
  solution, not a problem. Ask what becomes possible, or stops hurting, if it
  succeeds - and confirm the target is actually the bottleneck of *that*, with
  the Amdahl arithmetic, before anything else.
- **What is the null alternative?** Do nothing, buy hardware, cache the caller,
  adopt a library, relax the requirement. The run competes with the cheapest
  acceptable one of these, not with the baseline.
- **What domain owns this problem, and what is it called?** The name unlocks the
  prior-art search and the domain's own impossibility bounds; a problem with no
  name can only be re-derived, badly.
- **How will the solution be used?** Who runs it, at what scale, maintained by
  whom, merged by whom - the constraint set, the complexity budget, and the
  invariants fall out of these answers rather than being invented.
- **What do we believe, and how is each belief held?** Label every load-bearing
  premise measured / reported / inferred / assumed, each with what checking it
  costs now versus what discovering it mid-run costs. Check the cheap decisive
  ones before designing anything; the high-importance, low-confidence rows
  become the run's reconnaissance agenda.

The conclusions become the `framing` block when `experiment.json` is written
(format in the reference). If framing ends at "wrong problem", "the null
alternative wins", or "no scalar exists", stop and say so plainly - that outcome
costs an hour and saves the budget, and it is the design skill working, not
failing.

______________________________________________________________________

## Phase 1 - Clarify

Fill in these. Ask about the ones the user has not already answered; infer the
rest from their code and say what you inferred.

- `objective` - one sentence: what gets better. If unclear: ask; everything else
  follows from it.
- `metric` - the exact number, in units, negated if smaller is better. If
  unclear: propose one from the goal and have them confirm.
- `evaluator.command` - how to measure it. Usually you write this in Phase 2.
- `correctness_gate` - the command that proves a candidate still works. If
  unclear: their existing test command; if they have none, that is the first
  thing to build.
- `targets` - which files, and which regions inside them, may change. If
  unclear: default to the one function they named.
- `invariants` - what must stay true, both imposed (public API, no `unsafe`,
  diff size) and the problem's own (round-trips, conservation, bounds). If
  unclear: ask directly; these are cheap to state and impossible to retrofit.
- `baseline_score` - filled in Phase 2 by scoring the untouched seed.
- `budget` - candidates and wall-clock the user will spend. If unclear: default
  40 candidates, and say what that costs in time.

Two questions worth asking explicitly, because their absence causes most bad
experiments:

1. **"What would a cheating solution look like?"** Their domain knowledge names
   the shortcut faster than you will find it. Whatever they say becomes an
   invariant or a gate.
2. **"How noisy is this measurement on your machine?"** If they do not know,
   Phase 2 will find out - but asking primes them to expect a noise floor in the
   result rather than a clean number.

### Decide what to evolve

Before choosing the evolve block, choose the **abstraction**. The same problem
can be attacked at three levels, and the choice matters more than any tuning you
will do later:

- **The solution itself** - evolve the function that does the work. Right for
  most engineering problems: optimizing a hot loop, a parser, a kernel.
- **A constructor** - evolve a function that *builds* the answer. Better for
  problems with highly symmetric solutions, where the construction is far
  shorter than the object it produces.
- **A search algorithm** - evolve a procedure that *finds* the answer within a
  fixed compute budget, better for non-symmetric problems; or co-evolve the
  searcher and the solution together.

Say which you chose and why, in one line, in `experiment.json`. If the target is
"find a better packing / schedule / assignment" rather than "make this code
faster", you are probably in the second or third case and defaulting to the
first will quietly cap what the run can discover.

### Establish the constraint set - and ask when you cannot infer it

Do this before the prior-art search, because it is what the search gets filtered
through. Write the constraints into `invariants`, in the user's words where
possible.

Some you can read off the code: `no_std`, `const fn`, MSRV, no-`unsafe` policy,
dependency list, target platforms, binary-size or allocation limits, required
accuracy or rounding semantics, public API surface.

Others you cannot, and guessing is how a run produces a technically-excellent
result nobody will merge:

- Is a new dependency acceptable, and under which licences?
- Is `unsafe` allowed anywhere, or behind a feature flag?
- Is a large lookup table acceptable, and how large is large?
- Must this stay portable, or is x86-64 enough?
- Is exact bit-compatibility required, or is a different-but-correct answer
  fine?
- How much added complexity is worth how much speed? Is there a diff-size or
  readability limit?
- Which existing behaviours are load-bearing versus incidental?

**Ask the user about anything material you cannot infer.** One round of
questions costs a minute; discovering in the closing review that the winning
candidate is unshippable costs the whole run. Phrase them as "would X be
acceptable" rather than abstractly, and offer the trade explicitly - *"a 40KB
table buys roughly 2×; is that acceptable in this crate?"* - because the answer
is usually a judgement about the product, not about the code.

Two failure modes to avoid in both directions. Do not invent constraints that
were never stated and quietly narrow the search. And do not treat a soft
convention as hard: if a large win is blocked by something the owner could
simply decide to relax, surface it as a decision rather than burying it as a
dead end.

### Identify the problem's own invariants - and make the gate enforce them

The constraints above are what the *owner* imposes. A second kind lives in the
problem itself: properties any correct answer must have, whatever algorithm
produced it. Harvest them deliberately -

- **Identities and round-trips** - `decode(encode(x)) == x`,
  `parse(print(x)) == x`, applying the inverse recovers the input.
- **Conservation** - totals balance, probabilities sum to 1, every input element
  is accounted for in the output, nothing created or dropped.
- **Bounds and monotonicity** - output within a provable range; more input never
  yields less output; a sort's output is a permutation of its input.
- **Symmetry** - order/permutation invariance, scale or translation invariance
  where the domain guarantees it.
- **Feasibility** - for constructions: every constraint satisfied, checked
  exactly (integer or rational arithmetic where possible), never with the
  candidate's own epsilon.
- **Metamorphic relations** - properties across *related* runs, for when no
  oracle exists: `f(perm(x)) == f(x)` for order-invariant code, `f(x ∪ y)`
  against `f(x)` and `f(y)`, scaling laws, a count that must grow monotonically
  under a superset input. Checkable on random inputs with no reference
  implementation, and nearly impossible for a gamed candidate to satisfy by
  accident.

Then **compile each one into an executable acceptance check** - in the gate, or
inside the timed harness - rather than leaving it prose. Problem invariants are
the strongest correctness instrument the experiment has, for a reason the test
suite is not: they hold on *every* input, including the randomized and held-out
ones, and they need no reference implementation. A candidate that is wrong only
at benchmark scale slips past example-based tests; it cannot slip past a
conservation check asserted on the benchmark input itself. And when the
equivalence policy is a tolerance band or different-but-valid, invariant checks
are most of what "correct" still means.

Write each invariant into `invariants` next to the command or assertion that
enforces it, and keep both outside the evolve block.

### Name the central contradiction

State the problem's core trade as one line in `experiment.json` -
`"contradiction": "improving X worsens Y"`. Faster but bigger, faster but less
accurate, simpler but slower: naming it gives every strategist the axis to work
with the inventive-principles checklist
(`skills/evolve/references/inventive_principles.md` - Ideal Final Result, the
four separations), instead of drifting into micro-variations of the seed. A run
whose contradiction nobody stated tends to rediscover the weighted compromise
the fitness function was designed to avoid.

### Compute the speed-of-light bound

Before spending the budget, ask what physics allows: memory bandwidth × bytes
that must move, issue width × instructions that cannot be removed, the passes
over the data that are irreducible. Twenty minutes of roofline arithmetic
answers the only question that matters - how much headroom exists. Baseline at
90% of the bound: the experiment is unwinnable as framed; reshape it (move less
data, change the algorithm class) or do not run it. Baseline at 20%: the gap
*is* the reconnaissance agenda - name what is eating the other 80% as rival
hypotheses for the run to discriminate. Record the bound in `notes`; the
reviewer uses it too - a gain that exceeds the roofline is not implausible, it
is impossible, and the measurement is wrong by theorem rather than by smell.

### Decompose the request into a metric set

The user says "make it faster". That is one *stated* goal wrapped around several
unstated ones, and the unstated ones are the reason a technically-winning
candidate gets rejected at merge. Break the request down before you write the
evaluator, and write the breakdown into `experiment.json`:

- **One total order.** Usually a single fitness scalar - the thing the search
  maximizes. When the trade between exactly two (at most three) axes is
  genuinely unknown and the deliverable is the frontier for the owner to pick
  from - performance versus code size is the canonical case - declare an
  objective tuple instead: `objectives.axes` in `experiment.json`, every axis
  higher-is-better, `score` staying the first axis, ranking by noise-aware
  Pareto dominance (`references/evaluator_contract.md` § *Multi-objective
  experiments*). Prefer the constraint form whenever the owner can state a bound
  \- it is harder to game and cheaper to interpret; a front is for when they
  cannot. Everything not on an axis stays a monitored metric or a guard, exactly
  as below.
- **Monitored metrics with thresholds.** Everything else the user would trade
  the scalar against, each with a bound and an owner. Typical set: **numerical
  accuracy** (ULP or relative error, worst case not mean - for any kernel where
  a faster answer may be a different answer), **correctness class** (exact,
  bit-identical, or within tolerance - say which), **code size / data size**,
  **allocations and peak memory**, **stack depth**, **compile time**, **binary
  or diff size**, **portability**, and **maintainability proxies** such as
  non-comment lines, function count, or duplicated decision tables.
- **Which of those are guards.** A guard is reported, never scored, at weight
  0.0. It exists to catch a regression, not to be optimized.

The rule that makes this work: **anything you would refuse to merge over is a
metric, and it must be measured from the first candidate.** If it is only in
your head, the search cannot see it, the leaderboard will rank against it, and
you will discover the conflict at the end while holding a fast candidate you do
not want.

A run that skipped this had one scalar (nanoseconds) and three unstated goals -
keep it small, keep it maintainable for a solo owner on a long horizon, keep it
exact. The fastest candidate grew the hot function 4.5x and duplicated a
five-mode rounding table; the merge argument then had to be reconstructed by
hand from line counts nobody had recorded, twice, with the first attempt using
raw lines instead of code lines and reaching the wrong conclusion. Two of those
goals were in the project's own written conventions the whole time.

For accuracy specifically: if the operation is numeric and the candidate may
reassociate, widen, narrow, or approximate, then an accuracy metric is not
optional - a search *will* find speed by quietly spending precision, and a
correctness gate built from equality on a few test values will not notice. Work
through `references/numeric_accuracy.md` before any code exists. It fixes five
things: the equivalence policy (bit-identical, tolerance band, or
different-but-valid - written into `invariants`), identical FP flags for
baseline and candidates, the tolerance band treated as the reward-hacking
surface it is, safe-math guards outside the evolve block, and deliberately
conditioned benchmark inputs - plus how to name *where* a candidate went
non-finite, because `score: null` teaches the run nothing.

### Choose the instrument set, not just the metric

The fitness scalar answers *did it get better*. It never answers *why*, and
"why" is what the next generation is steered by. So decide up front which
instruments the harness carries, the same way you would equip a lab bench, and
build them in Phase 2 alongside the timer. The menu - timing with spread,
disassembly of the hot region, static microarchitecture analysis (`llvm-mca`),
hardware counters, allocation and size accounting, cross-build-flag checks - is
in `references/instruments.md`, along with the run whose every mechanism finding
came from an agent improvising `objdump` mid-candidate because the harness
carried only a timer. Pick from what the problem actually makes load-bearing.

Two rules make these pay:

1. **Record them per candidate, in the evaluator's `metrics` dict**, beside the
   score. They cost nothing at evaluation time, they land in the database, and
   they are what lets the synthesizer correlate *across the whole population* -
   "every candidate that won removed instructions per digit" is a finding the
   leaderboard alone cannot produce.
2. **State which instrument settles which question**, in `experiment.json`. Then
   a strategist with a mechanism hypothesis knows how to test it for pennies
   instead of spending a whole candidate.

### Triage the change space: what a script searches, what the LLM searches

An LLM loop is a *structure* search. It is a poor numeric optimizer, and it is
worse than poor at multi-dimensional numeric optimization: it will wander a
continuous subspace forever, and every step costs a full evaluation - minutes of
agent time wrapped around seconds of measurement.

So **every experiment partitions its change space before generation 1, and
nothing is left un-triaged**:

- **Parametric** - anything expressible as a value in a space file. Searched by
  a standalone script with no LLM in its loop. It never gets an LLM candidate.
- **Structural** - code shapes nobody has written yet: a different algorithm, a
  different data structure or memory layout, a different decomposition of the
  problem. This is the only thing worth paying agent turns for.

This is a required planning step, not a "if there happen to be knobs" step. A
parameter left un-triaged does not stay neutral: it gets discovered by the loop
in generation 4 and burns candidates on arithmetic a sweep would have settled in
minutes, and every candidate that touched it before then is now confounded.

**The test for which side something falls on.** A change is parametric if you
can name its domain in advance and a script can apply it without understanding
it - substitute a value, rebuild, re-measure. If applying it requires deciding
*what code to write*, it is structural. Two traps:

- **A structural choice with a small fixed set of alternatives is parametric.**
  "Linear scan vs binary search vs a lookup table" is three values of one
  categorical axis, not three generations. If all the variants already exist or
  are each an afternoon to write once, write them once and let the script pick.
  The LLM's contribution was inventing the third option, not choosing among
  them.
- **A knob whose domain you cannot state is not yet parametric.** "Tune the
  heuristic" is structural until someone names the range. Naming it is design
  work, and doing it now is cheaper than discovering mid-run that the loop has
  been sampling it blind.

Record the triage in `experiment.json`, and for every structural item write one
sentence on *why* it cannot be a value. That sentence is where a knob most often
turns out to be one after all.

Then design the parametric search itself, following
`references/parameter_search.md`: **enumerate** every knob (numeric constants,
mode flags, build and toolchain settings, discrete variants, the search's own
meta-parameters - targets hide more than the author remembers), **reason** about
each response's shape before choosing a method, **pick** the algorithm from the
method list to match that shape rather than habit, and **size** the space before
picking anything clever - a full grid that fits the budget beats any sampler.
The same file carries the four rules that stop a tuning plan producing confident
nonsense, starting with proving the metric is *sensitive* to a knob before
tuning it.

Write the result into `experiment.json` as a **tuning plan**: for each
parameter, its domain, the expected response and why, the method, the budget,
and how the choice will be validated. Then *keep it out of the evolutionary
loop* - the loop searches structures, the tuner searches numbers, and mixing
them wastes both.

### Take the LLM out of the loop when the search is parametric

An LLM-driven generation costs minutes of agent time per candidate to wrap
seconds of measurement. That price buys something real when the search is over
*structures* - code shapes nobody has written yet. It buys nothing when the
search is over *parameters*: booleans, categoricals, numeric constants, build
flags. There the model is a slow, expensive random-number generator.

So whenever the triage above found anything parametric, **build it as a single
long-running search process** and let the model watch. Same evaluator, no agent
in the iteration. In a real run each candidate took 10–20 minutes of agent time
around ~30 seconds of measurement; the same wall clock as a standalone sweep is
tens to hundreds of evaluations instead of one.

**This is a Phase 2 deliverable, not something to reach for later.** If the
triage found a parametric subspace, Build produces three files alongside the
evaluator:

- `tuning/space.json` - the axes and their domains, straight out of the plan.
- `evaluator/eval_params.py` - the parameter-mode evaluator, from
  `assets/templates/eval_params.py`. It takes
  `--params PARAMS.json --output-file OUT.json` (a *different* contract from the
  candidate evaluator's `--program-dir`), applies the values to a copy of the
  program, and then **calls the candidate evaluator's own `evaluate()`** rather
  than scoring anything itself. Two hand-written scorers drift - a repeat count
  here, a warmup there - and the moment they do, the sweep's winner cannot be
  folded back in and compared, because you have two experiments. Delegating
  makes the agreement structural instead of something to remember.
- the driver - `assets/templates/tune.py`, copied into `.ae/` and adapted.

**Run the sweep before generation 1**, and fold its winner into the seed. The
loop should start from the best configuration of the current structure, not
rediscover it. Otherwise generation 1 through 3 spend agent turns on arithmetic,
and worse, every structural comparison made before the sweep is confounded: a
candidate that looked like a 4% win may have been a better constant that any
structure would have enjoyed.

The counterpart rule is what protects the LLM's budget. **An agent turn is for
inventing a shape that does not exist yet** - a different algorithm, a different
data layout, a fusion of two passes, a representation nobody has tried. If a
candidate's diff is a changed constant, a flipped flag, or a swapped variant
from a set you could have enumerated, the triage was wrong and the loop is doing
the tuner's job at a hundred times the price. Send it back to the space file and
say so in the knowledge base.

`assets/templates/tune.py` is a working driver - stdlib only, adapt it. What
matters is not the file but the seven properties that make interrupting an
unattended run cost nothing - one process owns the search, every result flushed
and fsynced, the best point written atomically, restart resumes, one progress
line per evaluation, it stops itself, signals exit clean - listed in
`references/parameter_search.md` beside the four things the structure does not
excuse. The last of those is the one that bites: a tuner maximizes over noise
more eagerly than an LLM does simply by taking far more samples, so the winner
still needs the closing ritual. Run the driver in the background and check in on
a human cadence - the model's contribution is choosing the space and the method,
noticing when the progress log says something is wrong, and folding the result
into the knowledge base. Not turning the crank.

### Find the prior art for the *problem* - before any candidate exists

Not the prior art for evolutionary search; the prior art for the thing being
optimized. Almost every target has a literature, a fastest-known implementation,
and a set of near-neighbour problems whose solutions transfer. Search for it and
write down what you find, in `seed_strategies.md`, with citations.

**Verify what you cite; do not recall it.** Literature review is the *dominant*
failure point in agent-driven research pipelines - a higher failure rate than
experimentation or writing - and it is what undermines the grounding of every
hypothesis downstream of it. That is this step. A technique remembered from
training is a hypothesis about the literature, not a citation: fetch the source,
read the actual implementation, and record what you *saw*. Mark anything
unverified as unverified in its entry. The cost asymmetry is stark - a wrong
recalled technique sends a generation down a path that a five-minute fetch would
have closed. A real run's knowledge base was wrong twice from exactly this
species of error: a number inherited rather than re-derived, in both cases
steering a whole generation.

Start with the cheapest source: a cross-experiment `lessons.md` beside the
experiment directories, if earlier runs left one - its dead ends and harness
fixes are free evaluations that already happened on this machine. Then ask, in
this order:

1. **What is the state of the art for this exact operation?** Name the fastest
   known implementation and read how it works.
2. **Who has solved this under the same constraints?** A competitor library with
   the same `no_std` / `const` / no-dependency / portability limits has already
   paid for the search you are about to run.
3. **What are the adjacent problems?** The inverse operation, the same operation
   at a different width, the same shape in another domain. Their techniques
   usually port with small changes. This is where inventions mostly come from -
   not ideas from nothing, but an adjacent domain's state of the art adapted to
   a new application, or elements of several known approaches mix-matched into
   one. Budget the seed strategies accordingly: at least one should be a
   *transfer* and one a *hybrid*.
4. **What does the literature say the cost currency is?** Papers state which
   effect dominates - branch misprediction, dependency-chain latency, table
   size, memory bandwidth. That tells the strategists what to aim at.
5. **What has been tried and does NOT work?** Published negative results are
   free evaluations.

This is the highest-return twenty minutes in the whole process, and it is the
step most often skipped, because generating plausible candidates *feels* like
progress. It is not: a strategist reasoning from first principles will
rediscover the well-known technique, badly, three generations in - while the
genuinely non-obvious idea (usually an architectural one, like "optimistic fast
path for the common case with a fallback") never surfaces at all, because it is
not what local reasoning about the existing code produces.

**Then filter it against your constraints, and expect to reject the winner.**
The fastest known implementation is usually fastest *because* it spends
something you cannot spend. Run every technique through the local constraint set
before it becomes a seed strategy:

- **Portability** - SIMD intrinsics, `unsafe`, runtime CPU dispatch, x86-only
  code. Fastest-in-benchmark is frequently unshippable in a portable library.
- **Space** - the 40KB lookup table that wins a microbenchmark is a non-starter
  in an embedded target, and may lose in a real program anyway once it is
  competing for cache with everything else.
- **Dependencies and licence** - read the fast library, do not link it.
- **Language/compile-time limits** - `const fn`, `no_std`, MSRV, borrow rules.
- **Accuracy and semantics** - a faster algorithm with different rounding,
  different error identity, or a narrower domain is a different function.
- **Maintainability** - a 400-line unreadable win nobody will merge is not a
  win. That belongs in the invariants.

So the useful output is rarely "adopt the SOTA". It is usually one of: the
*architecture* transfers while the hot-loop trick does not; the second-place
technique is the one that fits; or a constraint-respecting hybrid - the fast
path from one source, the fallback from another. Record the rejected ones with
the constraint that killed them, in the "explicitly out of bounds" section: that
stops a strategist proposing AVX-512 in generation 3, and it is a one-line save
each time.

Be pragmatic about which constraints are real. "We've always done it this way"
is not a constraint; `no_std` is. If a genuinely large win is blocked by a soft
constraint, say so and let the owner decide - that is a finding, not a dead end.

The failure mode is specific and worth naming: without this step a run explores
*variations of the code in front of it*, when the win is often a *different
shape of solution entirely*. No amount of population diversity fixes that,
because every lineage starts from the same seed.

Seed `seed_strategies.md` from what you find, one entry per technique, each
citing its source and saying explicitly what would have to be true for it to
transfer here. Those become generation 1's proposals instead of guesses.

**And scan the seed for catalogued anti-patterns before generation 1.** A
deployed fleet-scale optimizer (provenance in the README) earns most of its
savings not from novel optimizations but from finding *known* anti-patterns -
unnecessary copies, redundant map lookups, missing reserves, missing moves,
needless allocations - and applying the catalogued fix. Walk the evolve block
against the menus in `skills/evolve/references/lowlevel_perf.md` and fold the
obvious catalogued fixes into the seed, exactly as the parameter sweep's winner
is folded in and for the same reason: a candidate compared against a seed still
carrying textbook anti-patterns is confounded - part of its "win" is a fix any
structure would have enjoyed - and the loop otherwise spends agent turns
rediscovering what a checklist already knew.

### Pre-register the interpretation

Before any code, write down what each possible outcome will mean - what counts
as success, what counts as a non-result, what would make you abandon the
approach, and the smallest gain that would actually change a decision. Ten
minutes here is the difference between a result and an argument, and it has to
happen before anyone has seen a number.

Load `skills/evolve/references/pre_mortem.md` (from the consultant skill) and
work through its pre-mortem list and outcome interpretations with the user. Put
the conclusions in `experiment.json` under `interpretation` and `risks`. The one
question that most often changes the design: *"it is three days later and the
result is garbage - why?"*

If the objective cannot be made into an honest scalar, say so now and stop. That
conversation belongs to the `evolve` skill.

Write the spec, echo it back in two or three lines, and move on.

### `experiment.json`

```json
{
  "name": "faster-interval-lookup",
  "objective": "Reduce time to classify a batch of 10k values against an interval table",
  "metric": "negated median nanoseconds per batch (higher is better)",
  "contradiction": "faster lookup pushes the table bigger; it must stay L1-resident",
  "targets": ["program/src/lookup.rs"],
  "source_map": {
    "program/src/lookup.rs": { "file": "src/lookup.rs", "lines": "118-164" }
  },
  "invariants": [
    "public function signatures unchanged",
    "no new unsafe blocks",
    "results bit-identical to the baseline on all test inputs"
  ],
  "correctness_gate": "cargo test --quiet",
  "gate_timeout_seconds": 600,
  "evaluator": {
    "command": ["python3", "evaluator/evaluate.py"],
    "timeout_seconds": 300,
    "repeats": 5
  },
  "tuning_plan": {
    "automated_search": {
      "space": "tuning/space.json",
      "command": ["python3", "evaluator/eval_params.py"],
      "method": "grid",
      "sizing": "3 x 4 x 2 = 24 points x 3 repeats x 20s = 24 min; full grid fits, so no sampling",
      "run_before_generation_1": true,
      "parameters": [
        { "name": "TABLE_BITS", "domain": [8, 9, 10], "expected_response": "unimodal - bigger table, fewer probes, until it leaves L1", "sensitivity_checked": null, "validation": "confirm winner on evaluator/holdout/" }
      ]
    },
    "structural_only": [
      { "what": "the probe sequence itself", "why_not_a_value": "each variant is different code, not a value - no domain can be named in advance" }
    ],
    "resolution": "cannot tune finer than the noise floor; state it once measured"
  },
  "baseline_score": null,
  "noise_floor": null,
  "budget": { "max_candidates": 40, "parallel": 3 },
  "notes": "Held-out inputs live in evaluator/holdout/ and are never scored during the run."
}
```

`tuning_plan` is not optional. If the triage found nothing parametric,
`automated_search` is `null` and `structural_only` carries the reason - an
absent key reads as a step nobody did.

`measurement` is optional and is where the **parallelism plan** lives. Classify
every piece of the evaluation at design time - it decides both the lock modes
and how much the budget's `parallel` actually buys:

- **Timed** (wall clock, cycles, latency, throughput) - machine-exclusive. Two
  timed measurements on one machine corrupt each other silently, multithreaded
  benchmarks worst of all. One at a time, machine-wide; the harness enforces it.
- **Untimed** (numerical accuracy, code size, output quality, feasibility, the
  correctness gate) - parallel-safe *against each other*, never against a timed
  measurement: untimed work still costs cores. These run under a shared lock -
  any number together, all waiting while someone times.

`"measurement": {"machine_exclusive": false, "why": "..."}` declares the whole
experiment untimed (everything runs shared - say why). With a cascade, plan per
stage: an untimed correctness screen carries `"machine_exclusive": false` in its
stage entry and runs shared in parallel, while only the timed final stage takes
the exclusive lock. That is where cascade parallelism pays: for an untimed
experiment `parallel` scales almost linearly; for a timed one it only
parallelizes strategists, implementers, gates, and screens, and the timed stage
always queues.

`objectives` is optional and declares a multi-objective experiment:

```json
"objectives": {
  "axes": ["neg_median_ns", "neg_code_bytes"],
  "noise_floors": {"neg_median_ns": 0.5, "neg_code_bytes": 0},
  "hypervolume_ref": {"neg_median_ns": -200, "neg_code_bytes": -8192}
}
```

`score` stays the first axis, the evaluator must emit every axis
(`references/evaluator_contract.md` § *Multi-objective experiments*), and
`evolve_db.py best` then prints the Pareto front instead of a leaderboard.
`hypervolume_ref` - a point worse than anything acceptable on both axes -
enables the dashboard's front-progress scalar; without it the front is tracked
but its growth is not summarized.

`repeats` defaults to 5 for anything timing-based. One sample cannot distinguish
a 3% win from noise, and a hill-climber fed noise will climb it.

______________________________________________________________________

## Phase 2 - Build

### The directory

```
<experiment>/
  experiment.json        the spec above
  .ae/                   evolve_db.py, evolve_run.py, evolve_report.py (copied from this skill)
                         + tune.py whenever the triage found a parametric axis
  program/               the evolving copy - never the user's working tree
  evaluator/             harness, benchmark inputs, held-out inputs
                         + eval_params.py, the --params/--output-file evaluator
                           the sweep drives (same score, different entry point)
  tuning/                space.json (the axes), then results.jsonl, best.json,
                         progress.log - written by a standalone search process
                         with no LLM in its loop. Absent only if the triage
                         found nothing parametric and said why
  knowledge_base.md      what has been tried and what it taught
  seed_strategies.md     3–6 starting directions, so generation 1 is not blind
  evolution.json         the database (created by `evolve_db.py init`)
  generations/           per-candidate snapshot + evaluation.json
  README.md              how to run it, what the number means
```

**Copy the target code into `program/`. Never evolve the user's working tree.**
Candidate code is model-written, gets executed hundreds of times, and is wrong
by design most of the time - it does not belong anywhere near files the user has
not committed. Integration back into their tree is a separate, reviewed step at
the end.

**Record provenance as you copy.** For each copied region, write the user-tree
path and line range into `source_map` in `experiment.json` at the moment of the
copy. Written now, integration at the close is a mechanical, reviewable patch to
a named location; reconstructed later from memory, it is an error-prone diff
hunt through a tree that has meanwhile moved on.

`program/` must build and run on its own. If the code depends on the wider repo,
either vendor what it needs or make `program/` a thin crate/module that the
evaluator builds in place; imports that reach back into the original source tree
break the moment a candidate is evaluated in a copy.

### Marking what may change

Wrap the editable region with markers, exactly:

```
# EVOLVE-BLOCK-START
...
# EVOLVE-BLOCK-END
```

Use the language's comment syntax (`//` for Rust/C/Go). The spelling matters -
underscores instead of hyphens is the most common way this silently stops
working.

See `references/evolve_blocks.md` for how much to enclose. The short version:
enough that a change can be made coherently, never the tests, the timing
harness, the benchmark data, or the gate.

### The evaluator

Invoked as `<command...> --program-dir DIR --output-file OUT`, writing:

```json
{
  "score": 12345.6,
  "metrics": {"median_ns": 81.0, "instructions": 4210},
  "insights": [{"label": "stdout", "text": "..."}]
}
```

`score` is `null` for any failure - never a large negative sentinel, which would
pollute every average downstream. Full contract, including the NaN rule and a
working template, in `references/evaluator_contract.md` and
`assets/templates/evaluator.py`.

**Prefer a cascade to a single evaluator.** Most candidates are broken or
obviously worse, and the full benchmark is the most expensive way to discover
that. Declare stages of increasing cost; a candidate reaches the next one only
if it clears the previous:

```json
"evaluator": {"stages": [
  {"name": "screen", "command": ["python3", "evaluator/screen.py"],
   "timeout_seconds": 60, "repeats": 1, "promote_if_score_at_least": -60000},
  {"name": "full", "command": ["python3", "evaluator/evaluate.py"],
   "timeout_seconds": 300, "repeats": 5}
]}
```

Stage 1 should be small-input and low-repeat, and must still check correctness -
the cheapest thing to reject is a candidate that computes the wrong answer fast.
Only the **last** stage's score is recorded and ranked; earlier stages are
filters, and their noisier numbers must never rank anything. Screened-out
candidates are reported separately from failures, so a high elimination rate
reads as the cascade working rather than as a broken harness.

The point is not just speed. The budget a cascade saves, redirected into repeats
on the survivors, is usually what makes the noise floor narrow enough to resolve
the effect you are looking for. For how to spend a fixed budget across many
candidates - racing, successive rejects, and why the maximum of N noisy scores
needs a split-sample correction - see
`skills/evolve/references/fitness_design.md`.

**Validate the screen as part of the design gate.** A cascade whose cheap stage
ranks candidates differently from the real benchmark discards your best work
silently. Make the stage-1 workload a *scaled-down version of the real one*, not
a different one, then check: score a handful of candidates on both stages and
confirm the ordering broadly agrees. If it does not, fix the screen before the
run - this is the one cascade failure that leaves no evidence behind.

### Wiring it up

```bash
mkdir -p <experiment>/{program,evaluator,generations}
AE=$(find ~/.claude/plugins ~/.gemini/config/plugins ~/.codex/plugins \
       ~/.grok/plugins .agents/plugins -path '*evolve*/skills/design/assets/ae' \
       -type d 2>/dev/null | head -1)
cp -r "$AE" <experiment>/.ae
python3 <experiment>/.ae/evolve_db.py init --experiment <experiment>
```

### First, on a new machine: verify the install

Before the gate proper, confirm the scripts and the discipline both work. Two
minutes, and it separates "my experiment is broken" from "my Python is broken"
--- a distinction that is expensive to make later, mid-run, with a candidate in
flight.

```bash
python3 .ae/evolve_db.py init --experiment .          # creates evolution.json
python3 .ae/evolve_db.py stats --experiment .         # prints zeros, does not throw
python3 .ae/evolve_report.py --experiment . --json    # renders with no programs
```

All three must run clean on an empty experiment. If `evolve_report.py` cannot
render an empty run it will not render a broken one either, which is exactly
when you will need it most.

### The gate: seven sanity checks

Phase 2 is done when all seven pass. Run them in order and report the numbers.

Checks 1-4 ask whether the harness measures consistently and discriminates in
both directions. Checks 5-6 ask whether it measures the *right thing* --- and
those are the failures nothing downstream can catch, because a search process
will happily optimize a metric that is pointed slightly wrong and hand you a
confident, well-measured, useless answer. Check 7 asks whether the right
*instrument* is pointed at each part of the problem.

1. **Score the untouched seed.** Record it as `baseline_score`.

   ```bash
   python3 .ae/evolve_run.py --experiment . --candidate-dir program --id seed --policy seed
   ```

2. **Score it again** (as `seed-recheck`). The difference between the two runs
   is the noise floor, before any candidate exists. Report it, and record it as
   `noise_floor` in `experiment.json` - the dashboard's "gain is inside the
   noise" check takes the wider of this and the spreads candidates show later.
   If it is larger than the improvement the user hopes for, stop and fix the
   harness - the experiment cannot answer their question yet. If the gap is
   wide, see *Score a ratio, not an absolute* below before giving up on the
   design. In a multi-objective experiment, record a floor **per axis** into
   `objectives.noise_floors` from the same two runs - dominance treats per-axis
   differences inside these floors as equal, so an axis with no declared floor
   silently claims perfect resolution.

   **Then score it a third time in a fresh process, ideally minutes later, and
   record that spread too - it is usually the bigger number.** Two runs
   back-to-back share a thermal state, a page cache and a binary layout, so they
   measure within-session noise and nothing else. A real run measured 0.463
   between sessions on byte-identical source against a within-session floor of
   0.25, which silently made every cross-session comparison in that run
   undecidable, and a probe nearly reported a 0.385 "win" because of it. Record
   the larger figure as `noise_floor`; the smaller one flatters the experiment
   and answers a question nobody asked.

3. **Break something on purpose** in a scratch copy - return a constant, empty
   the loop body - and score it. It **must** come back invalid. If a broken
   program scores well, the gate is not connected to what the user cares about,
   and finding that out now has saved the entire budget.

   Then do it again, harder: build a candidate that **passes the project's own
   test suite and is still wrong at benchmark scale** - samples every fourth
   document above some size, takes a fast path only for large inputs, memoizes
   on a key the harness reuses. `return {}` is caught by anything; this is the
   shape a search process actually produces, because it is the shape that
   scores. If your harness only catches the first kind, it has not been tested.
   Whatever catches this one - full output equality on every timed call, a
   second-call-collapse probe - is the check that is actually load bearing, and
   it belongs in the evaluator rather than the test suite.

4. **Plant a known-good candidate** - a change you are confident is a real
   improvement, even a small one - and confirm the harness *sees* it as a win
   above the noise floor. Check 3 proves the harness can say no; this one proves
   it can say yes. A harness that rejects everything looks rigorous and is
   worthless, and you will not discover that until a whole budget has been spent
   finding nothing.

5. **Audit the benchmark's inputs against production's.** Checks 1–4 ask whether
   the harness measures *consistently*; this one asks whether it measures *the
   right thing*, and it is the check whose absence does the most damage, because
   nothing downstream can detect it. Produce three things:

   - **The distribution comparison.** Histogram the real workload's inputs on
     whatever dimensions drive cost (length, size, density, cardinality) and put
     the benchmark's shapes on the same axis. A run that skipped this scored
     four synthetic shapes that were all *longer than 99% of real input*, ranked
     a technique first that is 13.8% slower on real data, and invalidated a
     whole generation of conclusions when the shapes were rebuilt. Deriving
     shapes from a harvested corpus costs an afternoon; discovering the mismatch
     in generation 3 costs the generations.
   - **The blind-spot list.** Name the input families the metric does *not*
     contain, explicitly, in `experiment.json`. The same run had no shape where
     the input carried more precision than the output type keeps - so the metric
     was structurally unable to see a 35% regression there, and a reviewer found
     it by hand three generations later. You will not enumerate every blind
     spot, but the ones you can name stop being invisible.
   - **A source for every weight.** Each weighted shape cites where its weight
     came from: measured call frequency, or an explicit product decision. A
     shape that exists so something "must not collapse" is a **guard**, and a
     guard belongs at weight 0.0 - reported, never scored. Weight given for
     guard reasons is how 0.20 of a metric ends up spent on input lengths that
     never occur in production, which then decides a merge.

6. **Mutation-test the oracle, one invariant at a time.** Check 3 proves the
   harness rejects *a* broken candidate. It does not prove the harness enforces
   *each* property you claim it enforces. For every invariant in
   `experiment.json`, plant a mutant that violates only that invariant, and
   record **which instrument catches it** - the project's test suite, the
   differential oracle, or a dedicated probe. Two lessons from a real run: two
   mutations of a load-bearing constant passed the project's own `cargo test`
   and were caught only by one bespoke probe in the evaluator; and that probe's
   comment claimed it covered three configurations while the code ran one,
   leaving the other two unguarded against exactly the failure it existed to
   catch. Both were found by accident, late.

   Write the resulting invariant → instrument list, one line per invariant, into
   the knowledge base. It tells every later reviewer which guarantees are
   actually machine-checked and which are prose, and it is the difference
   between "the fuzz passed" and knowing what the fuzz was capable of failing. A
   differential test that has never been shown to fail is not evidence.

7. **Confirm the change space is fully triaged.** Every axis of variation the
   experiment intends to explore is assigned to exactly one instrument:
   automated search or the LLM loop. This check asserts the *assignment* is
   complete, not that the sweep has finished running.

   Walk the seed's evolve blocks and read out every constant, flag, threshold,
   capacity and build setting inside them, plus the variants named in
   `seed_strategies.md`. For each, point at where it is handled:

   - listed as an axis in `tuning_plan.automated_search`, with a domain, or
   - listed in `tuning_plan.structural_only` with one sentence on why it cannot
     be a value.

   Anything appearing in neither is the failure this check exists to catch. Then
   confirm the parametric side is actually buildable: `tuning/space.json`
   parses, `evaluator/eval_params.py` runs on one hand-written point and returns
   a finite score, and that score is comparable to `baseline_score` - same
   instrument, same units, same sign convention. A sweep whose scores cannot be
   compared to a candidate's is two experiments, not one.

   ```bash
   python3 evaluator/eval_params.py --params /tmp/probe.json --output-file /tmp/probe-out.json
   ```

   If the triage found nothing parametric, say so explicitly and give the
   reason. That is a legitimate outcome - but it is a claim someone should be
   able to argue with, and an unstated one reads as an oversight.

Score the broken and the known-good candidates with `--sanity`, which keeps them
in the record but excludes them from the failure-rate health check - deliberate
breakage should not make a validated experiment look broken. Their records, with
notes, are the evidence that the gate discriminates in both directions, and the
cheapest thing to re-run when someone later doubts a result.

### Score a ratio, not an absolute

If step 2 shows a wide or *drifting* noise floor - successive baseline scores
trending one way as the machine warms up - absolute timing will systematically
favour whichever candidates happen to run while the box is cold. Every score is
then partly a timestamp.

The fix is to make each measurement self-referential: time the candidate and the
untouched reference **back to back in the same process on the same input**, and
score the ratio. Alternate which runs first across repeats so the ordering
cancels. Drift, thermal state, and background load hit both arms equally and
divide out. In practice this is the difference between a ~7% noise floor and a
sub-1% one, which is the difference between an experiment that can resolve a
real 3% win and one that cannot.

Keep the reference implementation outside the evolve block, obviously - it is
part of the harness, and a candidate that can edit its own control has no
control.

Then write `README.md` with the objective, the baseline, the measured noise
floor, and the exact command to continue with `evolve:runner`.

______________________________________________________________________

## Things that reliably go wrong here

- **The evaluator scores a stale build.** It must build from `--program-dir`,
  not from a path baked in at design time. Verify by breaking the program and
  watching the score move.
- **Absolute paths in the harness.** Candidates are evaluated in copies;
  anything absolute points back at the original and measures the wrong code.
- **The gate is inside the evolve block.** Then it is not a gate.
- **Two performance experiments measure on one machine at once.** The harness's
  machine-wide lock queues them by default; the failure returns the moment
  someone opts out casually or benchmarks outside `evolve_run.py` / `tune.py`.
  Opting out is for metrics with no timing in them, never a throughput
  optimization.
- **Benchmark inputs are constants.** Randomize what you can per evaluation and
  hold out a second set the run never sees, or the loop will find your inputs
  rather than a better algorithm.
- **No held-out set at all.** Then the final result cannot be checked, only
  believed.
- **A tunable knob left inside an evolve block with no space file.** The loop
  will find it, and spend agent turns bisecting a number a script could have
  swept while everyone was at lunch - and every structural comparison made along
  the way is confounded by whichever value happened to be in the seed.
- **The sweep's evaluator and the candidate evaluator disagree.** Two entry
  points (`--params` and `--program-dir`) must produce the same score for the
  same program, in the same units and sign convention. If they drift, the
  sweep's winner cannot be folded back in, and you have two experiments that
  cannot be compared.

## References

- `references/problem_framing.md` - Phase 0: the problem behind the request, the
  null alternative, the premise ledger.
- `references/evaluator_contract.md` - writing the evaluator.
- `references/evolve_blocks.md` - deciding what a candidate may edit.
- `references/parameter_search.md` - writing the tuning plan and the sweep
  driver.
- `references/numeric_accuracy.md` - the target is numeric and speed can be
  bought with precision.
- `references/instruments.md` - choosing what the harness measures beyond the
  timer.
- `assets/templates/` - starting files to copy and fill in.
- `skills/evolve/references/fitness_design.md` (the consultant skill) - turning
  the goal into a score; staging; selection bias.
- `skills/evolve/references/perf_harnesses.md` (the consultant skill) -
  language-specific benchmarking; measurement bias.
- `skills/evolve/references/lowlevel_perf.md` (the consultant skill) - seeding
  strategies and estimates when the target is low-level performance.
- `skills/evolve/references/ml_tuning.md` (the consultant skill) - the target is
  a model or training pipeline: seed-variance noise floors, fidelity hazards,
  the nuisance-hyperparameter confound.
- `skills/evolve/references/quant_trading.md` (the consultant skill) - the
  target is a backtested strategy: the data budget, temporal splits, the noise
  test, Sharpe gaming.
- `skills/evolve/references/pre_mortem.md` (the consultant skill) -
  pre-registering what each outcome will mean.

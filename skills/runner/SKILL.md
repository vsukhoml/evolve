---
name: runner
description: >-
  Drive an evolutionary optimization experiment: run generations of the Strategist →
  Implementer → Evaluator → Reviewer loop with parallel subagents, record every
  candidate in the evolution database, update the knowledge base, and stop on
  budget, plateau, or a result that is real. Use this skill when the user says
  "run the experiment", "start evolving", "launch it", "do another 10
  generations", "keep going", or hands over an experiment directory built by
  evolve:design and wants it driven.
---

# Running the loop

## Before the first generation

The experiment directory must have: `experiment.json` with a non-null
`baseline_score`, `.ae/` scripts, a `program/` that builds, an evaluator that
has scored the seed twice, and `evolution.json`. If `baseline_score` is null,
stop - go back to `evolve:design` and finish its gate. A run without a baseline
produces numbers nobody can interpret.

Check the state and say what you found:

```bash
python3 .ae/evolve_db.py stats --experiment .
python3 .ae/evolve_report.py --experiment . --json
```

**On a resumed run, check the harness is not stale.** An experiment carries its
own copy of `.ae/`, taken when it was created, so a directory built before a
skill update silently lacks whatever the current instructions assume. Diff it:

```bash
AE=$(find ~/.claude/plugins ~/.gemini/config/plugins ~/.codex/plugins \
       ~/.grok/plugins .agents/plugins -path '*evolve*/skills/design/assets/ae' \
       -type d 2>/dev/null | head -1)
diff -q "$AE" .ae/
```

Differences are not automatically wrong - the experiment may have been patched
deliberately - but you must know which is which before following an instruction
the local copy cannot execute. In a real run this bit twice in one session: the
documented `evolve_db.py review` subcommand did not exist locally, and a bug
fixed upstream was still live in the experiment's copy.

**Run the parameter sweep before generation 1, if the design left one.** Read
`tuning_plan.automated_search` in `experiment.json`. If it is non-null and
`tuning/best.json` does not exist, the sweep has not been run - launch it now
and wait for it before spending a single candidate:

```bash
python3 .ae/tune.py --space tuning/space.json --command "python3 evaluator/eval_params.py" \
    --out tuning/ --method <plan's method> --repeats <plan's repeats> \
    --noise-floor <floor> --patience 40 --max-seconds <cap> 2> tuning/progress.log
```

Then fold the winning point from `tuning/best.json` into `program/`, re-score
the seed, and update `baseline_score`. Note the old and new baseline in the
knowledge base - the difference is the sweep's contribution, and it must not
later be attributed to a candidate.

The order is not a preference. A structural candidate measured against a
badly-configured seed is confounded: a 4% "win" may be a better constant that
any structure would have enjoyed, and you cannot separate the two after the
fact. Running the cheap search first also means generation 1 starts from the
best configuration of the *current* structure, so the loop spends its turns on
shapes rather than arithmetic.

If `automated_search` is null, check that `structural_only` says why. An absent
triage means the design gate's check 7 did not happen - go back rather than
guess.

Two things to say out loud before spending the budget: the **noise floor**, and
roughly **how long the budget will take** (candidates × evaluation time ÷
parallelism). People agree to "40 candidates" without realising it is four
hours.

## Early generations are reconnaissance

A hypothesis should sharpen through contact with the data, not arrive fully
formed. Stage the run - investigate, tune, execute, ablate - each stage seeded
by the best of the last. Spend the first generation or two on probes: strategies
framed as questions ("front-end bound or memory bound?", "does the table even
fit in L1?"), where the candidate exists to produce an inference, not to win.
Record the answers in the knowledge base and its open-questions list; let the
middle generations exploit what reconnaissance established; leave the ablations
to the closing ritual. A probe that fails to beat the baseline but settles an
open question has paid for itself - write it in the KB as an answer, not a loss.

Run reconnaissance as **strong inference**, not hypothesis-at-a-time: keep two
or three rival mechanism hypotheses alive in the knowledge base - "memory-bound"
vs "mispredict-bound" vs "allocator churn" - and design each probe as a crucial
experiment whose outcome is incompatible with at least one rival, ideally
splitting the field in half like binary search. A single working hypothesis
hardens into a ruling theory the whole run then polishes, which is population
collapse at the epistemic level. And when the block is knob-heavy, one cheap
sensitivity screen - vary each knob once across its range - ranks which knobs
matter before candidates are spent tuning ones that do not.

Label each generation's mode: **exploring** (generating hypotheses) or
**confirming** (testing one). Evidence gathered while exploring never counts as
confirmation - re-earn it in a confirming generation, or it is HARKing with
extra steps.

## One generation

Each generation produces `parallel` candidates. Run the four roles in order.
Strategists and implementation parallelize across candidates; the **measurement
does not** - `evolve_run.py` holds a per-experiment lock while it scores,
because three benchmarks racing on one machine are timing each other's cache
pressure. Spawn all the implementers at once; their scoring calls queue on their
own.

**The lock is also machine-wide, across experiments - with two modes.** A
per-experiment lock cannot see a second experiment (or a `tune.py` sweep)
measuring on the same box, and two *timed* measurements running at once corrupt
both silently - both complete, both record numbers, both sets of numbers are
wrong, multithreaded benchmarks worst of all. So timed stages hold the machine
**exclusively**, one at a time across all experiments, while untimed work -
correctness gates, untimed screen stages, whole experiments declared
`"measurement": {"machine_exclusive": false}` - runs under a **shared** lock:
any amount in parallel with each other, but never during someone's exclusive
measurement, because untimed work still costs cores. The design skill's
parallelism plan decides which stage is which. Never launch a second timed
experiment on the same machine expecting parallel throughput - its timed stages
will queue, and that is the guardrail working; the untimed parts of both runs
interleave freely. And on a whole-machine benchmark, remember the lock covers
*measurement* only: implementers compiling in parallel still cost cores, so drop
`parallel` to 1-2 rather than trusting the lock alone.

### 1. Select parents

```bash
python3 .ae/evolve_db.py select --experiment . --n 3 --policy mix
```

`mix` alternates greedy (exploit near the top) and novel (explore thin
lineages). Override deliberately, not by habit:

- `--policy greedy` when a promising direction is clearly not exhausted.
- `--policy novel` when the report warns about lineage collapse, or after ~10
  candidates with no gain above the noise floor.

In a multi-objective experiment (`objectives` declared in `experiment.json`),
greedy samples the Pareto front uniformly - every non-dominated trade-off is
equally a "best". Watch where recent parents came from: a run whose parents all
sit at one end of the front is optimizing one axis with extra steps, and
deserves a slot aimed explicitly at the neglected end. Brief that strategist
with the front itself - "these are the current trade-offs; extend the sparse
region" - not just the leader on one axis.

When a candidate restarts from the original seed with a stated different
approach, score it with `--new-lineage` - otherwise it inherits the seed's
lineage root, and the diversity metric cannot see that the population just
widened.

**On a suite benchmark, watch what selection is refusing to build on.** With
`preserve_and_extend` declared, a candidate that gave up cases its parent solved
keeps its score and its leaderboard row but stops being selectable as a parent -
so a lineage accumulates capabilities instead of trading them, and the archive
still holds the loser for its lesson and for recombination. With
`promotion.confirm_before_steering`, greedy draws only from re-confirmed
programs while novel draws from everything. Both are read from
`experiment.json`, both need driving, and the failure they prevent is a lucky or
lopsided measurement becoming the ancestor of the next twenty candidates:
`references/coverage_and_confirmation.md`.

**Spend one slot per generation repairing a promising failure.** Alongside
"improve the best" and "try something new", give one worker the job of fixing a
candidate that failed for a *mechanical* reason - a compile error, a missed edge
case - but whose strategy was sound. Repair deserves to be a first-class action,
not an afterthought: failed candidates are the ones that were ambitious enough
to break, so they carry the most headroom. Discarding them, which is what a
naive loop does, throws away the most interesting part of the population. Skip
the repair slot only when nothing failed for a mechanical reason.

Repair is the **only** slot that gets a failure as a starting point. Every other
strategist sees failures as evidence - the strategy, its label, the number, the
step that broke - and never as code to extend, because a broken candidate handed
over as a parent gets improved rather than diagnosed, and its flaw is inherited
along with its idea. And a candidate marked `infra_failed` is not a failure at
all: it was never measured, so re-score it under a new id rather than repairing
something that may have been fine.

**And when two lineages hold different half-wins, spend a slot recombining
them.** Give one strategist the top program from each of two distinct lineages
and the job of combining what makes each one win (`--policy recombine` - the
label is free-form). This is also why strategists are shown diverse programs
rather than just the leader: recombination is the only move that can merge two
partial solutions, and no amount of mutation inside one lineage produces it.

**Every few generations, spend a slot simplifying the best**
(`--policy simplify`): make it shorter and plainer without losing score above
the noise floor. It is cheap diversity pressure, and it is what keeps the
eventual winner mergeable instead of carrying the scars of every mutation that
got it there.

**Say what "simpler" is measured in, or you will get comments deleted.** A
simplify slot briefed only as "shorter" reliably comes back proposing to strip
prose - a change that touches no emitted instruction, so its expected effect is
not merely inside the noise floor but *zero by construction*, and that destroys
the "why" documentation which is the most expensive thing in the file to
reconstruct. Brief the slot in **mechanism counts**: non-comment lines,
functions, distinct code paths, special cases, tuning constants the benchmark
cannot validate. Count them yourself before briefing and put the real numbers in
the prompt - raw line counts silently include comments, and a winner that is 80%
prose looks four times more complex than it is. Comments are explicitly out of
scope, to be rewritten to match whatever survives. If the simplification is real
the prose shrinks on its own, because there is less to explain.

**Weight the slot mix with the cross-experiment `lessons.md`.** Every candidate
records its policy, so past runs know which moves actually produced real wins on
similar problems - "recombine earned 2 of 3 wins on parser-shaped problems"
should buy recombine more slots here. Adjust the mix on evidence, not on habit.

**When a mechanism wins, spend the next generation on its family.** A winning
idea is rarely alone: it has variants, siblings, and neighbors built on the same
mechanism, and they are the cheapest place the next win can live. Enumerate them
the moment the win is confirmed and give them the following generation's slots,
rather than trusting the loop to wander back. A large published autonomous run
tested two sibling variants of the same optimizer idea 74 hours apart because
nothing prompted the adjacency - days of frontier compute spent between two
members of one family.

The *policy* mix is the one place a bandit-style allocation is sound, because
the arm set is small and stable across runs. **Do not use one to pick
candidates**: bandit algorithms minimize cumulative regret while you want a
single good final recommendation, they are empirically beaten by successive
halving on this shape of problem, and their assumptions (a fixed, stationary arm
set) are violated the moment a generation regenerates the pool.

### 2. Strategists - in parallel, one per candidate

Spawn one subagent per parent, **in a single message so they run concurrently**.
Each gets: the problem, the parent's code, **the parent's evaluation insights**
(spread, profile notes, stderr - the measurement is the ground truth a strategy
must answer to), the knowledge base, `seed_strategies.md`, the current
leaderboard, **the evolve blocks of one or two elites from other lineages**
(inspiration for mix-match - mechanisms, not lines), and its assigned policy. It
returns a strategy document - hypothesis, rationale, expected effect, how we
would know - and nothing else. It does not write code.

Two cheap levers on the quality and variety of what comes back:

- **Mix model strengths.** Use a fast model for most strategists and a stronger
  one for a minority of slots. The fast model maximizes ideas explored per unit
  time; the strong one supplies the occasional leap. Volume and depth are
  different jobs and one model setting cannot do both well.
- **Vary the framing.** Do not send every strategist a byte-identical prompt.
  Vary the ordering of the leaderboard, which past attempts you show, and the
  phrasing of the ask. Identical prompts produce correlated proposals, which is
  population collapse arriving through the front door.

Full brief in `references/agent_briefs.md`. Two things matter most:

- **The knowledge base is mandatory reading.** Its whole purpose is to stop
  generation 12 re-proposing what generation 3 disproved.
- **A novelty check before the compute spend.** The strategist confirms its idea
  is not already in the KB's dead-ends, and for research-flavoured problems may
  search the literature. This is the cheapest step in the pipeline and it kills
  the most waste.

Save each to `generations/<id>/strategy.md`.

**Triage before implementing.** When the strategies come back, check each
against the knowledge base and the noise floor, and decline the obvious losers:
a duplicate of a recorded dead end, a proposal whose own expected effect sits
inside the noise floor, a violation of a stated invariant. What triage buys is
the cheap veto, not a ranking - a model's self-assessment of its own idea is a
weak instrument, so kill only clear duplicates and infeasibles and never pick
winners; that is the evaluator's job. Record each declined strategy in the
knowledge base with the reason; it cost one prompt, and it should not cost a
second one.

### 3. Implementers - in parallel

One subagent per strategy. Each:

1. Copies `program/` to a scratch candidate directory (never edits `program/` in
   place - parallel implementers would collide, and the baseline would be lost).
2. Applies the strategy **inside the EVOLVE-BLOCK markers only**. Touching the
   evaluator, the gate, the benchmark data, or anything outside the markers is
   an automatic reject, not a judgement call.
3. Scores it through the harness - never by running the code by hand:

```bash
python3 .ae/evolve_run.py --experiment . \
  --candidate-dir /tmp/ae-cand-gen007-a --id gen-007-a \
  --parent gen-003-b --policy greedy \
  --strategy-file generations/gen-007-a/strategy.md --generation 7
```

`evolve_run.py` runs the correctness gate first, then the evaluator with
repeats, rejects non-finite scores, snapshots the exact program, and records
everything. Routing every evaluation through it is what makes the run comparable
candidate-to-candidate - an agent that benchmarks by hand has opted out of the
gate, the timeout, and the snapshot at once.

### 4. Reviewer - one subagent for the generation

Reads each **diff** (not the score) against the invariants and asks: is this
correct, is it a genuine improvement, or did it game the benchmark? Its verdict
goes into the record, and a `reject` removes the candidate from selection and
the leaderboard even if it scored best.

Record the verdict - this also recomputes the winner, since a veto can dethrone
the stored best:

```bash
python3 .ae/evolve_db.py review --experiment . --id gen-007-a \
  --verdict accept --reason "real algorithmic win, holds on held-out inputs"
```

The reviewer exists because the evaluator answers "did the score go up", never
"is this a real improvement". Be suspicious in proportion to the size of the
win: a gain much larger than the domain makes plausible is a measurement bug
roughly nineteen times out of twenty. Check that one before celebrating it.

**The reviewer is a low-recall instrument, not a judgement.** Repeat passes on
the same material rarely surface the same findings, its stated confidence
measures nothing, and at that recall "the reviewer found nothing" is close to no
information. Verdicts are also asymmetric: a *reject* is real signal, an
*accept* is close to silence. So for a verdict that matters - the winner, a
candidate about to merge - run it two or three times independently, at least one
pass from a **different model** (a second model's critique is informative
exactly where self-review is not), and take the union of findings, and report
silence as "one low-recall pass found nothing", never as a clean bill. Measure
it once, cheaply, with planted defects: an uncalibrated reviewer is the run's
single largest unmeasured risk, because every other instrument has a noise floor
attached and this one does not. The numbers behind these rules and the
planted-error procedure are in `references/agent_briefs.md` § *Reviewer
calibration*.

Falsification deserves the same first-class standing on the generate side - it
is the research process, not a validation step bolted on afterwards. The
mechanism here is already in the strategy format: every strategy must state
**how we would know it did not work**. What to protect is the *specificity* of
that clause, not the addition of another role. In practice the specific ones
fire by themselves and the vague ones produce nothing.

### Ties and near-ties

A candidate that beats the incumbent by less than the noise floor is not a new
best - it is a tie the measurement cannot resolve, and `evolve_run.py` flags
exactly this on the "new best" line. Do not report it as an improvement. If the
ordering matters for parent selection, re-measure both at higher repeats with
`--dry-run` and let those numbers pick the parent; the recorded scores stay as
measured. At a genuine tie, prefer the **simpler diff**: at equal score,
simplicity is the only real tiebreaker, and it keeps the eventual winner
mergeable.

### Confirm the winner with a split sample

The maximum of N noisy scores is biased upward *by construction* - the
leaderboard is sorted partly by who got the luckiest measurement, and the effect
grows with N. The fix has a proof behind it, and it is not "re-run the winner
and average everything together":

**Choose the winner on one set of measurements, then report its score from a
disjoint set.** That estimator provably never overestimates the true maximum.
Averaging the confirmation run back into the selection data throws the guarantee
away.

Mechanically: measure the confirmation set with `evolve_run.py --dry-run` on the
winner's snapshot (`generations/<id>/program`) - it evaluates without recording,
so the confirmation numbers never enter the selection data.

Do this **once, on the single winner.** Running a "confirmation" on every
promising candidate rebuilds the multiple-comparisons problem inside the stage
meant to solve it: apply a holdout enough times and false positives stop being
unlikely and become expected.

The steering confirmation under `promotion.confirm_before_steering` is a
different thing and does not violate that rule: it guards a *selection*
decision, its numbers are never quoted as a result, and it may run as often as
the budget allows. Keep the two apart in the report - which programs earned the
right to steer, and separately what the winner scored on its holdout.

In a multi-objective run the same rule reads: the owner picks the point (or two)
they would actually ship from the front - that choice is a product judgement,
not the run's - and only the picked points get the confirmation. The rest of the
front is reported as measured, labelled unconfirmed.

Separately, re-score the *incumbent* periodically during the run. Otherwise a
lucky early score becomes an immortal champion nothing can dislodge, and the run
presents as a plateau against a number that was never true.

**Stronger, and cheap: score every candidate adjacent to a fresh re-score of its
parent.** The noise floor you measured at design time is *within-session* noise.
Between sessions the machine drifts - different thermal state, different
background load, a different binary layout - and that drift can exceed the floor
outright. Measured in a real run: byte-identical source scored −10.720 and
−10.257 in two sessions, a 0.463 spread against a declared floor of 0.25. The
probe that found it would otherwise have reported a 0.385 "win" as real.

So a comparison against a number recorded hours ago is not a comparison, and the
fix costs one extra evaluation per candidate: re-score the parent now, in this
session, and compare against that. Quote both. When a run has been going long
enough to span sessions, say which deltas were measured adjacently and which
were not - the second kind are undecided, not small.

For how much inflation to expect given your noise floor and candidate count, and
why N should be counted in distinct lineages rather than candidates, see
`skills/evolve/references/fitness_design.md` § *Selection bias*.

### 4b. Score the predictions - the calibration ledger

Every strategy states an **Expected effect** before its candidate is built. That
clause is a pre-registration, and it is free evidence - but only if someone
scores it afterwards. Keep a small ledger in the knowledge base: for each
candidate, what was predicted, what happened, and whether the **direction**, the
**magnitude** and the **mechanism** were right. Three labeled verdicts, one line
per candidate.

It pays for itself within a generation or two, because it tells you how to
*read* your own pipeline. A real run scored **direction 5/7, magnitude 3/7 with
every miss over-optimistic, and mechanism 3/7** - so a predicted gain there
should be read as "probably the right sign, plausibly half the stated size", and
any confident mechanism story should be treated as a coin flip until an
instrument confirms it. Without the ledger, that pipeline would have kept
believing its own magnitude estimates.

Two things the ledger surfaces that nothing else does. **A strategy whose
falsifier was specific fires by itself** - "a128 and a256 above the parent with
the other shapes flat" triggered its own fallback automatically - while vague
falsifiers produce nothing; so the ledger is really measuring whether your
briefs are demanding specific predictions. And **a systematically
over-optimistic pipeline is a triage input**: when everything is predicted at
2x, raise the bar a proposal must clear before it earns an evaluation.

### 5. Update the knowledge base

Append one line per candidate to `knowledge_base.md`: what was tried, what
happened, the number, and **the inference**. "Unrolling did nothing, so the loop
is not front-end bound" is worth six candidates; "tried unrolling, no change" is
worth none.

**Label each failure while you are there**
(`evolve_db.py label --failure-mode`), from a small vocabulary fixed at the
start of the run. The report then names the mode that dominates the whole
benchmark, and that theme goes into the next generation's strategist briefs - a
strategist shown only its own parent's trace keeps proposing the local fix for a
bottleneck spread across nine other candidates.

Then refresh the dashboard:

```bash
python3 .ae/evolve_report.py --experiment . --write dashboard.md
```

## Synthesis - zoom out every few generations

The KB updater sees one candidate at a time. Every ~10–15 candidates - and
always at a plateau warning or before deciding to stop - run a synthesizer over
the whole population (brief in `references/agent_briefs.md`): all of
`evolution.json` including the failures and screened-out candidates, the
knowledge base, the dashboard. It looks for what no per-candidate entry can show

- metrics that correlate with winning across the population, strategy families
  that cluster, seed directions that never grew a lineage, constraints nobody
  has pushed against - and returns revised rival hypotheses, a condensed KB, and
  a recommendation for the remaining budget.

Patterns found this way are observational (the causal rule applies): they steer
probes and the slot mix, they never enter the KB as *measured*. The population
is data - read it, not just the leaderboard.

**Refresh the external sources at the same cadence.** The prior-art search
happened once, at design time, and a run long enough to span days is long enough
for its sources to move - an upstream repository, a competitor's new result, a
fresh entry in the cross-experiment `lessons.md`. Re-check them at each
synthesis point. In a large published autonomous run, the technique behind the
eventual record sat in an upstream pull request for days and only entered the
search when a forced restart happened to re-fetch the sources; nothing in the
loop would ever have looked again on its own.

## Between generations

Report only what changed - a new best, a health warning, a state change.
Narrating "generation 8 complete, no improvement" every few minutes trains the
user to stop reading. The dashboard holds the detail.

Post a short report when: a new best appears, the report raises a WARN/BAD, or
the run stops.

## Stopping

Stop when any of these is true, and say which:

- The budget is spent.

- No gain above the noise floor for ~15 candidates **and** lineage diversity is
  healthy - the space is exhausted at this granularity, which is a legitimate
  finding, not a failure.

- The failure rate is above ~60% - the harness is wrong. Fix it and restart
  rather than spending budget on a broken measurement. Candidates that were
  never measured (`infra_failed`) are excluded from that rate and are their own
  stop signal: when the box is dropping evaluations, every number measured
  beside them is suspect too, so fix it before spending more budget.

- The best gain is inside the noise floor after a substantial budget - report
  the non-result plainly.

- In a multi-objective run, read every "no gain" signal against the **front**,
  not the primary axis: the dashboard's front-unchanged check is the plateau
  signal there, because the first axis can stall for many candidates while the
  front is still genuinely filling in.

- The surviving candidates differ only in numeric constants - switch
  instruments: a grid or Bayesian sweep tunes a continuous subspace better than
  LLM mutation ever will. Record the handoff and the knob ranges in the
  knowledge base; that is a finding, not a failure.

  Treat it as a **triage miss** and name it as one: a knob the design phase
  filed as structural, or did not see at all, has turned out to be a value. Add
  it to `tuning_plan.automated_search`, extend `tuning/space.json`, and say in
  the knowledge base which generations were spent discovering it - those
  candidates' comparisons are confounded by it, and a later reader needs to
  know. The design phase should already have written a `tuning_plan` naming the
  method for each knob (binary search / grid / Morris screening / Bayesian /
  NSGA-II, chosen from the expected response shape) - execute that rather than
  improvising, and before tuning any knob confirm the metric is *sensitive* to
  it across its whole domain, or the tuner will return a precise value fitted to
  noise.

  **Hand it to a standalone search process rather than driving it yourself.**
  `skills/design/assets/templates/tune.py` runs the whole space in one resumable
  process with flushed progress, an atomically-written `best.json`, a wall-clock
  cap and a convergence stop. Launch it in the background and poll the log on a
  human cadence:

  ```bash
  python3 .ae/tune.py --space space.json --command "python3 evaluator/eval_params.py" \
      --out tuning/ --method random --repeats 3 --noise-floor <floor> \
      --patience 40 --max-seconds 3600 2> tuning/progress.log
  # then, occasionally:
  tail -5 tuning/progress.log ; cat tuning/best.json
  ```

  Do not re-implement this as one candidate per generation. An agent turn per
  parameter combination spends minutes of wall clock on seconds of measurement,
  and the search is the part that wants iterations. Your job while it runs is to
  notice a progress log that has stopped moving, a failure rate climbing, or a
  best that arrived suspiciously early - and then to give the winner the closing
  ritual, because a tuner maximizes over noise more eagerly than an LLM does
  simply by taking far more samples.

**Before stopping, refresh the technique coverage ledger** in
`seed_strategies.md` and read it as a whole. Every family gets a status -
confirmed, refuted, excluded by constraint, untested, not applicable - each
citing a candidate id, a probe, or the constraint. A run that stops with
unexamined blanks has not exhausted the space; it has exhausted *one shape* of
the space, and those are very different findings. Report the blanks in the final
report rather than letting a candidate count imply coverage: "we ran seventeen
candidates" answers a question nobody asked, while "multiple accumulators were
never tried, and here is why that is or is not defensible" answers the one they
did. If the owner asks whether the standard approaches were tested, this ledger
must be the answer.

On a long run, a win that has already passed the closing ritual mid-way need not
wait for the budget to end: offer it for integration then, and continue the run
from it. The value lands sooner, and how it behaves in production is
reconnaissance the benchmark cannot produce. Integration itself stays what it
always is - a separate, explicitly requested, reviewed step.

Then run the **closing ritual**, which is what separates a result from a number:

1. Re-score the winner in a **fresh copy** from its snapshot.
2. Score it on the **held-out** inputs, and across the input *shapes* the caller
   actually sees - short and long, sparse and dense. Quote the worst one beside
   the best; a held-out set catches tuning to specific inputs, not tuning to an
   input profile.
3. Read the winning diff line by line yourself.
4. **If the diff contains more than one idea, ablate it factorially**: with 2–3
   ideas, score all 2^k combinations against the seed with `--dry-run` (4–8
   evaluations) rather than one idea at a time - one-factor-at-a-time misses
   interactions, and an interaction (two changes that only win together) is
   exactly what a recombined winner is made of. Only then write down which
   mechanism earned the gain. A two-change diff credited to one change is how
   knowledge bases go wrong - the headline number survives, but everything the
   run "learned" is attribution guesswork.
5. Report the gain **with its noise floor**, the diff, and what the run learned
   - including the dead ends, which are often the more reusable half. Every
     number in that report must be re-derivable from a stored artifact.

Integration into the user's actual tree is a separate, explicitly requested
step. Never write into their working tree as part of the loop.

## When commands fail

Debugging the harness mid-run burns budget fast, so cap it. Three failed
attempts at the same step means stop and diagnose structurally - say what each
attempt showed and what root cause that implies - instead of trying a fourth
variation. Never run more than five variations of one command without new
information; a sixth is guessing. Before each retry, state what the last failure
taught you and why this attempt is different. And separate fixable from
unfixable: a missing dependency or a wrong path is yours to fix; a broken
evaluator contract or a machine-level problem is a stop-the-run finding, not a
retry target.

## Safety

The loop executes model-written code unattended, hundreds of times, and the
hazards are the ordinary ones: dangerous packages, web access, spawned
processes. Proportionate response - pure local computation is fine in a normal
process; anything touching the network, the filesystem outside the candidate
directory, or subprocesses belongs in a container. Timeouts are always set. The
harness always lives outside the evolve blocks.

## References

- `references/agent_briefs.md` - spawning strategist / implementer / reviewer
  subagents; calibrating the reviewer.
- `references/coverage_and_confirmation.md` - suite benchmarks: per-case
  coverage, the two-speed promotion rule, failure-theme aggregation.
- `skills/evolve/references/failure_modes.md` (the consultant skill) - a result
  looks too good.
- `skills/evolve/references/run_diagnosis.md` (the consultant skill) - the run
  is misbehaving.
- `skills/evolve/references/fitness_design.md` (the consultant skill) -
  selection bias, racing, spending a fixed budget across candidates.

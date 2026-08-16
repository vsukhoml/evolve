# The evaluator contract

The evaluator is the only thing in the experiment that touches ground truth, so
it is the only component whose bugs are indistinguishable from discoveries.
Write it first, break it on purpose, and only then trust it.

## Interface

Invoked by `evolve_run.py` as:

```
<command...> --program-dir /abs/path/to/candidate --output-file /tmp/out.json
```

It writes JSON to `--output-file`:

```json
{
  "score": 12345.6,
  "metrics": {"median_ns": 81.0, "p99_ns": 96.0, "instructions": 4210},
  "insights": [
    {"label": "stdout", "text": "..."},
    {"label": "build", "text": "finished in 4.1s"}
  ]
}
```

- `score` - a finite float where **higher is better**, or `null` on any failure.
- `metrics` - free-form numbers kept for later analysis. Cost nothing now, save
  a rerun later.
- `insights` - labelled text: stdout, stderr, build errors, tracebacks. This is
  what a human reads when a candidate dies.

Exit code is advisory; the JSON is authoritative. Write the file even on
failure, with `"score": null` and an insight explaining what happened. An
evaluator that dies without writing leaves the loop guessing.

## Say when the failure was not the candidate's fault

```json
{"score": null, "failure": "infrastructure", "insights": [{"label": "oom", "text": "..."}]}
```

The harness records that as `infra_failed`, keeps it out of the failure rate,
and tells the run the strategy is **untested rather than refuted**. Both halves
matter. A candidate killed by an unrelated job's OOM pushes the failure-rate
check toward its "the harness is wrong" stop, and - worse - the technique it was
carrying gets written into the knowledge base as a dead end, so a future run
avoids an idea nobody ever tried. That is the most expensive kind of wrong entry
there is, because nothing later in the run can contradict it.

The boundary is not "did it fail" but **"was the candidate the reason"**:

- **Infrastructure** - out of memory or disk from something else on the box, a
  missing toolchain, a dependency mirror that went down, a device that
  disappeared, a container that could not start.
- **Not infrastructure** - a timeout at the declared budget. The budget is part
  of the problem statement, so a candidate too slow to finish inside it has been
  measured, and it failed. Likewise a build error, a crash, or a wrong answer:
  all of those are the candidate.

The evaluator is the only component that can tell these apart, because it is the
only one that knows what it was doing when it died. Say it explicitly - the
harness detects only the two cases it can know for itself (the gate command or
the evaluator command not existing) and never guesses from an exit code or a
stderr pattern.

## Multi-objective experiments

When `experiment.json` declares an objective tuple:

```json
"objectives": {
  "axes": ["neg_median_ns", "neg_code_bytes"],
  "noise_floors": {"neg_median_ns": 0.5, "neg_code_bytes": 0},
  "hypervolume_ref": {"neg_median_ns": -200, "neg_code_bytes": -8192}
}
```

the evaluator additionally writes every declared axis:

```json
{
  "score": -81.0,
  "objectives": {"neg_median_ns": -81.0, "neg_code_bytes": -2048},
  "metrics": {"...": "..."}
}
```

- Every axis keeps the scalar rules: **higher is better** (negate what should
  shrink), finite, `null` never appears - a missing or non-finite axis fails the
  whole evaluation. A partial vector is a failure, not a smaller success: stored
  with a hole it would sit beside complete vectors looking rankable while being
  incomparable to every one of them.
- `score` stays required and is by convention the **first axis**, so every
  scalar tool - crash sentinel, baseline, trajectory - works unchanged.
- Ranking becomes noise-aware Pareto dominance: `evolve_db.py best` prints the
  front, a per-axis difference inside that axis's `noise_floors` entry counts as
  equal, and within-noise ties coexist on the front. Measure the per-axis floors
  at design gate check 2; an axis with no floor claims perfect resolution.
- In a cascade, only the **last** stage's objectives count - the same rule as
  the score, for the same reason: screening stages measure a cheaper proxy that
  has no business on the front.
- `hypervolume_ref` (optional, two axes only) is a reference point worse than
  anything acceptable on both axes; the dashboard uses it to summarize front
  progress as a dominated-area scalar.
- Deliberately no NSGA-II machinery in the harness - populations are tens and
  plain dominance is enough. If an experiment genuinely needs crowding or
  tournament selection, implement it in that experiment's own harness, after the
  owner confirms the extra moving parts are wanted.

## Per-case scores, when the benchmark is a suite

A scalar score is a sum over the benchmark, and a sum hides a trade. The
candidate that is 8% faster *on average* because it is 12% faster on four inputs
and 3x slower on the fifth outranks the one that is 5% faster everywhere, and
nothing in the leaderboard says so. On a single-input benchmark that cannot
happen. On a suite it is the normal failure, and it stays invisible until the
winner ships and someone reports input five.

So when the evaluator scores a suite, emit the vector beside the aggregate:

```json
{
  "score": 1.34,
  "cases": {"sparse_1k": 1.51, "dense_1k": 1.22, "adversarial": 0.98},
  "metrics": {"...": "..."}
}
```

- Each case is **higher is better**, same convention as everything else, and
  finite. A case that appears in one repeat and not the next fails the whole
  evaluation - the medians would be taken over different populations.
- The case set must be **fixed by the experiment, not chosen by the candidate**.
  A candidate that can shrink the suite will: dropping the case it loses raises
  the mean, which is a benchmark game that looks exactly like a win.
- In a cascade only the **last** stage's cases count. A screening stage measures
  a cheaper proxy suite, and comparing a child's screen cases against a parent's
  full-benchmark cases reports coverage the candidate never demonstrated.
- Binary suites (solved / not solved) are the degenerate case: values 0 and 1, a
  `case_floor` of 0. This is the shape an agent or prompt experiment has.

Declare the contract in `experiment.json` to make the harness act on it:

```json
"preserve_and_extend": {"max_regression": 0.0, "case_floor": 0.25}
```

Then each child is compared to its parent case by case, and one that gave up
more than `max_regression` **may still score, rank, and be reported - it just
may not be built on**. That split is the whole design. The archive keeps it,
because the edit that loses two cases here may be the only one that reaches a
case nothing else does, and its lesson is worth as much as a winner's; but a
lineage that can trade cases away accumulates nothing, and the run wanders
sideways while the leaderboard climbs.

`case_floor` is the noise floor of **one case**, which is wider than the
aggregate's - a median over N cases averages away noise the individual case
still carries. Measure it the same way you measure the aggregate floor, on
repeated runs of identical source, and set `case_floors` per case where they
differ by more than a factor of two. Only losses beyond the floor count toward
the regression; summing within-floor wiggle across a large suite manufactures a
regression out of pure sampling.

A case the parent reported and the child did not is not a tie. It is a case
whose result is unknown, and an unknown cannot be preserved - the harness treats
a dropped case as an automatic disqualification from parenthood, whatever the
aggregate says.

## The three rules that are not negotiable

**Higher is better, always.** Negate anything you want small, at the point of
measurement:

```python
score = -median_ns
```

The alternative is a direction flag honored in six places, one of which will be
wrong, and the symptom is a run that gets steadily worse while the leaderboard
says it is improving.

**`null`, never a sentinel.** `-1e12` for failure looks harmless and then turns
up inside a mean. `evolve_run.py` treats anything at or below `-1e9` as a crash
for exactly this reason, but do not rely on that - return `null`.

**Reject non-finite scores before returning.** NaN is not valid JSON, and Inf
silently wins every comparison forever:

```python
if score is None or math.isnan(score) or math.isinf(score):
    return {"score": None, "insights": [{"label": "non_finite", "text": str(score)}]}
```

NaN arises constantly in anything involving floating-point accumulation,
training loops, or division by a count that a candidate made zero.

## Structure

```python
def evaluate(program_dir: str) -> dict:
    # 1. build the candidate, from program_dir - never a baked-in path
    # 2. warm up
    # 3. measure `repeats` times, keep every sample
    # 4. verify the output is still correct on a checksum
    # 5. return the median, negated if smaller is better
```

Step 4 is the one people skip. A candidate that returns instantly because it
returns nothing is the single most common fake win, and one asserted checksum
over a non-trivial input closes it.

A checksum checks agreement with the reference; **problem invariants** check
correctness by the problem's own laws - round-trips, conservation, bounds,
feasibility. Assert the cheap ones on every timed call: they hold on any input,
need no reference implementation, and catch the wrong-at-scale candidate that
example-based tests cannot. The design skill's invariant harvest is where these
come from.

Repeats can live in either place: `evolve_run.py` will call the evaluator
`evaluator.repeats` times and take the median across calls, and the evaluator
can also loop internally. Internal repeats are cheaper (one build); external
repeats also capture build and process-startup variance. Doing both is fine -
just do not report a single sample.

## Held-out inputs

Keep two sets of benchmark data:

```
evaluator/inputs/    scored every evaluation
evaluator/holdout/   never touched during the run
```

At the end, score the winner on `holdout/`. A candidate that wins on one and not
the other optimized your benchmark, not your problem. This is the cheapest
insurance in the whole design and it takes ten minutes to set up.

Where the inputs can be generated, generate them per evaluation from a fixed
*distribution* with a varying seed. Special-casing a distribution is far harder
than special-casing a constant.

## Sandboxing

The evaluator executes model-written code, hundreds of times, unattended. The
hazards are the obvious ones: a candidate that pulls in a dangerous package,
reaches the network, or spawns processes.

Proportionate defaults:

- Pure computation on local data: a normal process is fine.
- Anything touching the filesystem outside the candidate directory, the network,
  or subprocesses: run the whole loop in a container or VM.
- Always set a timeout (`evaluator.timeout_seconds`); an unbounded evaluation is
  how a run quietly stops at 3am.
- Never let the evaluator, the gate, the benchmark data, or the runner scripts
  sit inside an evolve block. A candidate that can edit its own examiner will
  eventually do so, and the result will look like a breakthrough.

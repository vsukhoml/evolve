# Coverage, confirmation, and failure themes

Read this when the experiment declares `preserve_and_extend` or
`promotion.confirm_before_steering` - that is, when the benchmark is a suite, or
when one evaluation is noisy enough that the run has to screen at low repeats.
The rules live in the skill; this is how to drive the three mechanisms without
tripping over the ones already there.

## Coverage: what changes in the loop

Nothing about scoring or ranking. `evolve_run.py` records the per-case vector
the evaluator emitted, the database compares it to the parent's, and the only
consequence is that a program which gave up more than `max_regression` stops
being selectable as a parent. It keeps its score, its leaderboard row, its
snapshot, and its lesson.

That split is deliberate and it is the part people undo by accident. The
temptation is to fail the candidate outright, which throws away the exact
population the archive exists to hold: the edit that loses two cases may be the
only thing that reaches a case nothing else does, and it is worth keeping for
recombination even though no lineage may descend from it. The opposite
temptation - report the regression and let selection ignore it - gives you a
lineage that trades capabilities in a circle while the aggregate climbs.

**Read the flag before you read the leaderboard.** `evolve_run.py` prints a
`gave up:` line to stderr the moment a candidate lands, the dashboard marks the
row, and `evolve_db.py stats` counts `ineligible_parents`. A run that is quietly
producing top-of-the-leaderboard candidates nobody may build on is not making
progress, however good the trajectory looks.

**A dropped case is not a tie.** A candidate whose evaluator reported four cases
where its parent reported five is disqualified regardless of the aggregate, and
this is the rule that earns its keep first. In a constructed harness check on a
three-case suite, a candidate that simply stopped reporting the case it lost
scored 5.0 against the seed's 1.0 and went straight to the top of the
leaderboard - shrinking the suite is a benchmark game that produces the same
shape as a breakthrough. If the case set is under any candidate's control, that
is a design bug in the evaluator, not something selection can fix.

**When most of the pool goes ineligible, the number is wrong, not the
candidates.** The report warns at a third. Check `max_regression` against
`case_floor` first: a tolerance tighter than one case can be measured to
disqualifies the population by arithmetic. If the floors are honest, the edits
are too large - a strategist rewriting a whole approach preserves what the
parent solved only by luck, so brief for smaller additive changes before
touching the tolerance.

## The two-speed rule, and how it differs from winner confirmation

Under `promotion.confirm_before_steering`, greedy selection draws only from
programs carrying a `confirmed` entry; novel keeps drawing from everything. A
candidate can therefore enter the archive on a cheap noisy signal and still not
become the ancestor of a whole branch until that signal is re-earned. Recall
during exploration, precision at the point where luck would compound.

To confirm, re-measure the snapshot without recording, then attach the result:

```bash
python3 .ae/evolve_run.py --experiment . --candidate-dir generations/gen-007-a/program \
  --id gen-007-a --dry-run --repeats 9
python3 .ae/evolve_db.py confirm --experiment . --id gen-007-a \
  --score 1.284 --repeats 9 --cases /tmp/probe-gen-007-a.json
```

The confirmation **never replaces the recorded score** - the record stays as
measured. Its cases *do* replace the coverage record, because that is the same
quantity measured better, and re-sampling the parent's solved cases at higher
fidelity is exactly what a preservation probe is for.

**This is not the split-sample winner confirmation, and the two must not be
merged.** The winner confirmation protects a *reported number* against the
upward bias of a maximum over N noisy scores, which is why the skill says to do
it once, on the single winner, on a disjoint set - applying a holdout repeatedly
rebuilds the multiple-comparisons problem it exists to solve. Steering
confirmation protects a *selection decision*, its numbers are never quoted as a
result, and running it on every candidate that reaches the front of the pool
costs evaluations without biasing anything. Keep them separate in the report:
say which programs were confirmed for steering, and separately what the winner
scored on its holdout.

Confirm the seed during the design gate. Until something is confirmed the filter
has nothing to select from and falls back to the whole pool - which is correct
(a fresh run must not stall) but means the rule does nothing on generation 1.

## Failure themes

Per-candidate insights answer "why did this one die". Only the aggregate answers
"what is this run as a whole losing to", and that is the question a strategist
should be briefed on, because it is the one whose answer is a capability rather
than a patch.

Label each failure as you write its knowledge-base line:

```bash
python3 .ae/evolve_db.py label --experiment . --id gen-007-c --failure-mode gate-failed
```

The value is free-form, like `--policy`, because a closed set blocks legitimate
uses for no benefit. But **use this vocabulary unless the problem demands
another**, and fix whatever you use at the start of the run - labels invented
per candidate aggregate into forty singletons, which is the same as no labels at
all:

- `build-failed` - did not compile, link, or import.
- `gate-failed` - built, and the correctness gate rejected it.
- `wrong-output` - passed the gate and still produced a wrong answer, which
  means the gate has a hole.
- `numerical-drift` - accuracy outside the declared tolerance.
- `timeout` - exceeded the declared budget. A genuine failure: the budget is
  part of the problem statement.
- `invariant-violated` - edited outside the evolve blocks, or broke a stated
  invariant. An automatic reject, not a judgement.
- `inside-noise` - scored fine and the change was smaller than the noise floor.
  Count these: a run where this dominates is being asked for changes too small
  to see, which is a briefing problem, not a search problem.
- `unsupported-assumption` - the strategy rested on a knowledge-base claim that
  turned out to be false. The most valuable label in the list, because it
  indicts an entry rather than a candidate.
- `duplicate` - declined at triage as a recorded dead end. Worth a label even
  though it never cost an evaluation: a rising count means the knowledge base is
  not reaching the strategists.
- `never-measured` - infrastructure. The harness sets `infra_failed` itself; the
  label exists so the vocabulary is complete.

The test for adding one: **a new label must imply a different next action.** Two
labels that lead you to do the same thing are one label with extra steps.

`evolve_report.py` then names the dominant theme and warns when one mode takes
40% or more of the labelled candidates. **Inject that theme into every
strategist brief for the next generation**, phrased as the bottleneck rather
than the symptom: "setup cost is what most failures are spending their budget on
\- propose a capability that makes setup cheap", not "candidate 7c timed out". A
strategist shown only its own parent's trace cannot see a theme that is spread
across nine other candidates, and will keep proposing the local fix.

The theme is observational, so the causal rule applies: it steers what gets
proposed, and it never enters the knowledge base as something measured.

**Never label an `infra_failed` candidate with anything else.** It was not
measured, so it refuted nothing; re-score it under a new id and let the real
result carry the label. A negative record that files untested techniques as dead
ends is worse than no negative record, because a future run reads it and does
not try the idea - and nothing later can contradict an experiment that never
ran.

## Negative results are context, not templates

The failures are half of what the run produces and the more reusable half, so
they belong in front of the next strategist. But *how* they are shown decides
whether they help. A failed candidate handed over as a starting point gets
extended: the model treats the code it was given as the thing to improve, and
inherits the flaw along with the idea.

So show failures as **evidence to reason from, with the erroneous part marked**,
and never as a parent to build on. Concretely, in a brief: give the strategy,
the label, the number, and the specific step that broke - "the hoisting idea was
sound, the candidate indexed the table one element short" - rather than pasting
the broken block as the parent program. The repair slot is the one exception,
and it is explicit about being one: it is given a mechanical failure to fix,
with the failure named.

The distinction matters most exactly where the negative record is richest. A run
with fifteen labelled failures has a great deal to say about which family of
approaches keeps breaking and why, and almost nothing worth copying line by
line.

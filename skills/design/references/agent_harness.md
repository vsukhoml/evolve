# Evolving a prompt or an agent harness

Read this when the thing being optimized is not a function but the scaffolding
around a model - a system prompt, a skill document, a set of tool descriptions,
the control flow of an agent loop - and fitness comes from running that agent on
a task suite. The design phase is the same three phases; four things about the
measurement are different enough to get wrong.

## What the target is, and what it is not

The evolve blocks go in the prompt or skill file, in the host language's comment
syntax, which for markdown is `<!-- EVOLVE-BLOCK-START -->`. Everything that
decides whether a task passed - the verifier, the task set, the scoring script -
stays outside every block, exactly as for code. The rule is not weaker here; it
is sharper, because a prompt is the one artifact that can talk its way past a
judge, and a candidate that can edit its own examiner will.

Freeze the model. Every gain the run reports is then a statement about the
harness, and that is the only claim this shape of experiment can actually
support. A run that lets the model version move alongside the prompt cannot
attribute anything: the preservation probe that fires no longer tells you which
layer moved.

## Fitness is binary per task, and the aggregate is a solve rate

The natural evaluator here scores each task with the benchmark's own verifier
and returns the fraction solved:

```json
{
  "score": 0.732,
  "cases": {"task_014": 1.0, "task_015": 0.0, "task_016": 1.0},
  "metrics": {"median_turns": 22, "median_tokens": 380000}
}
```

`cases` is not optional in this shape. A solve rate is the mean of a binary
vector, and it is the single most misleading aggregate there is: two harnesses
at 0.73 can solve disjoint task sets, and the run needs to see a candidate that
picked up three tasks while dropping three others as the lateral move it is.
Declare `preserve_and_extend` with `case_floor: 0` - a binary case has no noise
floor of its own, its noise is in the sampling - and set `max_regression` to the
number of solves you are willing to trade, usually zero.

**Score each task at avg@k, not once.** Repeated runs of the same agent on the
same task diverge even at temperature zero, and on a public agent benchmark that
variance has been measured at 2.2-6.0 points of pass@1 - which is the size of a
whole accepted edit. A single rollout per task turns the case vector into a coin
flip, and the coverage machinery then disqualifies candidates at random. Put the
repeats inside the evaluator (k rollouts per task, the mean as the case value)
rather than in `evaluator.repeats`; you want k samples per *task*, not k samples
of the whole suite.

That noise is also why this archetype wants `promotion.confirm_before_steering`.
Screen at low k on a rotating subset, confirm at higher k on the full suite
before anything becomes an ancestor.

## There is no cheap correctness gate - build the action audit instead

A code experiment gets its gate for free: the project's tests either pass or
they do not, and they run in seconds. Here the verifier *is* the score, so
`correctness_gate` has nothing cheap to check, and the thing it would have
caught arrives by a different door: a candidate that satisfies the verifier by
an action the deployment would never permit - reading the evaluation plane,
fabricating state, escalating privilege, editing the task fixtures.

So write an **action-validity policy** at design time, before any candidate
exists, and enforce it as a post-hoc audit over the trajectory rather than as a
gate over the diff. Name what is permitted (ordinary observation, the
application's own operations) and what invalidates a solve whatever the verifier
said. Report both the raw and the audited score; the gap between them is the
number that tells you whether the search is optimizing the task or the harness
around it. A static-plus-LLM audit is far stronger than a keyword scan and still
not a sandbox - say which one you built.

## Budget and locking

Nothing here is timed, so declare
`"measurement": {"machine_exclusive": false, "why": "no wall-clock measurement; solve rate under a verifier"}`
and let the experiment parallelize almost linearly. The machine lock exists to
stop two benchmarks timing each other's cache pressure; a suite of agent
rollouts has no such interaction, and serializing it wastes the one resource
this archetype is actually short of.

Which is the budget. Size it in **tokens and rollouts**, not candidates: one
evaluation is `tasks x k` full agent runs, so a 90-task suite at k=3 is 270
rollouts *per candidate*, and a 40-candidate budget is over ten thousand. Say
that number out loud before generation 1. Screening on a rotating subset is not
an optimization here, it is what makes the run affordable - but then the raw
scores of candidates screened on different subsets are not comparable, and only
each candidate's change against its own parent is.

## The held-out split is mandatory, not the cheapest insurance

For a code experiment a holdout is ten minutes of insurance. Here it is the
experiment: the search reads the verifier's feedback on the very tasks it is
scored on, so in-domain gains partly measure how well it fitted the evaluation
set, and nothing in the run can separate the two. Split the tasks before
generation 1, evolve on one side, and freeze the harness before it ever sees the
other. Report the held-out number as the result and the in-domain number as
provenance. Expect the transferred gain to be a fraction of the in-domain one -
if it is not, check the split for leakage before celebrating.

## What belongs to the tuner instead

Triage this change space like any other. The parametric side is real and it is
not small: sampling temperature, k, retry and turn limits, context budget,
tool-result truncation length, how many few-shot examples. Those go to `tune.py`
with a named domain, and they must be **held fixed while the structural search
runs** - a prompt edit measured under a different temperature is confounded, and
this is the archetype where that happens most easily because both knobs live in
the same config file.

One asymmetry worth knowing before you plan a recombination slot. Structural
edits to a harness are usually *additive and disjoint* - two lineages that each
added a different skill merge by keeping both, and the merged child is accepted
if it holds the union of what its parents solved. Numeric knobs do not union:
two branches that both set the temperature conflict, and there is no "keep
both". So recombination is a move on the structural axis only, and the
parametric axis is re-tuned after a merge rather than merged.

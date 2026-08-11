---
name: orchestrator
description: >-
  End-to-end evolutionary optimization workflow - chains experiment design, the
  evolution loop, and monitoring into one flow, detecting where the user already
  is and carrying the handoff artifacts between phases. Use this skill when the
  user says "optimize this with evolve", "evolve this function", "find me a
  faster implementation of X", "make this faster and prove it", "run
  evolve end to end", or points at code and asks an automated search to
  improve it. Do not ask what they mean by optimize - a path plus "make it
  faster" is a complete request.
---

# End to end

You chain three skills and carry the state between them. The user asked for a
result, not a tour of the process - once a phase's gate is satisfied, continue
to the next one and say that you are continuing. Do not stop to ask "shall I
launch it?"; they already said so.

## Where to enter

- A goal, or code plus "make it faster" → start at **Phase 1 - Design**.
- An experiment directory with a scored baseline → start at **Phase 2 - Run**.
- A running or finished experiment → start at **Phase 3 - Monitor**.
- Something genuinely ambiguous → ask which of the three.

"Optimize my code at `<path>`" is not ambiguous. Start at Design.

## Phase 1 - Design

Load `evolve:design` and follow it end to end. It begins by interrogating the
problem itself (its Phase 0 - the problem behind the request, the null
alternative, the premise ledger); a stop there - wrong problem, or a cheaper
substitute wins - is a legitimate end state for the whole chain, delivered in an
hour instead of a budget. Its validation section is the gate, and it is where
not to economise: across a real run, essentially every wrong conclusion traced
to a harness defect rather than to the search - unrepresentative input shapes
that inverted a ranking, cross-session drift larger than the declared noise
floor. The candidates were fine; the instrument was not. All of the following
before continuing:

- [ ] `experiment.json` has a non-null `baseline_score`
- [ ] noise floor measured within-session *and* cross-session, the wider figure
  recorded
- [ ] a deliberately broken candidate was rejected by the gate
- [ ] a known-good candidate (or a calibrated regression) registered beyond the
  noise floor
- [ ] benchmark inputs audited against production's, blind spots named
- [ ] every invariant mutation-tested to find which instrument actually enforces
  it
- [ ] change space triaged - each knob assigned to a parameter search or the LLM
  loop, with reasons

Then decide, in this order:

1. **The objective cannot be a measurable value(s), or no correctness gate can
   exist** → stop the whole flow and hand off to the `evolve` consultant skill.
   A blocker, not a caveat.
2. **The noise floor is wider than the gain they want, or the budget cannot
   resolve it** → fix the harness first (repeats, workload, ratio scoring); do
   not run.
3. **The win is one profiler session away** → say that, and offer the profiler
   session instead of the two-day run.
4. **Otherwise** → state the cost - candidates × evaluation time ÷ parallelism;
   four hours agreed to up front beats four hours discovered at hour two - then
   continue: "Design complete: baseline <x>, noise floor ±<y>. Running the
   loop."

Exception: if the user's words were specifically "design an experiment" or "set
up an experiment", stopping after design is the plausible intent - check.

**Carry forward**: experiment directory, baseline score, noise floor, budget,
and the triage. If a parameter sweep is outstanding, it runs before generation
1, and the baseline carried forward is the one measured *after* its winner is
folded into the seed.

## Phase 2 - Run

Load `evolve:runner` and drive generations until the first of:

- **budget spent, or plateau above a healthy lineage count** → Phase 3.
- **the harness turns out broken** - the baseline will not score, a broken
  candidate scores well, every candidate lands inside the noise → back to Phase
  1; conclusions drawn from the candidates so far do not survive the fix.
- **the run misbehaves in any other way** → diagnose from the consultant's
  `references/run_diagnosis.md` symptom list before touching knobs.

**Carry forward**: best candidate id, gain, noise floor, review verdicts.

## Phase 3 - Monitor and close

Load `evolve:monitor` and produce the final report - closing ritual,
pre-registered read, worst input shape, the noise floor beside the gain.

Then, and only then, offer integration:

> The winner is +22.8 vs baseline (noise ±3.1), holds on held-out inputs, and
> the diff is 14 lines. Want me to apply it to `<their file>`?

Integration is a separate, explicitly requested step - the loop never writes
into the user's working tree, because candidate code is model-written and wrong
by design most of the time. On a yes: patch through `source_map` in
`experiment.json`, then run *their* test suite in *their* tree, not the
experiment's gate.

## Stepping back

If the user wants to go back a phase - "let me fix the evaluator" mid-run -
pause, load the relevant skill, and resume where you left off. The experiment
directory holds all the state, so nothing is lost by stepping back.

---
name: monitor
description: >-
  Monitor a running or finished evolution experiment: render the dashboard,
  report new bests and health warnings, diagnose why candidates are failing,
  and produce the final report with the winning diff, the gain, and its noise
  floor. Use this skill when the user asks "how is the experiment doing",
  "check on the run", "show me the results", "what's the best score so far",
  "why did those candidates fail", "is it done", or points at an experiment
  directory and wants its status. Reports only when something changed - it does
  not post heartbeats.
---

# Monitoring a run

## The dashboard

```bash
python3 .ae/evolve_report.py --experiment <dir> --write dashboard.md   # markdown
python3 .ae/evolve_report.py --experiment <dir> --json                 # for you to parse
```

Render it inline in the chat the **first** time and when the run **ends**. In
between, give the path and say what changed. Give the full absolute path so it
is clickable.

The JSON form carries the fields worth quoting: `best_score`, `baseline_score`,
`gain`, `noise_floor`, `lineages`, `since_best`, `failed`, and a `checks` list
of `[OK|WARN|BAD]` findings, each with the reasoning attached. A multi-objective
run adds `objectives`, `front`, `front_size`, `hypervolume`, and
`since_front_change` - there, the front is the result and the primary axis is
just one edge of it.

## When to speak

Post when, and only when:

- **A new best appears** - one line:
  `New best gen-012-a: -81.4 (baseline -104.2, +22.8, noise ±3.1)`. Always carry
  the noise floor; a gain without it is not yet a claim. In a multi-objective
  run the event is **the front changing** - a point joining, or displacing
  members - reported with both axes:
  `Front +gen-012-a: neg_ns=-81.4, neg_bytes=-2048 (displaced 1, front now 4)`.
- **A health check turns WARN or BAD** - quote the check and say what you
  propose to do.
- **The run reaches a terminal state** - full report.
- **The user asks.**

Say nothing on a quiet poll. "Still running, no change" trains people to stop
reading your messages, and then they miss the one that mattered. The dashboard
holds the detail; they will ask if they want it sooner.

## Monitoring a parameter search (no LLM in its loop)

When part of the problem is parametric, it runs as a standalone process rather
than a generation per agent turn (see `evolve:design`, *Take the LLM out of the
loop when the search is parametric*) - normally before generation 1, so the loop
starts from the best configuration of the current structure. Your role is
genuinely passive: it will finish without you. Read three files.

```bash
tail -5 tuning/progress.log     # is it moving, and what has it just tried
cat tuning/best.json            # the incumbent, atomically written
wc -l tuning/results.jsonl      # how far through the space
```

Poll on a human cadence - minutes, not seconds - and apply the same speaking
rule as above: a new best, a problem, or the finish. Silence otherwise.

Four things in a progress log that deserve a message, because none of them stops
the run by itself:

- **The timestamps have stopped advancing.** Distinguish hung from slow by
  whether the last line is minutes or hours old relative to the per-evaluation
  times already printed. This is why the log prints elapsed seconds per point.
- **The failure rate is climbing.** A handful of `FAILED` lines is a rough
  corner of the space; a solid run of them usually means the evaluator broke
  partway - a stale build directory, a full disk, a leaked file handle - and
  everything after that point is noise being recorded as data.
- **The best arrived in the first few evaluations and nothing has moved since.**
  Either genuine convergence, or the space is centred wrong and the optimum is
  at an edge. Check whether the incumbent sits on a boundary of any axis; if it
  does, the range needs widening and the run is answering a question narrower
  than the one asked.
- **Every point scores within the noise floor of every other.** The metric is
  insensitive to these knobs. Stop the run - the actual finding is that this
  benchmark cannot tune these parameters, and continuing produces a precise
  value fitted to nothing.

Stopping early is safe by construction: results are flushed per evaluation,
`best.json` is written atomically, and a restart resumes. So prefer stopping a
suspect run over letting it burn hours you will then distrust.

When it finishes, the tuner's own `best.json` is the answer - do not re-rank it
from the log. Give the winner the closing ritual anyway: re-measure it on a
fresh measurement set and on held-out inputs. A tuner takes far more samples
than an LLM loop does, so the maximum it reports is *more* inflated by
selection, not less.

## Reading the health checks

`evolve_report.py` flags four things, each with its reasoning inline:

- **High failure rate** - strategies too large, or the evolve block lacks the
  context needed to edit safely. Read three failure insights before theorizing.
- **Few lineages** - population collapse: everything descends from one ancestor
  and the run has stopped searching. Force novel-policy generations.
- **No recent improvement** - either the space is exhausted at this granularity,
  or the fitness function stopped discriminating.
- **Gain inside the noise floor** - nothing has been demonstrated. Raise
  `evaluator.repeats` or enlarge the benchmark before trusting any of it.

The last one is the one people argue with. It is not pessimism: if repeated
measurements of the *same* program vary by more than the improvement, the
improvement has not been observed.

## Why did candidates fail

```bash
python3 .ae/evolve_db.py show --experiment <dir> --id gen-007-b
cat <dir>/generations/gen-007-b/evaluation.json     # insights live here
```

Summarize the pattern, do not dump the output: "4 of 6 failures are the same
borrow-checker error inside the hoisted loop - the evolve block does not include
the lifetime declaration the change needs" is actionable. A wall of compiler
output is not.

If the failure rate is above ~40%, that is the finding. Say it plainly and
propose widening the evolve block or narrowing the strategy scope, rather than
reporting a leaderboard computed from the survivors.

## Lineage and provenance

```bash
python3 .ae/evolve_db.py lineage --experiment <dir> --id <best>
python3 .ae/evolve_db.py best --experiment <dir> --top 10
```

The lineage of the winner is the story of the run: which idea it descends from,
how many steps it took, and whether the intermediate steps were real gains or
lucky noise that happened to survive. It is usually more interesting than the
leaderboard, and it is what you show when someone asks what the run learned.

## The final report

```markdown
## <experiment> - final

**Result**: <gain> vs baseline (noise floor ±<x>) - <real | inside the noise>
**Pre-registered read**: <which row of experiment.json `interpretation` fired>;
  smallest gain worth acting on was <threshold> - this <clears | does not clear> it
**Budget**: <n> candidates, <m> scored, <k> rejected by review, <t> elapsed
**Winner**: `<id>`, score <s>, lineage <root> → ... → <id>

### What changed
<the winning diff>

### Verification
- Re-scored from snapshot in a fresh copy: <score>
- Held-out inputs: <score>
- Worst workload shape: <score> on <shape>
- Reviewer verdict: <accept/suspect> - <reasons>

### What the run learned
<3–5 lines, including the dead ends - those transfer to the next attempt more
often than the winner does>

### Patterns across the population
<what correlated with winning and losing across ALL candidates - secondary
metrics, policies, lineages; which regions of the design space were never
explored; which open questions survived. Observational, and labeled as such
- these are the next experiment's hypotheses, not conclusions>

### Future exploration
<2–3 concrete directions the patterns point at, each phrased as a testable
hypothesis with the probe that would discriminate it>
```

**Report the worst shape, not just the headline.** Re-score the winner across
the input shapes the caller actually sees - short inputs and long, sparse and
dense, empty and huge - and quote the weakest result beside the best. A held-out
set catches a candidate tuned to specific *inputs*; it does not catch one tuned
to an input *profile*. A 1.22× win that is 1.02× on short documents is a real
1.02× to whoever runs mostly short documents, and they will find that out in
production rather than in your report.

Every headline number must be re-derivable from a stored artifact. If you cannot
point at the file a figure came from, re-run it before writing it down.

**Close against the pre-registration.** `experiment.json` carries an
`interpretation` block written before anyone saw a number - which outcome means
what, and the smallest gain worth acting on. The report must say which
pre-registered row fired and whether the gain clears the acting-on threshold.
Interpreting the result without it is the post-hoc goalpost-moving the block
exists to prevent; if the result does not fit any pre-registered row, say that,
rather than inventing a new success criterion after the fact.

Before writing it, run the closing ritual: re-score the winner from its snapshot
in a fresh copy
(`evolve_run.py --dry-run --candidate-dir generations/<id>/program` measures
without adding a record), score it on the held-out inputs, and read the diff
yourself. If the diff holds more than one idea, ablate the components
factorially - all 2^k combinations via `--dry-run`, not one at a time, since
interactions are where recombined wins live - before crediting a mechanism. A
two-change diff credited to one change poisons every lesson the run reports. A
winner that only exists in the database is a number, not a result.

If the gain is inside the noise floor, report that as the finding, clearly, in
the first line. A run that truly says "no demonstrated improvement in 40
candidates" has saved the user the week they would have spent on the same idea
by hand - that is a real deliverable, not a failure.

**Harvest before you leave.** Append the durable lessons - measurement tricks
that worked, dead ends that generalize beyond this target, harness bugs and
their fixes - to a `lessons.md` shared across experiments (a sibling of the
experiment directory). The design phase of the next experiment reads it first.
Dead ends are only "the reusable half" if they land somewhere a future run will
actually look.

Include the **policy yield**: `evolution.json` records every candidate's policy,
so report which moves (greedy / novel / recombine / repair / simplify) produced
the real wins and which produced the dead ends, on this problem shape. The next
run's slot allocation reads it - that is the credit assignment that lets the
methodology itself improve on evidence.

Carry the final synthesis over too: the population patterns and the map's blank
regions are precisely what seeds the next experiment's rival hypotheses and seed
strategies. A pattern that dies in a closed report guides nothing.

Integration into the user's working tree is a separate step they have to ask
for. Offer it; do not do it. If they ask, `experiment.json`'s `source_map` names
the exact file and line range each evolve block came from.

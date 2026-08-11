# <experiment name>

- **Objective** - `<one sentence: what gets better>`
- **Metric** - `<exact number and units; higher is always better>`

## Numbers to know before reading any result

- Baseline (untouched seed): `<score>`
- Noise floor (same program, measured twice): `±<spread>`
- Budget: `<n>` candidates, ~`<t>` wall clock

Any improvement smaller than the noise floor has not been demonstrated. Quote
both numbers together, always.

## What a candidate may change

Only the regions between `EVOLVE-BLOCK-START` and `EVOLVE-BLOCK-END` in:

- `<targets>`

Invariants that make a candidate an automatic reject:

- <invariant>
- <invariant>

Off limits by construction: the tests, the evaluator, the benchmark data, the
correctness gate.

## Running it

```bash
# status
python3 .ae/evolve_report.py --experiment . --write dashboard.md

# pick parents for the next generation
python3 .ae/evolve_db.py select --experiment . --n 3 --policy mix

# score a candidate (the only sanctioned way to run candidate code)
python3 .ae/evolve_run.py --experiment . \
  --candidate-dir /tmp/ae-cand-<id> --id <id> --parent <parent> \
  --policy <greedy|novel> --strategy-file generations/<id>/strategy.md

# leaderboard, provenance
python3 .ae/evolve_db.py best --experiment . --top 10
python3 .ae/evolve_db.py lineage --experiment . --id <id>
```

If `tuning_plan.automated_search` is non-null and `tuning/best.json` does not
exist, run the sweep **before** the first generation and fold its winner into
`program/`, then re-score the seed and update the baseline. The loop searches
structures; the sweep searches values, without an agent in its iteration.

```bash
python3 .ae/tune.py --space tuning/space.json --command "python3 evaluator/eval_params.py" \
  --out tuning/ --method <method> --repeats <n> --noise-floor <floor> \
  --patience 40 --max-seconds <cap> 2> tuning/progress.log
```

Or hand the directory to the `evolve:runner` skill and let it drive.

## Layout

- `experiment.json` - the spec: objective, gate, evaluator, invariants, and the
  parametric/structural triage.
- `program/` - the evolving copy. **Not** the user's working tree.
- `evaluator/` - harness, benchmark inputs, `holdout/` never seen during the
  run.
- `evaluator/eval_params.py` - parameter-mode entry point the sweep drives;
  delegates to the same scorer.
- `tuning/` - `space.json`, then `results.jsonl`, `best.json`, `progress.log`
  from the sweep.
- `knowledge_base.md` - what has been tried and what it taught; read before
  proposing.
- `seed_strategies.md` - starting directions, so generation 1 is not blind.
- `evolution.json` - every candidate: score, parent, lineage, review verdict.
- `generations/<id>/` - strategy, evaluation output, and a snapshot of the exact
  program.
- `dashboard.md` - rendered status.

## Closing the run

1. Re-score the winner from its snapshot in a fresh copy.
2. Score it on `evaluator/holdout/` - inputs the run never saw.
3. Read the diff line by line.
4. Report the gain **with its noise floor**, plus what the dead ends taught.

Integrating the winner into the real source tree is a separate, reviewed step.
Nothing here writes outside this directory.

# Parameter search: choosing the method and building the driver

Read this when the change-space triage found a parametric axis and you are
writing the tuning plan and its driver. The rules - triage everything, a script
searches numbers, the loop searches structures - live in the skill; this is the
procedure for doing the parametric side well.

## First, enumerate what is actually tunable

Most targets hide more knobs than the author remembers:

- **Numeric constants in the code** - thresholds, block sizes, cadences,
  capacities, unroll factors, table sizes, bail-out limits.
- **Boolean / mode flags** - enable a fast path or not, which of two
  representations, cache or recompute.
- **Build and toolchain settings** - opt level, `target-cpu`, LTO, codegen
  units, inlining thresholds, overflow checks, allocator. These frequently
  matter more than anything in the source, and a source-level result measured
  under one setting may not survive another.
- **Structural discrete choices** - algorithm variant, data layout, split point.
- **The search's own meta-parameters** - population and island counts, migration
  interval, exploitation ratio, temperature and model mix, evaluation repeats,
  cascade promotion thresholds.

## Second, reason about the response before choosing a method

This is the step people skip, and it decides everything. For each parameter ask:
is the response monotonic, unimodal, or multi-modal? Continuous or a step
function with a threshold? Separable, or does it interact with another knob? How
expensive is one evaluation, and how does the noise floor compare to the effect
you expect?

## Third, pick the algorithm to match

The shape of the response, not habit:

- **1 parameter, monotonic or unimodal, cheap eval** → binary / ternary search,
  or a full sweep - plot it, do not just find the argmax.
- **1 parameter, small discrete domain** → exhaustive. Cheaper than arguing.
- **2–4 parameters, cheap eval, possibly interacting** → full factorial grid, or
  Latin hypercube if the grid is too big.
- **Separable parameters** → coordinate descent, one at a time - but *verify*
  separability rather than assuming it.
- **Many parameters, unknown importance** → screen first: Morris
  elementary-effects or a fractional factorial ranks which knobs matter, before
  you spend anything tuning ones that do not.
- **5–20 parameters, expensive noisy eval** → Bayesian optimization (GP or TPE);
  CMA-ES if continuous and you can afford more evaluations.
- **Genuinely competing objectives (speed vs size vs accuracy)** → NSGA-II or
  another Pareto method - return the front, not one point, and let the owner
  choose. Or MAP-Elites if you want the frontier as a browsable archive.
- **Interacting discrete flags with no gradient** → GA with crossover, or
  exhaustive over the flag subset with numeric tuning nested inside.

## Fourth, size the space before picking anything clever

Multiply the axis lengths, multiply by `repeats`, multiply by one evaluation's
wall clock. That number decides the method, and it is usually smaller than
people fear:

- **If the full grid fits the budget, enumerate it.** Exhaustive search needs no
  assumptions about separability, unimodality or interaction, and it returns the
  whole response surface rather than one point - which is what tells you whether
  the optimum is a plateau you can trust or a spike sitting on noise. A 3×4×2
  grid at 3 repeats and 20 s per evaluation is 24 minutes unattended. Do not
  reach for Bayesian optimization to save 24 minutes of a machine that is
  otherwise idle.
- **If it does not fit, screen before you narrow.** Rank which knobs matter
  (Morris elementary effects, or a fractional factorial), drop the ones whose
  whole domain moves the metric by less than the noise floor, and re-size. Most
  large spaces collapse to two or three axes that matter.
- **Only then pick from the list above**, and say in the plan what made the full
  grid infeasible. "Too big" without the arithmetic usually means nobody did the
  arithmetic.
- **Exception: ML training evaluations.** Expensive evaluations over spaces with
  low effective dimensionality flip this advice - random search beats the grid
  there. See `skills/evolve/references/ml_tuning.md` § *search-space craft*.

A space that still does not fit after screening is a signal about the evaluator,
not the search: shrink one evaluation (a cheaper screening stage, a smaller
corpus for the sweep with the full corpus reserved for confirming the winner)
rather than accepting a method whose assumptions you cannot check.

## Four rules that stop a tuning plan producing confident nonsense

1. **Prove the metric is sensitive to a parameter before tuning it.** A run
   carried `SWAR_MIN_LEN = 16` whose benchmark had no input between 9 and 35
   bytes - thresholds of 8, 11 and 16 measured *identically*. Tuning it would
   have returned a precise value fitted to nothing. If varying a knob across its
   whole domain does not move the metric by more than the noise floor, the
   experiment cannot tune it, and the honest output is "unvalidatable by this
   benchmark; argue it from the input distribution and say so".
2. **The noise floor sets the resolution.** You cannot tune to a precision finer
   than the minimum detectable difference. State that resolution in the plan.
3. **Tune on one input set, confirm on held-out.** Otherwise you have fitted the
   benchmark corpus, and a threshold is exactly the kind of parameter that
   overfits invisibly.
4. **Do not tune the search's meta-parameters on the run you are reporting.**
   That fits the searcher to the instance and inflates the result. Tune them on
   a different problem, or accept the defaults and say so.

## The driver: seven properties

`assets/templates/tune.py` is a working driver - stdlib only, adapt it. What
matters is not the file but the seven properties, each of which exists because
an unattended run is only useful if interrupting it costs nothing:

1. **One process owns the whole search.** It enumerates or samples the space,
   calls the evaluator, and finishes. The model launches it and reads progress.
2. **Every result is appended, flushed and fsynced immediately.** A `kill -9` at
   any instant loses at most the evaluation in flight. Buffered output that dies
   with the process is the classic way to lose six hours.
3. **The best point is written atomically on every improvement** (temp file +
   rename). You must never finish a long run holding a truncated `best.json`.
4. **Restart resumes.** Read what has been measured, skip it. This makes
   stopping free, which in turn makes it safe to stop.
5. **Progress is one flushed line per evaluation on stderr**, naming the point,
   its score, the incumbent, and how long it took - so `tail -f` distinguishes
   *working* from *hung*, and a new best is visible the moment it happens.
6. **It stops itself**: on a wall-clock cap, and on convergence - N consecutive
   evaluations with no improvement exceeding the noise floor. Both stated before
   the run, not chosen once results are visible.
7. **SIGINT/SIGTERM finish the evaluation in flight and exit clean.** You will
   want to stop it early; that must not be destructive.

Run it in the background and check in on a human cadence - every few minutes,
not every iteration. The model's contribution is choosing the space and the
method, noticing when the progress log says something is wrong, and folding the
result into the knowledge base. Not turning the crank.

## Four things this structure does not excuse

- **Early stopping trades optimality for time.** A patience-stopped run returns
  the best *found*, not the best. If truncation is likely, use a randomized
  order - a truncated random order is an unbiased sample of the space, while a
  truncated grid has merely explored small values of the first axis.
- **Coordinate descent assumes separability.** Verify it (vary two knobs jointly
  on a small subgrid) or it will converge confidently to a point no full grid
  would choose.
- **A failed evaluation is not a score of zero.** Record it as a failure. Zero
  is a legitimate value in many objectives, and coercing to it teaches the
  search to prefer crashes.
- **The winner still needs the closing ritual**: re-measure it on a fresh
  measurement set and on held-out inputs. A tuner maximizes over noise exactly
  as eagerly as an LLM does, and with far more attempts - so selection bias is
  *larger* here, not smaller.

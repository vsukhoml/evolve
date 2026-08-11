# Tuning ML training: meta-parameters, regimes, trade-offs

Read this when the optimization target is a model or its training pipeline -
hyperparameters, the training regime, an accuracy-versus-cost trade - rather
than a piece of code with a benchmark. Provenance for every borrowed rule is in
the README.

The general machinery already fits; use it in ML vocabulary before adding
anything:

- The split-sample confirmation rule **is** train/validation/test discipline:
  select on one set, report from a disjoint one.
- The evaluation cascade **is** low-fidelity training: fewer epochs, a data
  subset, a smaller model, promoted only on survival.
- The parametric/structural triage **is** the hyperparameter/architecture line:
  learning rate, schedule shape, batch size, augmentation magnitudes,
  regularization strengths are values a script sweeps; a new architecture, a new
  loss, a new data pipeline is a shape worth an agent turn.
- The constraint-plus-objective rule **is** the accuracy/performance trade in
  its clinical, pragmatic form.

What follows is where ML changes the constants - and two places where it
overrides the generic advice outright.

## The noise floor is seed variance

"Score the seed twice" here means *retrain with two different seeds*. Random
init, data order, and nondeterministic kernels give identical configurations
different final scores - percent-scale spread from the seed alone on standard
vision benchmarks, and in deep RL routinely enough to reverse a comparison. Most
published "improvements" that fail to replicate died on this.

- **Measure the spread across 3–5 seeds before tuning anything**, and record it
  as the noise floor. A configuration difference inside seed spread is nothing,
  however many decimal places it carries.
- **Pair the randomness across configurations** - same init where shapes allow,
  same data order, same augmentation draws. This is the ratio trick from timing
  harnesses: shared noise divides out, and paired comparisons resolve
  differences an unpaired floor cannot.
- **Record every seed in the evaluator's `metrics`**, always. Determinism flags
  buy reproducibility at a throughput cost; whether you pay it or accept kernel
  nondeterminism into the floor, say which in `experiment.json`.
- Report the mean and the spread over seeds, never the best seed. The best of N
  seeds is the same upward-biased maximum the selection-bias rules exist for.

## Low-fidelity evaluation, and where it lies

One full training run is one evaluation; at hours per run, a 40-candidate budget
is measured in days. The cascade is therefore mandatory, not an optimization -
and multi-fidelity allocators (successive halving, Hyperband, ASHA) are the
formalized version: start many configurations cheap, promote the survivors to
more epochs or more data.

The screen-validation rule from the design gate applies with a specific ML
failure mode attached:

- **Short-horizon rank order disagrees with full-horizon rank order for exactly
  the knobs people tune.** Regularization and learning-rate schedules look worse
  early and win late - the crossing-curves problem - so a truncated screen
  systematically kills them. Validate the fidelity: train a handful of
  configurations at both budgets and check the ordering broadly agrees before
  trusting the cheap stage with anything.
- **A schedule is a function of the total budget; re-anchor it, never truncate
  it.** A cosine schedule stopped at 30% is not a cheaper version of the same
  regime, it is a different (and broken) regime. At reduced fidelity, compress
  the schedule to the reduced budget.
- **"Cost to reach a threshold" metrics carry a horizon confound.** A candidate
  that configures a *longer* run can cross the threshold early in passing - its
  schedule constants are tuned to its own horizon, not to the crossing the
  metric scores. A large published autonomous run set its record by crossing the
  target at 2,920 steps while scheduled for 3,050, leaving the winning
  hyperparameters tuned to a range the metric never measured. Pin the configured
  horizon in the spec, or record it per candidate and treat crossings from
  different horizons as different experiments.
- **Use learning curves as the kill signal, not just the final number.**
  Diverged and hard-plateaued runs can be stopped early with little risk;
  ambiguous curves are the ones the crossing-curves hazard protects.

## The nuisance-hyperparameter confound

Split every knob three ways per question asked: **scientific** (the thing this
comparison is about), **nuisance** (must be tuned for *each* arm for the
comparison to be fair - learning rate above all), and **fixed** (held constant,
stated).

The consequence for the evolutionary loop is the one rule in this file that
*extends* the design skill rather than instantiating it. The design skill says
sweep the parametric axes once, before generation 1, and fold the winner into
the seed. In ML that is not enough: **the optimal learning rate moves when the
structure moves.** A structural candidate - wider layers, a new block, a
different loss - evaluated at the incumbent's learning rate is confounded, and
the confound is usually *against* the candidate, so real wins get recorded as
dead ends in the knowledge base and poison the run's conclusions.

- Give every structural candidate a small nuisance re-tune before its real
  evaluation: 3–5 log-spaced learning-rate points at low fidelity, best point
  promoted to the full evaluation. Build it into the evaluator or the
  implementer brief, and into the budget arithmetic - it multiplies the cost of
  a structural candidate by a small integer, which is the honest price of an
  uncomfounded comparison.
- Record the chosen nuisance values per candidate in `metrics`, so the
  synthesizer can see when a "structural" win was actually a learning-rate win -
  the same attribution discipline as the closing-ritual ablation.

## Search-space craft

- **Log-scale anything spanning decades**: learning rate, weight decay,
  epsilon-like constants. Momentum-type parameters live on a log scale in
  `1 - x`.
- **Conditional dimensions are real**: the optimizer choice gates its own
  parameters. Either split the space per branch or use a searcher built for
  tree-structured spaces (TPE); a flat grid over a conditional space wastes its
  budget on meaningless coordinates.
- **Random search beats grid here - an override of the generic advice.** The
  parameter-search reference says enumerate the grid when it fits; that advice
  assumes cheap evaluations and few axes. Training runs are expensive and
  hyperparameter spaces have low effective dimensionality - a few knobs matter,
  most do not - so a grid spends its budget re-testing duplicate values of the
  axes that matter while random search covers each axis's domain at full
  resolution. Quasi-random (low-discrepancy) sampling is the refinement;
  Bayesian optimization earns its complexity only above the cost and dimension
  where random stops being competitive.
- **Respect the known couplings**: learning rate re-tunes when batch size
  changes; warmup matters at large batch; the schedule is tied to the epoch
  budget. Tune the learning rate first - it dominates - and re-tune it after any
  change big enough to matter.

## The gate, for a training run

The correctness gate has a direct analog, and the judge rule has a sharper edge:

- **Gate on training health**: loss finite at every step (a NaN is a gate
  failure with an insight naming the step, not a null score), gradient norms
  bounded, the run completing, and a minimum-accuracy floor on a small canary
  set so a candidate that trains beautifully to garbage is rejected cheaply.
- **The test set and its labels live outside the evolve block**, unreadable by
  candidate code - a candidate must never be able to see the thing that judges
  it. Validation data drives selection; the test set is touched exactly once, at
  the closing ritual, and never before.
- **Repeated selection against one validation set overfits it** - this is the
  winner's curse in its original habitat, and the fix is the plugin's standard
  one: the reported number comes from data no selection decision ever saw. The
  community-scale evidence is oddly comforting - new test sets built for old
  benchmarks dropped absolute accuracy by 3–15 points while mostly *preserving
  the ranking* - but within one run the max-of-N inflation is arithmetic, not
  luck, so confirm the winner on held-out data regardless.

## Accuracy versus performance

- **Prefer the constraint form**: maximize accuracy subject to latency ≤ X -
  measured on the deployment hardware at the deployment batch size, not in
  FLOPs, not on the training GPU. A weighted sum of accuracy and speed always
  has a corner where one term buys the other in a way no owner would sign.
- **No threshold from the owner? Return the front.** NSGA-II or a MAP-Elites
  archive over the accuracy/latency plane, and let the owner pick the knee -
  that choice is a product judgement the run should expose, not make.
- **Triage the levers**: quantization bit-widths, pruning ratios, distillation
  temperature are parametric; *whether* to distill, a different backbone, an
  early-exit architecture are structural.
- **Both axes are metrics from candidate one.** A run that optimizes accuracy
  for a week and measures latency at the end has the merge argument it deserves.

## Instruments for a training run

Per candidate, in the evaluator's `metrics` and `insights`:

- the learning curve (train and validation loss versus step), so a failure says
  *diverged at step N* or *plateaued from step M* instead of `score: null`;
- seeds, chosen nuisance values, gradient-norm anomalies;
- throughput (samples/s), peak memory, wall clock - training cost is a monitored
  metric even when accuracy is the objective;
- deployment-hardware latency, whenever the trade-off section applies.

The purpose is the standard one: the scalar says whether it got better, the
instruments say why, and "why" is what the next generation is steered by.

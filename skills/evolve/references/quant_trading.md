# Trading strategies: backtests, meta-parameters, the data budget

Read this when the optimization target is a trading strategy or market signal -
tuning lookbacks and thresholds, searching for signal constructions, scoring
candidates by backtest. Provenance is in the README.

Start from what the plugin already gives you. The selection-bias rules in
`fitness_design.md` - the maximum of N tries on the same data is inflated,
correct for the number of tries, choose on one sample and report from a disjoint
one - apply here at full strength, because a backtest is nothing but N tries
against one dataset. Backtest overfitting is not a special quant risk; it is the
plugin's central enemy in its natural habitat. What follows is pragmatic
instantiation - mechanisms and empirical behavior, no theory required - and one
place where the generic advice inverts outright.

## The budget inversion: the scarce resource is data, not compute

The consultant skill asks whether evaluation is cheap relative to the budget,
and treats cheap as good. **In backtesting that reads exactly backwards.** A
backtest costs seconds, so nothing stops a loop from testing thousands of
variants against the same finite price history - and at realistic
signal-to-noise (annual Sharpe below ~1 against sample lengths of a few thousand
days), the maximum over thousands of trials on one dataset is noise that
survived selection, with high probability. Cheap evaluation is the hazard,
because the resource being spent is not wall clock; it is the dataset's finite
supply of independent evidence, and it does not refill.

- **Count the budget in hypotheses tested against the data**, not in candidates
  per hour. Declare it in `experiment.json` like any budget, and stop when it is
  spent even if the machine is idle.
- **The run knows its own trial count.** `evolution.json` records every
  candidate ever scored - including failures and screened-out ones - which is
  exactly the N the max-of-N correction needs and that manual research never
  has. Use the recorded count, bracketed by lineages as the selection-bias rules
  prescribe, and discount the winner's score by it at the closing ritual
  (`fitness_design.md` § *Selection bias*).
- **Reserve a final out-of-sample window before generation 1** - the most recent
  segment is the pragmatic choice - and touch it exactly once, at the close. A
  window consulted twice is selection data.

## Temporal data discipline

Market data is a time series from a drifting process; every split rule changes
accordingly:

- **Never shuffle.** Train/selection/confirmation splits are contiguous in time,
  ordered, with selection strictly after training and confirmation strictly
  after selection. Walk-forward (anchored or rolling) is the valid resampling
  scheme.
- **Leave a gap at split boundaries.** A label that spans time - a 5-day forward
  return - leaks across a naive boundary: the last training labels overlap the
  first test window and have already seen it. Drop the overlapping observations
  plus a safety margin, or the out-of-sample number is quietly in-sample.
- **Point-in-time everything.** Fundamentals as originally reported, not as
  restated; index membership as of the date, not today's survivors. A universe
  built from today's constituents has already read the future - the names that
  died are exactly the ones a long strategy would have held.
- **Enumerate the look-ahead vectors** in the design phase blind-spot list:
  signals computed on the close and executed at that same close, data
  timestamped by period rather than by availability, corporate actions applied
  early.

## The gate, instantiated

- **The noise test.** Run the candidate on shuffled returns or on synthetic
  random walks with matched volatility: net profit must be ~zero. A strategy
  that makes money on noise has found the backtester - a leak, a cost hole, a
  look-ahead - not the market. This is design check 3 ("break something on
  purpose") in its quant form, and it is the single highest-value check in this
  file.
- **PnL reconciliation.** Positions × price moves − costs must equal reported
  PnL, as an executable identity. Backtester bugs hide in the gap.
- **Costs are always on, and the cost model lives outside the evolve block.**
  Transaction costs, slippage, spread, borrow: a candidate that can touch the
  cost assumptions will fund its edge from them - same rule as the gate, same
  reason. Zero-cost backtests are not a baseline; they are a different
  experiment.
- **Timestamp access control.** Candidate code must be structurally unable to
  read data past the decision time - the harness serves data through an
  interface that ends at t, rather than trusting the strategy not to index t+1.
  A candidate must never be able to see the thing that judges it, and here the
  judge is the future.
- **No silent data repair.** Dropped NaN days, forward-filled gaps, and
  de-duplication belong to the harness, stated; inside the evolve block they are
  degrees of freedom for finding the dataset's holes.

## Metric craft

- **A Sharpe ratio is gameable by skew.** Short-volatility payoffs - steady
  small gains, rare large losses - backtest beautifully right up to the tail
  event the sample happens not to contain. Sharpe alone selects *for* that
  shape. Use the constraint form: maximize risk-adjusted return subject to
  maximum drawdown ≤ X, turnover ≤ Y, and report skew and tail metrics as
  monitored guards from candidate one.
- **Net of costs, at intended size.** An edge that exists only at zero turnover
  cost or zero market impact is a fact about the simulator. Turnover is a
  first-class monitored metric; capacity - does the edge survive the size you
  would actually run - is a stated assumption if not modeled.
- **Anything you would refuse to trade over is a metric**: exposure
  concentration, worst single day, time-under-water. The generic rule, verbatim.

## Plateaus, regimes, and the noise floor

- **Demand parameter plateaus.** A lookback of 17 that wins while 15 and 19 lose
  is a noise spike, not an optimum. The generic sweep advice already prefers the
  response surface over the argmax; here it hardens into an acceptance criterion
  - neighborhood robustness or it does not ship.
- **One out-of-sample window is one regime draw**, not a distribution. Report
  performance per regime (calm/stressed, rising/falling rates - whatever
  partitions the sample accurately) and say where the PnL was earned. A winner
  whose entire edge sits in one regime is a bet on that regime's return, which
  may be a fine thing to ship, but only knowingly.
- **The noise floor comes from resampling the PnL series** - block bootstrap
  (blocks, to preserve autocorrelation) gives the spread a Sharpe estimate
  carries at your sample length. It is large: at typical edges, years of daily
  data resolve Sharpe to roughly ±0.5. Differences inside it are nothing,
  exactly as with timing.
- **Edges decay.** Markets adapt: whatever made the edge gets traded away, and
  the process that generated the sample drifts regardless. Empirically an edge
  measures smaller out-of-sample than in-sample even when real, and smaller
  still as it ages. The closing report states the winner as a persistence bet
  with its regime exposure, not as a fixed property of the market.

## Triage

- **Parametric** - lookback windows, entry/exit thresholds, rebalance frequency,
  sizing fractions, stop levels. Sweep them with the driver; demand sensitivity
  before tuning (a threshold the backtest cannot discriminate across its domain
  is unvalidatable - the generic rule, and in this domain it fires constantly).
- **Structural** - the signal construction, the universe definition, the
  labeling scheme, the execution logic. These are what agent turns are for.
- **Tune sizing after the signal, not jointly.** Position sizing (a Kelly
  fraction, a vol target) optimized jointly with the signal lets leverage
  masquerade as edge; fix the signal, then size it on its realized PnL, and
  report both stages.

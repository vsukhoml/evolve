# Framing: is this the right problem?

Read this at Phase 0, before any spec exists. Phase 1 clarifies *how to
measure*; this file asks whether the thing about to be measured is the thing
worth measuring. The failure it prevents is the most expensive one in the whole
pipeline and the only one no downstream check can catch: a well-designed
experiment, cleanly measured, answering a question nobody needed answered. An
hour of interrogation is the cheapest insurance a run can buy.

The output is not a feeling of due diligence. It is a written `framing` block
(format at the end) whose entries feed named downstream artifacts - and a
decision: proceed, reshape, or stop. Stopping here is a success, at the lowest
price success is ever available for.

## The problem behind the request

Requests arrive as chosen solutions. "Make X faster" is not a problem; it is one
candidate answer to a problem that has not been stated yet, and optimizing the
stated request can miss the actual need entirely.

- **Ask what becomes possible, or stops hurting, if this succeeds.** Then ask
  why *that* matters, and once more. Stop when the answer is an outcome someone
  would pay for; that outcome, not the request, is what the experiment must
  serve.
- **What does the problem cost today, and measured by whom?** A pain nobody can
  quantify is a pain nobody will notice being fixed - which also means no one
  can say whether the run was worth its budget. Estimate to the precision that
  changes the decision and no further: one significant figure usually ranks this
  work against its alternatives, and extra decimal places on a speculative
  estimate are effort, not information.
- **Whose problem is it?** The person who feels the pain, the person who owns
  the code, and the person who must accept the change are often three people
  with three different constraint sets. Collect all three; the merge-refusal
  conditions of the acceptor are invariants (Phase 1 consumes them).
- **Is the target the bottleneck of the real problem?** Fraction of end-to-end
  cost, before anything else: a target that is 18% of the total caps the whole
  exercise at 1.22× no matter how well the search goes. The ceiling arithmetic
  lives in the pre-mortem (`skills/evolve/references/pre_mortem.md`); run it
  here, where it can still change the target instead of just the expectations.
- **Why now?** What changed to make this worth a budget this month? "It has
  always been slow" is a reason to suspect it does not actually matter.

## The null alternative

Every experiment competes with the cheapest acceptable way of not running it.
Enumerate the alternatives explicitly:

- **Do nothing** - what concretely breaks, and when?
- **Spend money instead of search** - bigger instance, more replicas, a faster
  disk. If a hardware line item buys the same outcome, the experiment is a
  procurement decision wearing a lab coat.
- **Change the caller** - cache, batch, precompute, move the work off the hot
  path. Often cheaper than making the work faster.
- **Adopt instead of discover** - a library, a known algorithm, a competitor
  implementation. If the answer is known, the consultant's rule applies: just
  make it.
- **Relax the requirement** - is the deadline, tolerance, or scale actually
  load-bearing, or inherited?
- **Wait** - code scheduled for rewrite makes any optimization a lease, not a
  purchase. Unless the work transfers, or raises the efficiency bar the
  successor must clear - then its effect outlives the implementation.

Name the strongest alternative in the `framing` block. The run's result will be
compared against it at the close, so choosing it honestly now prevents the
comparison being invented flatteringly later.

## Stating it correctly

- **One sentence, one measurable outcome, direction and units.** If the problem
  cannot be said this way yet, it is not ready for Phase 1 - keep interrogating.
- **Say the proxy distance out loud.** The metric connects to the felt outcome
  in one stated sentence ("p50 batch latency tracks the report generation the
  customer waits on") or it is a proxy chosen for convenience, and the run will
  optimize the convenience.
- **Say whether the goal is a threshold or a frontier.** "Reach X" ends the
  moment X is reached; "as good as possible within the budget" never ends on its
  own. The two shapes want different stopping rules, different budgets, and
  different reports, and a run that internalizes the wrong one either stops
  early or burns budget past the point of value. In a large published autonomous
  run the goal was frontier-shaped, the agents read it as threshold-shaped, and
  a human had to intervene mid-run to restate it - written in the docs was not
  enough. State the shape here and repeat it in the stopping rules.
- **Name the instance distribution.** Faster *for which inputs*, at which scale,
  on which hardware? These answers are what the benchmark audit (design check 5)
  will later be checked against; unstated here means unauditable there.
- **State the asymmetries now.** The smallest gain that changes any decision
  (feeds pre-registration), and what must *not* get worse to make a gain
  acceptable (feeds the monitored metrics and guards). A goal with no stated
  floor under the other metrics is an invitation to trade them away invisibly.

## Naming the domain

- **What is this problem called, and by whom?** Most problems are instances of a
  named class - interval stabbing, bin packing, top-k selection, string
  searching. The name is the key that unlocks the prior-art search (Phase 1's
  highest-return step consumes it); a problem with no name cannot be searched,
  only re-derived.
- **What does the domain say is impossible?** Every field carries its own bounds
  - information-theoretic limits, roofline arithmetic, conservation laws,
    no-free-lunch trades. Knowing them here prevents a run whose target sits
    past the wall.
- **Where is the system boundary?** What is inside the search, what is fixed
  environment, and what is shared with neighbors (cache, bandwidth, a database)
  that the experiment could disturb or be disturbed by. And where does the
  *effect* land? Some real wins worsen the component's own metric while
  improving the whole (a prefetch that makes the allocator look slower and the
  application faster), or deliver their benefit in a different component than
  the one being changed - measure at the boundary where the effect materializes,
  or a genuine win will be recorded as a loss.

## Use context

The deployment reality is where constraints come from; collect it before
inventing any:

- **Who runs it** - platform, scale, invocation frequency, latency-sensitive or
  throughput-sensitive, cold-start or steady-state.
- **Who maintains it** - a solo owner on a long horizon prices complexity
  differently from a staffed team; the complexity budget is a framing fact, not
  a review-time surprise.
- **Who merges it** - their refusal conditions, collected verbatim, become
  invariants. Ask directly: "what would make you reject a 2× win?"
- **The exchange rates** - what the owner would actually trade for the gain:
  memory for speed, portability for speed, readability for speed, and at what
  ratio. Phase 1's constraint questions refine these; Phase 0 establishes that
  they exist.

## The premise ledger

The framing rests on beliefs, and beliefs are held in different ways. Write down
every load-bearing premise - "the hot loop is memory-bound", "inputs are mostly
under 64 bytes", "the tests cover the rounding modes" - and label each with *how
it is held*, using the knowledge base's own vocabulary:

- **measured** - by whom, when, on what data. The only label that closes a
  question.
- **reported** - someone said so. Second-hand measurement is testimony, not
  measurement; note whose.
- **inferred** - derived from other premises; wrong whenever they are, plus
  whenever the derivation is.
- **assumed** - held because holding it is convenient. The default label for
  anything nobody can source.

Then work the ledger:

- **For each premise, name what would change it and what checking costs now.** A
  profile, a histogram of real inputs, a `grep` - many decisive checks cost
  minutes. Check everything cheap-and-decisive before designing; a real run's
  knowledge base was wrong twice from a number inherited rather than re-derived,
  and each error steered a whole generation.
- **Score importance separately from confidence.** The high-importance /
  low-confidence corner of the ledger *is* the reconnaissance agenda: those
  premises become the rival hypotheses and probe candidates of the run's early
  generations (`evolve:runner` § reconnaissance).
- **Separate the three kinds of not-knowing.** Nobody-has-looked wants a
  measurement; we-disagree wants the owner to decide; cannot-know-yet wants a
  design that hedges. Naming which kind each open question is prevents measuring
  a disagreement or voting on a measurement.
- **Ask the owner the highest-yield question directly:** "what do you believe
  about this system that you have never personally verified?" The answer is
  usually the most important row in the ledger, and it arrives pre-labeled.
- **Close with: "what should I have asked that I did not?"** It costs one
  sentence and regularly returns the constraint everyone forgot was not written
  down.

## The output

Write the conclusions into `experiment.json` under `framing` when Phase 1
creates it:

- `problem` - the problem behind the request, one sentence, outcome-shaped.
- `null_alternative` - the strongest cheaper substitute, and why the run beats
  it (or the honest note that it might not).
- `domain` - the problem's name and the bound the domain imposes.
- `use_context` - who runs, maintains, merges; the exchange rates.
- `premises` - the ledger: statement, label, falsifier, and status for each.
- `decision` - proceed, reshape (with the reshaped statement), or stop.

Each entry has a consumer: `use_context` feeds `invariants`; `domain` feeds the
prior-art search; the ledger's weak rows feed reconnaissance; the smallest-gain
and must-not-worsen answers feed pre-registration and the guard metrics. A
framing entry nothing downstream consumes is decoration; delete it or wire it.

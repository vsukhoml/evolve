# Inventive principles: a TRIZ-derived checklist for code

A generative grammar for strategists - the novel policy, the seed strategies,
and anyone staring at a run that only proposes variations of what exists. TRIZ's
core claim transfers to optimization intact: when improving X worsens Y, the
weighted compromise is the move of last resort; most contradictions can be
*resolved* - X gained without paying Y - by restructuring.

Use only what is below - the Ideal Final Result, the four separations, a curated
subset of the 40 principles, and resources thinking. The rest of TRIZ (the 39×39
contradiction matrix, ARIZ, Su-Field analysis) was distilled from mechanical-era
patents and does not earn its weight on software; do not go looking for it. This
is a checklist that *generates* candidates; the evaluator still decides.

## Name the contradiction first

Every optimization worth running has a central trade: faster but bigger, faster
but less accurate, simpler but slower, general but heavy. State it as
**"improving X worsens Y"** - the design skill records it in `experiment.json`
as `contradiction`. A named contradiction gives strategists an axis to work;
without one, the run drifts into micro-variations of the seed. (This is also why
`fitness_design.md` prefers a constraint plus one objective over a weighted sum:
the weighted sum *prices* the contradiction, which invites paying it, instead of
resolving it.)

## The Ideal Final Result

Ask: **what if this step did not exist at all?** The computation costs nothing
because it never happens. Concrete forms, in order of ambition:

- **Eliminate** - is the result ever consumed? Is this precision, this
  generality, this pass actually needed by the caller?
- **Precompute** - move the work to build time, design time, or first use.
- **Hoist** - out of the loop, up to the caller, into initialization.
- **Memoize accurately** - cache keyed on real inputs. (The harness randomizes
  inputs precisely so that faulty memoization dies at the gate.)
- **Defer** - compute only what is observed, when it is observed.

The IFR question generates the architectural candidates that local mutation
never proposes. It belongs in generation 1's seed strategies, not as a
generation-12 afterthought.

## The four separations

For the sharper form - the same thing must be A *and* not-A - TRIZ separates:

- **In time** - expensive setup once, cheap steady state; accumulate then
  process in batch; amortize across calls.
- **In space** - hot/cold data splitting; struct-of-arrays layouts; a fast
  structure in front of an authoritative one.
- **Upon condition** - *the fast path*: the common case handled cheaply, the
  rare case handled correctly by a fallback. The single most productive move in
  this file - optimistic paths, small-size specialization, happy-path parsing
  with a strict slow lane.
- **Between scales** - properties enforced per batch instead of per element; a
  vectorized inner loop under a general outer one.

## A curated dozen of the 40 principles

Each entry: TRIZ principle number and name, then the software move.

- **1 Segmentation** - tiling/blocking, chunked processing, SIMD lanes.
- **2 Taking out** - pull the rare case out of the hot loop; validate at the
  boundary, not per element.
- **10 Preliminary action** - lookup tables, precomputed state, perfect hashing
  - sized against the stated constraints.
- **13 The other way round** - iterate backwards, compute the complement, invert
  control (push → pull).
- **15 Dynamics** - hybrid algorithms that switch by size or shape - introsort's
  cutover, small-buffer optimization.
- **17 Another dimension** - change the layout: AoS→SoA, bit-planes, transpose
  the loop nest.
- **20 Continuity of useful action** - fuse passes so data is touched once; keep
  the expensive unit busy; pipeline.
- **21 Skipping** - stream instead of materializing intermediates; process at
  full speed through, not stage by stage.
- **25 Self-service** - structures that maintain their own invariant -
  sentinels, intrusive links, tombstones.
- **26 Copying** - a cheap approximation first, exact verification after - the
  screen/verify shape.
- **28 Mechanics substitution** - replace branches with arithmetic or masks,
  comparisons with subtraction, pointers with indices.
- **35 Parameter changes** - change the representation: fixed-point for float,
  deltas for absolutes, sorted for hashed.

## Resources: what is already free

TRIZ's resource discipline - use what the system already has before adding
anything:

- **Idle bits** - alignment guarantees, unused high bits, padding already paid
  for (checked against portability constraints).
- **Existing passes** - work folded into a loop that already touches the data,
  instead of a new pass.
- **Work the caller already did** - sortedness, validation, lifetime guarantees
  the API contract provides.
- **Compile-time knowledge** - constants, monomorphization, sizes known
  statically.
- **The measured input profile** - the distribution the design phase
  established. A fast path is only fast if the common case is actually common;
  the profile says what is.

## Using this in a run

The novel-policy strategist works the sequence: name the contradiction the
current best embodies → try the IFR question → try the four separations → only
then propose a variation. Seed strategies come from crossing this checklist with
the prior-art findings - that is the *transfer* and *hybrid* requirement made
mechanical.

Every move still passes the constraint filter (table sizes, `unsafe`,
portability, dependencies) and the invariant checks. This grammar makes
candidates; it never excuses one.

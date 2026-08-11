# Numeric accuracy: the five rules

Read this whenever the operation is numeric and a candidate may reassociate,
widen, narrow, or approximate. A search *will* find speed by quietly spending
precision, and a correctness gate built from equality on a few test values will
not notice. Floating point makes this sharper than it sounds, because addition
is not associative (a candidate that restructures a loop has changed the
*answer*, not just the speed) and because failure is silent (NaN compares false
against everything, so a `max` over NaNs returns garbage instead of crashing).

Five rules, all decided before any code exists:

1. **Pick the equivalence policy and write it into `invariants`.** There are
   only three acceptable choices. **Bit-identical** - required for money math,
   cross-platform determinism, anything with a golden-file test; it forbids
   reordered reductions, FMA-contraction changes, fast-math flags and most
   vectorization, so say so or the run will spend its budget discovering
   optimizations the policy rejects. **Tolerance band** - state the bound and
   *where it is measured*. **Different-but-valid** - for constructions and
   heuristics where any feasible answer counts; then the checker carries all the
   weight, so make it exact (integer or rational) rather than letting a
   candidate exploit the checker's own epsilon.
2. **Pin the compiler's FP flags identically for baseline and candidates.** If
   `-ffast-math`, FMA contraction or reassociation differ between the two
   builds, the comparison is meaningless.
3. **A tolerance band is a reward-hacking surface.** A candidate will trade
   accuracy for speed right up to the edge of the band, because that is what the
   search rewards. Make the band as tight as the domain allows, and check it in
   the gate at benchmark scale - never inside the evolve block.
4. **Safe-math guards live outside the evolve block.** Clamps, epsilon
   protections, divergence checks, iteration caps: inside the block, a candidate
   "fixes" instability by widening the clamp - score up, numerics worse. Same
   rule as the gate, for the same reason. For iterative code, cap iterations in
   the harness and treat a cap hit as a *gate failure with an insight*, not a
   timeout, which reads as a crash and hides the pattern.
5. **Condition the benchmark inputs deliberately** - near-cancellation cases,
   wide dynamic ranges, denormals, values right at the tolerance boundary - in
   the gate *and* the held-out set. Well-conditioned inputs invite candidates
   that are fast precisely because they are sloppy, and a well-conditioned
   held-out set will not catch them.

When a candidate does go non-finite, name *where*: check intermediates, not just
the final score, and emit an insight like "NaN first seen in iteration 3 of the
accumulation loop". `score: null` teaches the run nothing, and by the time a NaN
reaches the score it has erased its own origin.

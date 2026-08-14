# Low-level performance moves

Read this when the optimization target is low-level software performance - a hot
loop, a kernel, a parser, a data structure - and you need candidate strategies
grounded in how machines actually spend time. Not every experiment is this; for
other targets skip it. It pairs with `inventive_principles.md` (shape-level
moves) and `perf_harnesses.md` (measuring without fooling yourself). The moves
are distilled from the practice of large-scale systems engineering; provenance
is in the README.

Two rules for using the menu:

- **Each move is a hypothesis, not an instruction.** It enters the run as a seed
  strategy or a strategist proposal with an expected effect and a falsifier, and
  it earns nothing until the harness scores it.
- **Triage every move before spending a candidate on it.** Many of these reduce
  to a value a script can sweep - a table size, an inline capacity, a sampling
  rate, a chunk size. Those belong in the tuning plan
  (`skills/design/references/parameter_search.md`), not in the LLM loop. The
  structural ones - a different representation, a fast/slow split, a fused pass
  - are what agent turns are for.

## Estimate before you search

Back-of-the-envelope arithmetic - count the irreducible low-level operations,
multiply by unit cost, sum - answers in twenty minutes what a generation of
candidates answers in hours, and it is the same arithmetic as the design skill's
speed-of-light bound. Unit costs to carry (approximate, and the *ratios* matter
more than the values - re-derive them on the experiment's machine when a
decision hangs on one):

- L1 cache reference - ~0.5 ns
- Branch mispredict - ~5 ns
- L2 cache reference - ~3 ns
- Uncontended mutex lock/unlock - ~15 ns
- Main memory reference - ~50 ns
- Read 1 MB sequentially from memory - ~64 µs
- Read 4 KB from SSD - ~20 µs
- Datacenter round trip - ~50 µs
- Read 1 MB from SSD - ~1 ms
- Disk seek - ~5 ms

The point of the exercise: it names the dominant term. A sort estimated at 7.5 s
of memory bandwidth and 75 s of branch mispredicts is a mispredict problem, and
candidates that attack anything else are spending budget on a term that cannot
pay.

## Where the wins live, in order

1. **Algorithmic class.** O(N^2) → O(N log N) → O(N) → O(1) beats everything
   below, every time. Replace a sorted-merge intersection with a hash probe;
   replace a per-edge cycle check with an insertion order that makes cycles
   impossible; replace a search with a precomputed index. Exhaust this level
   before descending.
2. **Memory representation.** Most "CPU" problems are memory problems wearing a
   disguise: alignment, access patterns, cache misses and allocator traffic.
3. **Allocation.** Each allocation costs allocator time, construction and
   destruction, and a fresh cache line of footprint.
4. **Unnecessary work.** Fast paths, precomputation, hoisting, deferral,
   specialization.
5. **Compiler-level mechanics.** Last, smallest, and least portable - attack
   only with the disassembly open.

## Memory representation moves

- **Shrink the struct** - reorder fields by alignment to kill padding; downsize
  numeric types; give enums a byte (`enum class X : uint8_t`). Mostly
  parametric: the layouts are enumerable.
- **Split hot from cold** - frequently-accessed fields together; hot read-only
  fields on a different cache line from hot mutable ones; cold data at the end,
  behind an indirection, or in a parallel array.
- **Indices instead of pointers** - 32-bit (or smaller) indices into an array
  halve the footprint of pointer-rich structures and localize what they
  reference.
- **Flat instead of node-per-element** - vectors and open-addressing hash maps
  over pointer-chasing maps; one contiguous block over N small nodes.
- **Inline small-count storage** - containers with inline capacity avoid the
  allocation entirely when the common count is small. The capacity is a
  sweepable value; the caveat is a large element type, which turns inline
  storage into bloat.
- **Flatten nested maps** - `map<a, map<b, c>>` becomes `map<pair<a, b>, c>`:
  one lookup, one allocation per entry. Unless the outer key is large, in which
  case the nesting was the compression.
- **Arenas** - allocate related short-lived objects together, free them as one.
  Kills destruction cost and scatters nothing. Do not put short-lived objects in
  a long-lived arena; that is a leak with better locality.
- **Arrays over maps, bits over sets** - a small integer or enum domain wants a
  plain array; a small-domain set wants a bit vector and bitwise set operations.
  A published example took 26–31% off a hot path by replacing a hash set of
  small integers with an inlined bit vector.
- **Arrays of Structures** vs. **Structure of Arrays** - depends on processing
  done, access patterns, opportunity for the vectorization.

## Allocation moves

- **Do not allocate what exists** - share one static empty/zero instance instead
  of constructing it per call. A published example bought 21% throughput from
  exactly this.
- **Reserve when the size is known** - `reserve` then append; never grow one
  element at a time. Prefer `reserve` + `push_back` over `resize` when
  construction is expensive.
- **Move, view, or index instead of copying** - pass views (`string_view`,
  spans), move what transfers ownership, and sort indices into large objects
  rather than the objects.
- **Reuse temporaries across iterations** - hoist the buffer, the protobuf, the
  string out of the loop so its capacity survives. Caveat: such objects grow to
  their high-water mark; reconstruct every N uses if inputs vary wildly.

## Avoiding work

- **Fast path for the common case** - the single most productive move in
  low-level code, and the `inventive_principles.md` "upon condition" separation
  wearing work clothes: handle the dominant simple case cheaply, fall back to
  the general routine for the rest. The split point is a sweepable value; the
  split itself is structural. The gate must exercise both paths, or the fast
  path is where correctness quietly leaves.
- **Precompute** - lookup tables for per-element decisions, predicate bits
  computed once instead of chains of checks per use, validation done at the
  module boundary instead of re-checked in every callee. Table size versus cache
  footprint is a measured trade, not a free win.
- **Hoist and defer** - loop-invariant computation moves out of the loop;
  computation whose result may never be read moves behind the read. A published
  example cut a pass from 43 s to 2 s by deferring one call until needed. Stats
  and counters are the classic offenders: compute on demand, or maintain them
  for a 1-in-2^k sample so the sampling decision is a mask.
- **Specialize** - replace the general library call on the hot path with the
  three lines it actually needs: prefix match instead of a regex engine, direct
  formatting instead of printf machinery (a published example: 4×). The general
  call was correct; it was also carrying generality nobody ordered.
- **Cache on a cheap key** - fingerprint the expensive input once and key the
  derived result on it. The reward-hacking caveat from the design skill applies:
  a cache the benchmark reuses across timed calls measures the cache, not the
  code.
- **Keep logging off the hot path** - a disabled log statement still costs a
  load and a branch and can block optimization around it. Precompute "enabled"
  outside the loop, or delete the statement.

## Help the compiler

Compilers optimize what they can prove. On a very hot loop, with the disassembly
or `llvm-mca` open (`skills/design/references/instruments.md`):

- **Keep calls out of the hot function**; move the slow path into a separate
  function so the hot one needs no frame and inlines cleanly.
- **Copy hot values into locals** before the loop - a local provably aliases
  nothing, a field or span element does not.
- **Drop to raw pointers in the innermost loop** when the abstraction defeats
  vectorization or bounds-check elimination - and let the reviewer weigh what
  that costs in safety and readability against what it measured.
- **Hand-unroll only what the profile says is very hot**, in chunk sizes a
  script can sweep, and re-measure across build flags: these wins are the least
  portable in this file, and one that exists only at one flag combination is a
  fact about the build.

## API-shape moves

Relevant only when the evolve block includes an interface:

- **Bulk operations** - one boundary crossing for N items amortizes per-call
  overhead that no amount of inner-loop work removes.
- **Accept precomputed arguments** - take the timestamp, the hash, the parsed
  form from the caller who already has it, instead of re-deriving it inside.
- **Thread-compatible by default** - synchronization belongs to the caller who
  needs it, so the caller who does not is not paying for it. Move it inside only
  when every caller synchronizes anyway.

## When the profile is flat

No hotspot is not "nothing to do" - it narrows the strategy set:

- **Blame the application-level caller, not the shared leaf.** Cycles land in
  `memcpy`, `push_back`, the allocator - shared functions nobody should optimize
  at that level. Re-attribute their cost upward to the nearest
  application-specific caller before picking targets: that is where the
  unnecessary copy or the missing `reserve` actually lives.

- **Stack many small wins** - twenty 1% improvements compound, but only when the
  noise floor can resolve 1%, which is a statement about the harness
  (`perf_harnesses.md`), not the ideas. If it cannot, fix the measurement before
  proposing anything.

- **Climb the call stack** - flame graphs find the loop three frames up whose
  restructuring (build the structure in one shot instead of incrementally)
  removes the flatness wholesale.

- **Profile allocations and cache misses, not just CPU time** - the top
  allocator client and the worst-missing function are hotspots the time profile
  hides.

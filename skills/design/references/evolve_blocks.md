# Evolve blocks: deciding what a candidate may change

```
# EVOLVE-BLOCK-START
def classify(values, table):
    ...
# EVOLVE-BLOCK-END
```

The exact spelling - `EVOLVE-BLOCK-START` and `EVOLVE-BLOCK-END`, hyphens, all
caps - is what the harness and the reviewer look for. Variants with underscores
are silently ignored, and the failure mode is a run where nothing ever changes.

Use the host language's comment syntax: `//` for Rust, C, C++, Go, Java; `#` for
Python, Ruby, shell; `--` for Haskell, SQL, Lua.

## How much to enclose

The block has to contain everything that must move together. Too small and every
interesting change is impossible; too large and the search wanders.

**Inside the block:**

- The function or region being optimized.
- Helper functions only it uses.
- Constants and tuning parameters it depends on - thresholds, block sizes,
  unroll factors. These are often where the wins actually are.
- Data-structure choices local to the region.

**Outside the block, always:**

- Tests, and anything they import.
- The timing harness and the benchmark data.
- The correctness gate.
- Public API signatures the invariants promise not to change.
- Imports and module setup the rest of the file needs (unless the candidate
  genuinely needs to add imports - in which case include the import block and
  say so in the invariants).

The rule behind all of that: **a candidate must never be able to edit the thing
that judges it.** Everything else is a judgement call about search space; this
one is structural.

## Multiple blocks

Several blocks in one file, or across files, all evolve together as one
candidate. Use them when the change has to be coordinated - a struct definition
in one place and the loop that walks it in another. Do not use them to fence off
five unrelated regions in the hope of getting five independent searches; you get
one search over their product, which is much larger and much slower.

## Sizing it, concretely

- **Under ~20 lines**: expect small parameter tweaks and little else. Fine for
  tuning, disappointing for algorithm discovery.
- **~50–200 lines**: the productive range for most experiments. Enough room to
  restructure, small enough to reason about.
- **Whole file / multiple files**: only when the objective genuinely requires
  cross-cutting change. Failure rates climb sharply, so raise the budget and
  expect the reviewer to work harder.

If the failure rate is high, the block is usually too *small*, not too large -
the candidate cannot see the context it needs to make a coherent edit, so it
guesses. Read three failures before adjusting; the insight text usually names
the missing piece.

## Seeding for diversity

The seed program inside the block should be the **simple, obvious, correct**
implementation, even if the user already has a clever one. Two reasons: it gives
a valid baseline, and starting from the clever version anchors every strategist
to that approach, which is exactly the population collapse you are trying to
avoid.

If the user's existing implementation is already tuned, keep it - but seed
`seed_strategies.md` with two or three deliberately *different* directions so
generation 1 explores rather than polishes.

For real starting diversity, go one step further: score 2–3 structurally
different seed variants as generation-0 roots, each with `--new-lineage`. Every
lineage otherwise descends from a single program, and the novel policy has to
escape that basin the hard way. The variants should come from the prior-art
search - different *shapes* of solution, not three tunings of the same one.

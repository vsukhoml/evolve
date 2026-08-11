# Building a benchmark harness that can be trusted

For performance experiments, the harness is where the experiment succeeds or
fails. These are the per-language recipes plus the rules that apply everywhere.

## Rules that apply to every language

- **Median of ≥5 repeats**, and record the spread. One sample is not a
  measurement.
- **Warm up** before timing, then time separately. Otherwise you are measuring
  JIT compilation, page faults, or a cold instruction cache.
- **Consume the result** so it cannot be optimized away - a `black_box`, a
  volatile write, an accumulated checksum the harness asserts on.
- **Fresh process per candidate** where affordable. Shared process state is how
  one candidate's allocator warm-up becomes the next one's speedup - and in any
  language with a module cache it is worse than that: an evaluator that scores
  several candidates in one process by putting each candidate's directory on the
  import path will import the *first* one and then serve it from cache forever,
  silently scoring every later candidate on code it never ran. The symptom is a
  run where dozens of very different candidates all score within noise of each
  other, which reads as "the space is exhausted".
- **Quiet the machine**: fixed CPU governor, no concurrent build, pinned core
  where the platform allows. Note in the report whether you managed this - a
  benchmark run on a laptop with a browser open has a much wider noise floor and
  the reader deserves to know.
- **Assert the output is still right** inside the timed harness, on a checksum
  the benchmark input makes non-trivial. This closes the "returns instantly
  because it returns nothing" hole cheaply.

## Measurement bias: the machine has an opinion about your code

Details that have nothing to do with your change move the measurement anyway.
The size of the process environment shifts stack alignment; link order shifts
code and data layout. Either can shift performance by more than the effect you
are studying - enough, in a controlled study across several CPUs and two
compilers, to *reverse* the measured sign of `-O3` versus `-O2`. A single
configuration measured very carefully is still one draw from a biased
distribution.

Three consequences, in order of what to do first:

1. **Prefer a paired, order-randomized comparison against the reference in the
   same process.** Time the candidate and the untouched reference back to back
   on the same input, alternate which goes first, and score the ratio. Layout
   luck, drift and thermal state hit both arms and divide out. This is the
   cheapest thing on the list and it routinely turns a 6–7% noise floor into a
   sub-1% one.
2. **Randomize the setup when the floor is still too wide.** Measure both
   variants across many environments - vary environment size and link order -
   and compare the two *distributions*, not two means. Randomizing inadequately
   just buys you a different bias, so vary the thing you suspect.
3. **Intervene to confirm a cause.** If you think layout explains a result,
   change the layout deliberately and re-measure. That gives confidence, not a
   guarantee.

And the corollary that decides benchmark design: **a bigger benchmark suite does
not reduce this bias - only a more diverse one does.** Adding more inputs of the
shape you already have buys nothing.

## C / C++

- Benchmark: Google Benchmark (`benchmark::DoNotOptimize`,
  `benchmark::ClobberMemory`), or a hand-rolled loop over
  `std::chrono::steady_clock` with the same guards.
- Profile: `perf record` / `perf stat` for cycles, cache misses, branch
  mispredicts. `pprof` where the toolchain provides it.
- Correctness gate: the project's tests, and this is the ecosystem where
  sanitizers earn their keep - build the gate with **ASan + UBSan**, and
  **TSan** separately if threads are involved. An "optimization" that introduces
  a data race will otherwise pass the gate and score beautifully, because a race
  is fast until it isn't.
- Assembly: `objdump -d` on the hot symbol, diffed against the baseline. When a
  candidate's win is real, the asm diff usually shows why in a few lines - and
  when it is fake, the diff shows the work missing entirely.

## Rust

- Benchmark: criterion (`black_box`, and criterion's own outlier reporting is a
  free noise-floor estimate), or `#[bench]` on nightly.
- Correctness gate: `cargo test`, plus `cargo clippy -- -D warnings` if lint
  cleanliness is a constraint you care about. If the crate is `unsafe`-free by
  policy, grep the diff for `unsafe` in the reviewer step.
- Assembly: `cargo asm -p <crate> --lib <path::to::fn> --rust` interleaves
  source with the generated code, which makes an asm diff readable rather than
  archaeological.
- Miri catches UB in unsafe code but is far too slow for the evaluation loop -
  run it once on the winner, not per candidate.

## Go

- Benchmark: `go test -bench . -benchmem -count=10`, and feed the output to
  `benchstat` - it reports the delta *with a significance judgement*, which is
  exactly the noise-floor discipline this whole document is about.
- Profile: `go test -cpuprofile`, then `go tool pprof`.
- Correctness gate: `go test ./... -race`.

## Python

- Benchmark: `pytest-benchmark`, or `timeit` with an explicit repeat count.
  Expect a wide noise floor; take more repeats than feels necessary.
- Profile: `cProfile` + `snakeviz`, or `py-spy` for sampling without
  instrumenting.
- Watch for the two Python-specific gaming moves: importing a C library that
  changes what is being compared, and moving work into module import time, which
  most timers do not cover.

## What to record per candidate

Beyond the score, record whatever makes a later argument possible without a
rerun: the raw samples, the spread, and any secondary metrics (instructions,
cache misses, allocations, binary size). They cost nothing at evaluation time
and they are the difference between "it got faster" and "it got faster because
the inner loop stopped missing L2".

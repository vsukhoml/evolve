# The instrument menu

Read this when deciding which instruments the harness carries beyond the timer.
Pick from what the problem actually makes load-bearing:

- **Timing** - the fitness metric itself, with spread and repeats.
- **Disassembly of the hot region** - instruction and branch counts per unit of
  work. The cheapest instrument that explains a result, and it turns "it got
  slower" into "it added two instructions per digit".
- **Static microarchitecture analysis** - `llvm-mca`, `uiCA`, or the vendor
  equivalent. This is the instrument that directly answers *latency-bound vs
  throughput-bound vs front-end-bound*, which is usually the single most
  valuable fact about a hot loop and the thing a run will otherwise argue about
  for generations from timing slopes.
- **Hardware counters** - `perf stat` for branch misses, cache misses, IPC, when
  the static model is not enough.
- **Allocation count and peak/stack usage** - mandatory when the target is
  embedded, `no_std`, or latency-sensitive.
- **Code size and read-only data** - `size -A`, symbol sizes. A candidate that
  buys 1% with 2 KB of tables is a different proposal from one that buys 1%
  free, and the fitness scalar cannot tell them apart.
- **Cross-platform and cross-build-flag checks** - other targets, other opt
  levels, debug vs release, with/without the flags the product actually ships
  (`overflow-checks`, LTO, `target-cpu`). A win that exists only at one flag
  combination is a fact about your build, not about the code.
- **Compile-time or const-evaluation cost**, where the API promises it.

The failure the menu prevents, observed in a real run: the harness carried a
timer and nothing else. Every decisive mechanism finding - a per-digit branch
nobody had counted, a table whose cost scaled with cache-line footprint rather
than instruction count, and the discovery that the loop was throughput-bound
rather than branch-bound - came from an agent improvising `objdump` or `size -A`
mid-candidate. The throughput-vs-latency question in particular consumed a full
candidate to settle empirically, and `llvm-mca` on the loop body would have
answered it in minutes, in Phase 2, before any candidate existed. Worse, none of
those numbers were recorded per candidate, so nothing could be correlated across
the population afterwards.

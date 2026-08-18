# The `evolve` skill

An AI agent plugin: five skills that turn "make this faster" into a result you
can defend - an experiment directory, a search that runs against it, and a final
report where every number is re-derivable from a stored artifact.

It is modelled on DeepMind's AlphaEvolve - an LLM proposes code changes, a
harness scores them, the good ones become parents - but most of what is here is
not the search. The hard part building a measurement you are not fooling
yourself with, and knowing the difference between a result and a number that
went up.

## Install

### Claude Code

```
/plugin marketplace add vsukhoml/evolve
/plugin install evolve@vsukhoml
```

To work from a local checkout instead, point the marketplace at the directory:
`/plugin marketplace add /path/to/evolve`.

Or copy `skills/*` into `~/.claude/skills/` to use them without the plugin
wrapper. The skills are self-contained; nothing outside this directory is
required.

### Google Antigravity

The repo root is itself a valid Antigravity plugin (root `plugin.json` marker
plus `skills/<name>/SKILL.md`, which is Antigravity's native skill format), so
installation is a straight copy into a scanned plugin location:

**Global (all workspaces):**

```bash
mkdir -p ~/.gemini/config/plugins/evolve
cp -r * ~/.gemini/config/plugins/evolve/
```

**Workspace-local:** the same copy into `.agents/plugins/evolve/` (or
`_agents/plugins/evolve/`) at the workspace root.

Or copy `skills/*` directly into `~/.gemini/config/skills/` or
`.agents/skills/`. The repo also ships `gemini-extension.json`, so
`gemini extensions install https://github.com/vsukhoml/evolve` works in the
Gemini CLI.

### Codex / ChatGPT

Add the repo as a plugin marketplace, then install from the Plugins Directory in
the ChatGPT desktop app (or `codex plugin add evolve@vsukhoml` where the CLI
supports direct installs):

```
codex plugin marketplace add vsukhoml/evolve
```

The repo carries both marketplace forms Codex reads - the native
`.agents/plugins/marketplace.json` and the legacy-compatible
`.claude-plugin/marketplace.json` - and `.codex-plugin/plugin.json` points at
the same `skills/` directory every other platform uses. On Codex variants
without plugin support, `AGENTS.md` at the repo root is picked up as project
context - see "Any other agent" below.

### Grok

```
grok plugin install vsukhoml/evolve --trust
```

then enable it in `~/.grok/config.toml`:

```toml
[plugins]
enabled = ["evolve"]
```

### Devin

```
devin plugins install vsukhoml/evolve
```

### Agent Plugins spec (any conformant client)

The repo is a conformant [Agent Plugins 1.0.0](https://agent-plugins.org)
package, so a client implementing that standard can install it with no
vendor-specific adapter: the root `plugin.json` declares the spec schema, and
`skills/<name>/SKILL.md` is already the layout the spec fixes for skill
discovery. There is no `mcp.json` - the plugin ships no MCP server, and the
skills invoke the harness directly as `python3 <file>`.

### Any other agent (instruction-only)

The skills are plain markdown and the harness is stdlib Python, so no plugin
machinery is actually required. Clone the repo (or vendor it into the project)
and point the agent at `AGENTS.md` in the repo root - it routes requests to the
right `skills/*/SKILL.md` and explains how to find the harness. For platforms
with an always-on rules file (Cursor, Windsurf, Cline, Copilot instructions,
Zed, Jules, Amp, ...), copy or reference `AGENTS.md` from there.

**Requirements:** Python 3 standard library only. No API keys, no external
services, nothing to install. The harness scripts (`evolve_db.py`,
`evolve_run.py`, `evolve_report.py`) and the parameter-search driver (`tune.py`)
are copied into each experiment directory, so an experiment stays runnable and
inspectable on its own after the plugin is gone.

**Safety:** this plugin executes model-written code repeatedly and unattended.
Pure local computation is fine in a normal process; anything reaching the
network, the filesystem outside the candidate directory, or spawning
subprocesses belongs in a container. Timeouts are always set, and the harness
always lives outside the regions a candidate may edit.

## The five skills

- **`evolve:evolve`** - advisory, read-only. Whether a problem is worth evolving
  at all, how to design a fitness function that cannot be gamed, how to read a
  run honestly, why a run stalled. Creates nothing.
- **`evolve:design`** - builds the experiment directory - spec, seed program
  with `EVOLVE-BLOCK` markers, evaluator, correctness gate, knowledge base,
  database. Ends at a seven-check gate.
- **`evolve:runner`** - drives generations of Strategist → Implementer →
  Evaluator → Reviewer with parallel subagents. Records every candidate, scores
  predictions against outcomes, stops on budget, plateau, or a real result.
- **`evolve:monitor`** - watches a running experiment, reports new bests and
  health warnings with the noise floor attached, writes the final report. Says
  nothing on a quiet poll.
- **`evolve:orchestrator`** - chains all three phases, detecting which one you
  are already in. **Start here** if you just want the thing optimized.

## Using it

The skills trigger on plain requests - "optimize this function", "design an
experiment to make X faster", "run the experiment", "how is the run doing" - or
explicitly by name (`evolve:orchestrator`, `evolve:design`, …). Three ways in,
by decreasing automation:

**Just optimize the thing.** Name the target and the measure, and let the
orchestrator drive:

> Optimize the parser in `src/decimal.rs` for throughput on short inputs.
> Results must stay bit-identical and the public API cannot change.

It detects where you are (bare goal → design; existing experiment directory →
run; running experiment → monitor) and chains the phases. Expect a conversation
before any code exists: whether this is the right problem at all and what the
cheaper alternatives are, the constraints and invariants, what a cheating
solution would look like, and the budget in candidates and hours. The questions
are the product working - every one of them is a failure mode being priced
before it is paid for.

**Ask before committing.** `evolve:evolve` is the read-only consultant: whether
the problem is worth a run at all, how to turn a goal into a score that cannot
be gamed, whether a finished result is real or noise, why a run stalled. It
creates no files and starts nothing, so it is the cheap first call when you are
not sure an experiment is warranted.

**Drive the phases yourself.**

1. "Design an experiment to …" (`evolve:design`) - interrogates the problem,
   writes the spec, builds the experiment directory, and proves the harness
   discriminates before any budget is spent: baseline scored twice, noise floor
   recorded, a deliberately broken candidate rejected, a known-good change
   detected. If the gate does not pass, nothing downstream is worth running.
2. "Run it" / "do 10 generations" (`evolve:runner`) - drives the Strategist →
   Implementer → Evaluator → Reviewer loop, records every candidate, and stops
   on budget, plateau, or a confirmed result, ending with the closing ritual
   (re-score in a fresh copy, held-out inputs, ablation, a report with the noise
   floor attached).
3. "Status?" / "write the final report" (`evolve:monitor`) - reads the
   experiment directory and reports what changed; refreshes `dashboard.md`.

**What to have ready:** the code, a command that proves correctness (your test
suite - if there is none, building one becomes the first step), and a rough
budget. Everything else is asked for. Your working tree is never touched: the
target is copied into the experiment's `program/`, and candidates evolve there.

**What you get back:** a self-contained experiment directory - spec, harness,
per-candidate history in `evolution.json` and `generations/`, a knowledge base
of what was tried and what it taught, `dashboard.md` - runnable and inspectable
with nothing but python3, months later, with the plugin gone. The winning diff
is never auto-merged; integrating it into your tree is a separate, explicitly
requested, reviewed step.

**Resuming:** point any skill at the experiment directory ("keep going",
"another 10 generations", "is this result real?"). State lives in the directory,
so a crashed or interrupted run continues from its records.

## Why it looks like this

The skills were written, then used on a real problem - a decimal string parser
in a financial library - then rewritten from what that run got wrong. Almost
none of the corrections were about the search. They were about the instrument:

- The first benchmark's inputs were all **longer than 99% of real inputs**, so
  it ranked the candidate techniques backwards. A whole generation of
  conclusions had to be thrown away.
- The metric had **no case for an entire input family**, so it could not see a
  35% regression there. A reviewer found it by hand, three generations later.
- **A fifth of the metric's weight sat on input sizes that never occur** in the
  product. That nearly decided which candidate got merged.
- The one probe guarding an observable behavior **ran a single configuration
  while its comment claimed three**.
- Run-to-run drift between sessions was **larger than the declared noise
  floor**, quietly making every cross-session comparison undecidable.
- The harness could **silently pair one program's snapshot with another
  program's score**.

Every one of those was a harness defect, and every one produced a confident,
well-measured, wrong answer. The candidate ideas were mostly fine.

So the design skill gates on seven checks rather than four - two of which exist
only to ask *is this measuring the right thing?* - and a run is expected to
carry instruments beyond a stopwatch: disassembly, static microarchitecture
analysis, allocation counts, code size. A timer tells you what changed and never
why.

## The parts worth stealing if you read nothing else

1. **Measure the noise floor across sessions, not twice in a row.** Between-run
   drift is usually the bigger number, and it is the one that decides whether
   your result exists.
2. **Compare a candidate only against a parent re-scored in the same session.**
   A score from hours ago is not a comparator.
3. **Choose the winner on one set of measurements and report its score from a
   disjoint one.** The maximum of N noisy scores is inflated by construction.
4. **Anything you would refuse to merge over is a metric**, and it must be
   measured from the first candidate. If it is only in your head, the search
   cannot see it and the leaderboard will rank against it.
5. **A guard belongs at weight 0.0** - reported, never scored. Weight given for
   guard reasons is how a metric ends up spending itself on cases that do not
   occur.
6. **When the search is over parameters rather than structures, take the model
   out of the loop entirely** and run one resumable process with flushed
   progress. An agent turn per parameter combination spends minutes of wall
   clock on seconds of measurement.
7. **A test that has never been shown to fail is not evidence.** Mutate the
   thing it guards and watch it catch the mutant - and check your mutation was
   not a no-op, a mistake that has been made more than once here.

## Background and references

Everything below explains *where a rule came from* - the papers, the systems
this was modelled on, the published numbers behind a threshold. The skills
themselves carry only rules, so that a skill being read mid-run is not competing
with a literature review.

______________________________________________________________________

## The lineage

### [AlphaEvolve](https://arxiv.org/abs/2506.13131) (Google DeepMind, 2025) - arXiv:2506.13131

The method this plugin is modelled on: an ensemble of LLMs proposes edits to a
codebase, automated evaluators verify and score each candidate, and an
evolutionary algorithm decides which programs seed future prompts. The
mechanisms the skills borrow, all from §2 of the paper: the **evaluation
cascade** (test cases of increasing difficulty, small-scale first to kill faulty
programs cheaply); **multiple scores** (optimizing several metrics often
improves the one you care about, because structurally different programs feed
varied examples back into the prompts); **LLM-generated feedback** for
properties that resist a formula, such as simplicity; the **choice of
abstraction** (evolve the solution, a constructor that builds it, or a search
algorithm that finds it - constructors work better for highly symmetric
problems, custom search algorithms for non-symmetric ones); a **model ensemble**
pairing a fast model for throughput of ideas with a stronger one for occasional
leaps; a **database** combining MAP-Elites with island models; **stochastic
prompt formatting** and meta-prompt evolution as diversity mechanisms; and the
note that seeds may be **rudimentary** - a single-line function returning a
constant is fine, as long as the program is complete.

### [OpenEvolve](https://github.com/algorithmicsuperintelligence/openevolve) - `github.com/algorithmicsuperintelligence/openevolve`

The most complete public reimplementation of AlphaEvolve's architecture, read
here for design ideas only. Its architecture is broadly AlphaEvolve's:
MAP-Elites over customizable feature dimensions, islands with ring-topology
migration at a configurable interval, an LLM ensemble with weighted model
combinations, a prompt sampler that builds context from past programs and
scores, evaluation cascades with early filtering, and checkpoint/resume. Config
knobs of note: `population_size`, `num_islands`, `migration_interval`,
`feature_dimensions`, `exploitation_ratio`, `num_top_programs` vs
`num_diverse_programs`, `similarity_threshold`, `template_variations`, and
`random_seed` (default 42, for reproducibility). Reported results include a 2.8×
attention-kernel speedup on an M1 Pro, a state-of-the-art n=26 circle packing,
and +23% on HotpotQA prompt optimization.

Four of its mechanisms became rules in the skills:

1. **Feature dimensions as first-class, with `complexity` as one of them** - the
   archive is binned on axes like complexity, performance and memory, so a
   simpler-but-slower program survives as the elite of its own cell instead of
   losing a scalar comparison. This is the ancestor of the design skill's rule
   that *anything you would refuse to merge over is a metric*, and of "if you
   carry only one extra axis, carry the one you would refuse to merge over" in
   `skills/evolve/references/failure_modes.md`.
2. **Double selection** - draw the *parent* and the *inspiration* programs from
   different pools (top performers vs structurally diverse). This is why
   `evolve:runner` gives each strategist elites from other lineages.
3. **The artifact side-channel** - feed stderr, build warnings and profiling
   output back into the next prompt as first-class context, not just the score.
   This is the runner's "parent's evaluation insights" input and its repair
   slot.
4. **`random_seed` everywhere** - this is the "record the seed with the score"
   rule in `skills/evolve/references/fitness_design.md`.

### [Prime Intellect - autonomous nanoGPT speedrunning](https://www.primeintellect.ai/auto-nanogpt) - `github.com/PrimeIntellect-ai/experiments-autonomous-speedrunning`

The largest public instance of the kind of run this plugin governs: two frontier
agents (Claude Code and Codex) independently optimizing the modded-nanogpt
track-3 benchmark across four waves - roughly 10,400 recorded runs, ~14,000
H200-hours, 23.9B tokens - finishing at 2,930 steps against a human-community
baseline of 2,990 (from a 3,500-step start). Empirical grounding for several
rules here, from a run big enough to price them:

- **The novelty wall.** The wave that *required* genuinely novel ideas produced
  no improvements at all, while transfer-and-recombine waves beat the human
  baseline - direct evidence for budgeting seed strategies toward transfers and
  hybrids rather than invention from nothing, and for the consultant's honest
  ceiling (industrial compute bought ~2% over the human frontier).
- **Seed hacking is real enough to need a gate**: results had to clear a
  statistical noise floor, and ~5% of all runs went to leave-one-out pruning of
  stacked components - the closing ritual's ablation, at scale.
- **The horizon confound** behind `ml_tuning.md`'s threshold-metric rule: the
  record crossed the target at 2,920 steps while scheduled for 3,050, its
  hyperparameters tuned to a range the metric never measured.
- **Stale sources**: the technique behind the eventual record sat in an upstream
  PR for days and entered the search only when a forced restart re-fetched
  sources - the runner's synthesis-cadence source refresh.
- **Adjacency left on the table**: sibling variants of one optimizer idea tested
  74 hours apart - the runner's "spend the next generation on a winner's family"
  rule.
- **Objective shape not internalized**: the goal was frontier-shaped, both
  agents read it as threshold-shaped, and a mid-run human restatement was needed
  - the framing reference's threshold-or-frontier question.

### [ECO - An LLM-Driven Efficient Code Optimizer for Warehouse Scale Computers](https://arxiv.org/abs/2503.15669) (Google, 2025) - arXiv:2503.15669

The breadth-first complement to this plugin's depth-first search: instead of
searching for novel optimizations on one hot target, ECO mines decades of
historical performance commits into a dictionary of anti-patterns (unnecessary
copies, redundant map lookups, missing reserves, missing moves, needless
sorts/allocations), finds new instances across billions of lines via embedding
retrieval over a fleet-profiler-filtered search space, and applies the
catalogued fix with a fine-tuned LLM - >6.4k submitted commits, >99.5%
production success rate, savings equivalent to 500k+ normalized cores per
quarter, \<0.5% reverted under post-submit profiler monitoring. What the skills
borrow:

- **The anti-pattern scan of the seed** (design's prior-art section): most fleet
  savings came from *known* fixes, so a depth-first run folds the catalogued
  ones into its baseline before spending candidates on novelty.
- **Conservative-edit selection** (the implementer brief): across their
  benchmarks the most conservative valid edit met or beat the median speedup of
  five samples in nearly all cases, while chain-of-thought prompting produced
  the largest diffs and the most invalid ones - hence "the smallest edit that
  implements the strategy".
- **Cycle re-attribution** (`lowlevel_perf.md` § flat profiles): the profiler
  blames shared leaves (`push_back`, allocator); ECO re-attributes cost to the
  nearest application-specific caller (their C_min 0.1% / C_max 25% pruning),
  which is where the fixable anti-pattern actually lives.
- Their verification ladder - build + tests, automated trivial fixes, LLM
  self-review before human review, post-submit monitoring with cheap revert - is
  the reviewer-plus-closing-ritual shape, deployed; corroborates the
  ship-confirmed-wins-early rule rather than adding a new one.

### Sakana AI - The AI Scientist

- **[v1](https://arxiv.org/abs/2408.06292)** (arXiv:2408.06292): idea generation
  → novelty check against the literature (Semantic Scholar) → run experiment
  from a human-authored template → plot → LaTeX write-up → automated review, at
  **under $15 per paper**. Its automated reviewer reaches roughly **69% balanced
  accuracy** against human reviewers, with an F1 above NeurIPS-2021 inter-human
  agreement. That figure is the source of the skills' repeated rule that *an LLM
  judge is a fallible instrument, not ground truth* - 69% is genuinely useful
  and also means about a third of verdicts are wrong.
- **[v2](https://arxiv.org/abs/2504.08066)** (arXiv:2504.08066): drops the
  human-authored templates, adds a **progressive agentic tree search** run by an
  experiment-manager agent, and a VLM feedback loop that critiques its own
  figures. Three manuscripts went to an ICLR 2025 workshop; one cleared the
  human acceptance bar (6.33, above 55% of human papers) - the first fully
  AI-generated paper to pass peer review. Its **staged search** (investigate →
  tune → execute → ablate) is the runner's "early generations are
  reconnaissance", and its three worker actions - draft a new root, **debug a
  failed leaf**, improve the best unprocessed node - are why the runner spends
  one slot per generation repairing a promising mechanical failure.
- The **[Nature](https://sakana.ai/ai-scientist/)** paper (March 2026)
  consolidates both and reports that paper quality scales with the underlying
  foundation model.
- Their stated limits are the useful part, and they shaped the consultant
  skill's "expect to be the reviewer yourself": naive or underdeveloped ideas,
  weak methodological rigor on hard implementations, hallucinated citations,
  duplicated figures, computational experiments only.
- Their repository's warning that it "will execute LLM-written code", with risks
  including "potentially dangerous packages, web access, and potential spawning
  of processes", is the source of the containerization advice in
  `evaluator_contract.md`, `failure_modes.md` and the runner's Safety section.

## No external backends

The systems above are read for design ideas; none of them is a dependency. This
plugin has **no external API dependency, no hosted service, and no API keys**
beyond the LLM Agent session itself. The harness scripts (`evolve_db.py`,
`evolve_run.py`, `evolve_report.py`, `tune.py`) are **Python 3 standard library
only**, and they are copied into each experiment directory, so an experiment
stays runnable and inspectable after the plugin is gone.

That is a deliberate constraint rather than an omission. An experiment is a
record you may need to re-derive a number from months later; anything that
depends on a service being up, an account being live, or a key still being valid
is a record with an expiry date on it.

______________________________________________________________________

## References

- **[AlphaEvolve](https://arxiv.org/abs/2506.13131)**, DeepMind 2025 -
  arXiv:2506.13131, The whole loop shape: evaluation cascade, multiple metrics,
  choice of abstraction, model ensemble, rudimentary seeds, prompt
  diversification. Its 75%-match / ~20%-improve base rate is the calibration in
  `pre_mortem.md`
- **[The AI Scientist v1](https://arxiv.org/abs/2408.06292)**, Sakana -
  arXiv:2408.06292, The novelty gate before the compute spend; the ~69% reviewer
  figure behind "an LLM judge is a fallible instrument"; the `seed_ideas`
  pattern behind `seed_strategies.md`
- **[The AI Scientist v2](https://arxiv.org/abs/2504.08066)**, Sakana -
  arXiv:2504.08066, Staged search (investigate/tune/execute/ablate) = the
  runner's reconnaissance phase; the debug-a-failed-leaf worker action = the
  repair slot
- **[The AI Scientist](https://sakana.ai/ai-scientist/)**, *Nature*, March 2026,
  Scaling claim: output quality tracks the underlying foundation model
- **[OpenEvolve](https://github.com/algorithmicsuperintelligence/openevolve)**
  (`algorithmicsuperintelligence/openevolve`), Feature dimensions incl.
  complexity, double selection, the artifact side-channel, `random_seed`
  reproducibility. Design ideas only - not a backend
- **[DarwinX](https://arxiv.org/abs/2608.07545)**, Salesforce AI Research 2026 -
  arXiv:2608.07545, The preserve-and-extend contract behind
  `preserve_and_extend` (per-case gain `g` and bounded regression `R`, with the
  child kept in the archive but barred from parenthood); the two-speed
  enter-cheap / steer-only-after-confirmation rule behind
  `promotion.confirm_before_steering` and its preservation probe; dominant
  failure-theme injection so the proposer invents a capability instead of
  patching a task. Its subject - a frozen model with an evolving prompt / tool /
  control-flow harness - is the archetype in `agent_harness.md`. The archive
  merge operator (accept a merged child iff it covers the union of both parents'
  solves) is **not** implemented here: it needs per-case vectors first, and the
  paper itself reports recombination's contribution over single-lineage mutation
  as still awaiting a controlled ablation
- Bjarnason et al., via arXiv:2608.07545 §10, The 2.2-6.0-point pass@1 swing on
  repeated runs of one agent on one public benchmark - the calibration in
  `agent_harness.md` for why a single rollout per task is a coin flip
- **[Intern-S2-Preview](https://arxiv.org/abs/2608.13505)**, Shanghai AI
  Laboratory 2026 - arXiv:2608.13505, §4.4.2–4.4.3 only; the rest is model
  training and does not apply to a frozen-model loop. Infrastructure failures
  and unparseable verifier output tracked separately from genuine task failure =
  the `infra_failed` status and its exclusion from the failure rate. Step-level
  curation that keeps erroneous steps in context but masks them from the
  imitation loss = negative results shown to a strategist as evidence rather
  than as a parent to extend. Its behavior-type annotation list is the shape of
  the default failure-mode vocabulary in `coverage_and_confirmation.md`

### Choosing among noisy candidates (→ `fitness_design.md`)

- Audibert, Bubeck & Munos,
  [*Bandit View on Noisy Optimization*](https://hal.science/hal-00520611), ch.
  16 of
  **[Optimization for Machine Learning](https://mitpress.mit.edu/9780262016513/optimization-for-machine-learning/)**,
  MIT Press 2011, The framing that decides everything: you want *simple* regret
  / best-arm identification, not cumulative regret - which is why UCB and
  Thompson sampling are the wrong tool. Successive Rejects (Fig. 16.1) and the
  Hoeffding race with its mandatory cap (Fig. 16.3) are lifted from here
- Karnin, Koren & Somekh,
  [*Almost Optimal Exploration in Multi-Armed Bandits*](https://proceedings.mlr.press/v28/karnin13.html),
  ICML 2013, Successive halving
- Jamieson & Talwalkar,
  [*Non-stochastic Best Arm Identification and Hyperparameter Optimization*](https://proceedings.mlr.press/v51/jamieson16.html),
  AISTATS 2016, The benchmark showing successive halving beats UCB and EXP3 on
  this shape of problem
- Li, Jamieson, DeSalvo, Rostamizadeh & Talwalkar,
  [**Hyperband**](https://arxiv.org/abs/1603.06560), JMLR 18(185) 2018 -
  arXiv:1603.06560, The screen-validation rule: multi-fidelity methods are
  "particularly bad" when low-fidelity performance does not predict
  high-fidelity performance. Also §4.4.2's admission that the most aggressive
  plain successive-halving bracket beat Hyperband in almost every experiment -
  the reason the skills default to plain two-stage screening
- Feurer & Hutter, ch. 1 of
  [**AutoML: Methods, Systems, Challenges**](https://link.springer.com/book/10.1007/978-3-030-05318-5),
  The budget-vs-number-of-configurations trade-off, both directions
- [**irace-evo**](https://arxiv.org/abs/2511.14794) - arXiv:2511.14794, Direct
  precedent: iterated racing (Friedman rank test, α = 0.05) wrapped around LLM
  code evolution

### Selection bias and multiple comparisons (→ `fitness_design.md` § *Selection bias*)

- Sayed,
  [**Inference and Learning from Data**](https://doi.org/10.1017/9781009218269),
  Vol. II, Cambridge 2022, Problems 31.31–31.32, The split-sample estimator
  behind winner confirmation: choose on set (a), report set (b); provably never
  overestimates. The formal warrant for `evolve_run.py --dry-run` confirmation
- van Hasselt,
  [*Double Q-learning*](https://proceedings.neurips.cc/paper/2010/hash/091d584fced301b442654dd8c23b3fc9-Abstract.html),
  NIPS 2010, The same construction, from RL - cited as the recognizable name for
  it
- Bailey & López de Prado,
  [*The Deflated Sharpe Ratio*](https://doi.org/10.3905/jpm.2014.40.5.094),
  Journal of Portfolio Management 2014, The E[max] inflation formula reproduced
  in `fitness_design.md`, its independence assumption (hence: count N in
  distinct **lineages**), and "apply a holdout 20 times and false positives are
  expected" - why confirmation runs once, on the winner
- Harvey, Liu & Zhu,
  [*…and the Cross-Section of Expected Returns*](https://doi.org/10.1093/rfs/hhv059),
  RFS 2016, Multiple-testing hurdle: t > 2.0 must rise to t > 3.0 across a large
  hypothesis zoo; the correction depends on trials *attempted*, which an
  evolutionary run actually knows
- Benjamini & Hochberg,
  [*Controlling the False Discovery Rate*](https://doi.org/10.1111/j.2517-6161.1995.tb02031.x),
  JRSS-B 1995, FDR rather than FWER when reporting a *set* of survivors
- Anderson,
  [*Multiple Inference and Gender Differences…*](https://doi.org/10.1198/016214508000000841),
  JASA 2008, The pattern of reducing the number of tests with a summary index
  *and* adjusting p-values
- Sutton & Barto,
  [**Reinforcement Learning**](http://incompleteideas.net/book/the-book-2nd.html),
  §2.5, §2.7, UCB's stationarity and fixed-arm-set assumptions - both violated
  by a candidate pool regenerated each generation

### Measurement (→ `perf_harnesses.md`, `pre_mortem.md`)

- Mytkowicz, Diwan, Hauswirth & Sweeney,
  [*Producing Wrong Data Without Doing Anything Obviously Wrong!*](https://doi.org/10.1145/1508244.1508275),
  ASPLOS 2009, The measurement-bias section entire. UNIX environment size and
  link order shift performance enough to **flip the sign** of `-O3` vs `-O2`,
  reproduced across Pentium 4, Core 2 and a simulator with both gcc and icc.
  Remedies: setup randomization (they used 484 = 22 link orders × 22 environment
  sizes, comparing *distributions*) and causal analysis. Their caveats are
  load-bearing too: inadequate randomization just buys a different bias, and **a
  larger benchmark suite does not help - only a more diverse one does.** Their
  survey of 133 ASPLOS/PACT/PLDI/CGO papers found none adequately considered it
- Georges, Buytaert & Eeckhout,
  [*Statistically Rigorous Java Performance Evaluation*](https://doi.org/10.1145/1297027.1297033),
  OOPSLA 2007, Multiple invocations, steady-state detection, confidence
  intervals instead of a single mean. Not Java-specific
- Chen & Revels,
  [*Robust Benchmarking in Noisy Environments*](https://arxiv.org/abs/1608.04295),
  arXiv:1608.04295, Estimator choice under noise
- Tene,
  [*How NOT to Measure Latency*](https://www.infoq.com/presentations/latency-response-time/),
  Coordinated omission - mandatory reading before any score that is a latency
  percentile
- Pugh, Soros & Stanley,
  [*Quality Diversity: A New Frontier for Evolutionary Computation*](https://doi.org/10.3389/frobt.2016.00040),
  Frontiers in Robotics and AI 2016, The organizing survey, and the warning that
  governs adoption: an *unaligned* behaviour characterization "negatively
  impact[s] the performance of QD algorithms, which on sufficiently hard
  problems may translate into an outright failure to find the best-performing
  solutions". Hence the rule: no behaviour descriptor unless it is plausibly
  quality-aligned
- Mouret & Clune,
  [*Illuminating Search Spaces by Mapping Elites*](https://arxiv.org/abs/1504.04909),
  arXiv:1504.04909; Cully et al.,
  [*Robots that can adapt like animals*](https://arxiv.org/abs/1407.3501),
  Nature 2015, MAP-Elites - one elite per behaviour cell; the applied companion
- Lehman & Stanley,
  [*Abandoning Objectives: Evolution through the Search for Novelty Alone*](https://doi.org/10.1162/EVCO_a_00025),
  Evolutionary Computation 2011, Novelty search's stated limits (§9): no
  optimization pressure once a solution is found - generate with it, then
  optimize on the objective. Also the negative result that NEAT's fitness
  sharing is "still fundamentally deceived when seeking higher fitness" -
  genotypic diversity is not a substitute for a non-objective gradient

### Low-level optimization moves (→ `lowlevel_perf.md`)

- Dean & Ghemawat, [*Performance Hints*](https://abseil.io/fast/hints.html),
  abseil.io - the source `lowlevel_perf.md` distills: back-of-the-envelope
  estimation with the latency-numbers list, the hierarchy from algorithmic class
  down to compiler mechanics, the memory-representation and allocation-reduction
  menus, fast paths / precompute / hoist / defer / specialize, and the
  flat-profile playbook. The published numbers quoted in the reference (21% from
  a shared zero instance, 26–31% from a bit vector over a hash set, 43 s → 2 s
  from deferring one call, 4× from specialized formatting) are theirs
- The wider [*Performance Tips of the Week*](https://abseil.io/fast/) series the
  hints page belongs to - a source of further seed strategies when the target is
  C++-shaped

### ML meta-parameter tuning (→ `ml_tuning.md`)

- Godbole, Dahl, Gilmer, Shallue & Nado,
  [*Deep Learning Tuning Playbook*](https://github.com/google-research/tuning_playbook),
  2023 - the scientific / nuisance / fixed hyperparameter framing behind the
  nuisance-confound rule (tune the nuisance knobs, learning rate above all, for
  *each* arm of a structural comparison); learning-rate-first ordering;
  schedules anchored to the total budget rather than truncated
- Bergstra & Bengio,
  [*Random Search for Hyper-Parameter Optimization*](https://jmlr.org/papers/v13/bergstra12a.html),
  JMLR 2012 - low effective dimensionality of hyperparameter spaces, and why
  random search beats grid there: the override of the generic enumerate-the-grid
  advice
- Li, Jamieson, DeSalvo, Rostamizadeh & Talwalkar,
  [*Hyperband*](https://jmlr.org/papers/v18/16-558.html), JMLR 2018; Li et al.,
  [*ASHA*](https://arxiv.org/abs/1810.05934), MLSys 2020 - multi-fidelity budget
  allocation: start many configurations cheap, promote survivors
- Snoek, Larochelle & Adams,
  [*Practical Bayesian Optimization of Machine Learning Algorithms*](https://arxiv.org/abs/1206.2944),
  NeurIPS 2012 - the GP-BO baseline, for when random stops being competitive
- Bouthillier et al.,
  [*Accounting for Variance in Machine Learning Benchmarks*](https://arxiv.org/abs/2103.03098),
  MLSys 2021 - seed, data-order and init variance in ML benchmarks, and the case
  for randomizing more sources rather than fewer when comparing
- Henderson et al.,
  [*Deep Reinforcement Learning that Matters*](https://arxiv.org/abs/1709.06560),
  AAAI 2018 - seed variance large enough to reverse comparisons between
  identical algorithms; the deep-RL half of "the noise floor is seed variance"
- Picard,
  [*torch.manual_seed(3407) is all you need*](https://arxiv.org/abs/2109.08203),
  arXiv:2109.08203 - the percent-scale seed-alone spread on standard vision
  benchmarks quoted in the reference
- Recht, Roelofs, Schmidt & Shankar,
  [*Do ImageNet Classifiers Generalize to ImageNet?*](https://arxiv.org/abs/1902.10811),
  ICML 2019 - new test sets drop absolute accuracy by 3–15 points while largely
  preserving ranking: community-scale adaptive overfitting weaker than feared,
  which does not repeal the within-run max-of-N inflation

### Trading-strategy backtests (→ `quant_trading.md`)

- Deliberately light on citations: the reference is first-principles and
  practitioner-empirical by design - every rule argues from a mechanism (how a
  backtest fools you) or from observed behavior (edges decay, skew games
  Sharpe), not from a named theory. Its statistical backbone - max-of-N
  inflation, counting trials attempted, split-sample confirmation - is the
  *Selection bias* section above (Bailey & López de Prado; Harvey, Liu & Zhu),
  machinery that came from this domain in the first place

### Problem framing (→ `evolve:design` Phase 0, `problem_framing.md`)

- Gause & Weinberg, *Are Your Lights On?*, Dorset House 1990 - the
  problem-behind-the-problem discipline: a problem is a difference between
  things as desired and things as perceived, most requests arrive as chosen
  solutions, and "whose problem is it?" changes what counts as solved
- Pólya, *How to Solve It*, Princeton 1945 - understand the problem before
  solving it: restate it in your own words, and "have you seen a problem in
  related form?" - the question behind naming the domain to unlock its prior art
- The premise ledger's measured / reported / inferred / assumed labels are the
  knowledge base's own evidence discipline (measured / inferred / argued),
  applied before the run instead of during it - beliefs classified by how they
  are held, each with a falsifier, so that low-confidence, high-stakes premises
  become the reconnaissance agenda instead of silent assumptions

### Experimental method (→ `evolve:runner` reconnaissance, `pre_mortem.md`)

- Platt, [*Strong Inference*](https://doi.org/10.1126/science.146.3642.347),
  Science 1964, Design each probe as a crucial experiment whose outcome is
  incompatible with at least one rival hypothesis
- Chamberlin,
  [*The Method of Multiple Working Hypotheses*](https://doi.org/10.1126/science.148.3671.754),
  Science 1890 (repr. 1965), The "ruling theory" failure - one working
  hypothesis the whole run then polishes, which is population collapse at the
  epistemic level
- Kerr,
  [*HARKing: Hypothesizing After the Results are Known*](https://doi.org/10.1207/s15327957pspr0203_4),
  PSPR 1998, Why evidence gathered while exploring must be re-earned in a
  confirming generation
- Morris,
  [*Factorial Sampling Plans for Preliminary Computational Experiments*](https://doi.org/10.1080/00401706.1991.10484804),
  Technometrics 1991, Elementary-effects screening - rank which knobs matter
  before spending budget tuning ones that do not (named in the design skill's
  tuning-method list, `references/parameter_search.md`)
- Deb, Pratap, Agarwal & Meyarivan,
  [**NSGA-II**](https://doi.org/10.1109/4235.996017), IEEE Trans. Evolutionary
  Computation 2002, The Pareto method named in the tuning table for genuinely
  competing objectives - return the front, not one point
- Altshuller, [**TRIZ**](https://www.altshuller.ru/e/),
  `inventive_principles.md` is a TRIZ-derived checklist. What transfers: the
  Ideal Final Result, the four separations, a curated dozen of the 40
  principles, resources thinking. What does not, and is deliberately excluded:
  the 39×39 contradiction matrix, ARIZ, Su-Field analysis - all distilled from
  mechanical-era patents

### Verification is a weak instrument (→ `evolve:runner` § *Reviewer*)

These are the numbers behind the reviewer rules. The rules are in the skill; the
evidence is here.

- **[SPOT - When AI Co-Scientists Fail](https://arxiv.org/abs/2505.11855)**, Son
  et al. 2025, 83 published papers, 91 errors significant enough to prompt
  errata or retraction, every one confirmed by the original authors. Best
  frontier model: **21.1% recall at 6.1% precision**; most near zero.
  **Confidence estimates uniformly low and uninformative.** Across **eight
  independent runs, models rarely recover the same errors** - between-run
  variance swamps between-model differences. Failures resemble student-level
  misconceptions, worst on long-tail knowledge and very long contexts. Hence:
  run the reviewer multiple times and union the findings when the verdict
  matters; ignore its stated confidence; treat "found nothing" as "one
  low-recall pass found nothing"; and calibrate with planted errors, which is
  SPOT's own construction scaled down to three or four defect classes
- **[AIGS - Generating Science from AI-Powered Automated Falsification](https://arxiv.org/abs/2411.11910)**,
  Liu et al. 2024, Argues falsification *is* the research process rather than a
  downstream check, and makes a `FalsificationAgent` an explicit role. Results
  are modest with no clean quantitative win over generation-only search, so it
  is taken as an architectural argument, not evidence: the plugin's equivalent
  is the strategy format's "how we would know it did not work", and the lever is
  the *specificity* of that clause, not adding a role
- **[Agentic AI for Scientific Discovery: a survey](https://arxiv.org/abs/2503.08979)**,
  2025, **Literature review is the dominant failure point** across frameworks,
  above experimentation and writing, and it is what undermines grounding. That
  is the design skill's "verify what you cite; do not recall it". Also
  recommends calibration (confidence matching actual correctness) and
  human-in-the-loop over full autonomy
- **[Can LLMs be Used to Simplify Algorithms?](https://arxiv.org/abs/2608.10753)**,
  El-Hayek, Henzinger & Zheng 2026 - arXiv:2608.10753, The counterweight to the
  bullet above. Ten theory papers put to three models under two prompts, one of
  which forbade searching for a solution to the exact problem while still
  allowing lookups for standard background. With search allowed, one model
  returned the known simpler algorithm on all six problems where one existed,
  and on very few without it - but on one problem it returned that known
  algorithm *instead of* the novel improvement the same model produced under the
  strict prompt. Hence the design skill's "the one place this search costs you
  is novelty" and the runner's search-blind lane: prior art raises the floor and
  lowers the ceiling. One run per cell and 20 evaluations per model, disclaimed
  by its own authors as case studies rather than measured effect. The prompt's
  closing prohibition - no partial reductions, do not return because current
  approaches fail, do not reduce to an equally difficult problem - is the
  strategist brief's "return a strategy"; that models still gave up on 2 of 20
  problems each is why the clause is not trusted to be sufficient

### Read but not yet drawn on

Downloaded for when the relevant question comes up; no rule currently depends on
them.

- **[MLAgentBench](https://arxiv.org/abs/2310.03302)** - arXiv:2310.03302,
  Benchmarking agents on ML experimentation tasks
- **[NovelSeek / InternAgent](https://arxiv.org/abs/2505.16938)** -
  arXiv:2505.16938, Closed-loop hypothesis → verification
- **[SciReplicate-Bench](https://arxiv.org/abs/2504.00255)** - arXiv:2504.00255,
  Reproducing algorithms from paper descriptions
- **[FML-bench](https://arxiv.org/abs/2605.17373)** - arXiv:2605.17373,
  Controlled study of AI research-agent strategies from a search-dynamics view -
  the closest external work to this plugin's slot-mix question
- **[Sakana Fugu](https://arxiv.org/abs/2606.21228)** technical report -
  arXiv:2606.21228, Orchestrator models that devise agentic scaffolds; relevant
  to the strategist/model-mix question
- **[REFUTE](https://huggingface.co/datasets/BGPT-OFFICIAL/refute)**
  (HuggingFace `BGPT-OFFICIAL/refute`), Dataset covering falsification,
  overclaims, missing-evidence refusal and planted-flaw detection - a source of
  defect classes if three or four are not enough for reviewer calibration
- **[TCS-BENCH](https://arxiv.org/abs/2608.09538)**, Cohen-Addad et al. 2026,
  arXiv:2608.09538 - research-level proof generation with a calibrated automated
  verifier (>90% agreement with experts, from 50 correct + 50 incorrect
  human-labeled proofs - the planted-error construction at benchmark scale). The
  numbers behind two reviewer rules: **verdict asymmetry** - self-acceptance
  carried almost no information (93.4% of self-accepted proofs drew unanimous
  re-acceptance) while routing on self-rejection alone lifted accuracy 54.0% →
  63.7%; and **cross-model critique** - a second model's judgement discriminated
  at 0.854 AUC exactly where self-verification failed, lifting accuracy to 67.7%
  (oracle 72.3%), with the judging *direction* mattering far more than the
  acceptance threshold (the cheap model judging the strong one worked; the
  reverse, 0.637 AUC, did not). Hence: act on rejects, discount accepts, make
  one reviewer pass cross-model, and calibrate the direction instead of assuming
  the stronger model judges better

### Tools named in the skills

Not references, but named because a rule tells you to reach for them: Google
Benchmark (`DoNotOptimize`, `ClobberMemory`), criterion, `cargo asm`, Miri,
`go test -bench` with **benchstat**, `pytest-benchmark`, `py-spy`, `perf stat` /
`perf record`, `objdump`, `size -A`, **llvm-mca** and **uiCA** for static
microarchitecture analysis, and ASan/UBSan/TSan for the C and C++ correctness
gate.

______________________________________________________________________

## License

Apache License 2.0 - see [LICENSE](LICENSE) and [NOTICE](NOTICE).

Apache-2.0 rather than MIT for one reason that matters here: it carries an
express patent grant. The value of this plugin is methodology, and methodology
is not protectable by a licence in any case - anyone who reads this README can
apply the ideas whatever the LICENSE says. So the licence's job is to remove
ambiguity for people who want to use, adapt and redistribute the code, and to
say plainly that using it does not walk them into a patent problem.

# evolve - agent operating instructions

You are reading the universal adapter for the `evolve` plugin: five skills that
turn "make this faster" into a result you can defend - an experiment directory,
a search that runs against it, and a final report where every number is
re-derivable from a stored artifact. On platforms with native plugin support
(Claude Code, Codex, Gemini/Antigravity, Grok, Devin) - and on any client that
implements the Agent Plugins 1.0.0 spec, which this repo conforms to - the
skills load through the platform's own mechanism; on everything else, this file
is the entry point and the skills work as plain instructions.

## How to operate

Each skill is a markdown file of operating instructions. When a request matches
a skill, open its `SKILL.md` and follow it exactly - the skills carry the rules,
this file only routes:

- The user asks whether an evolutionary run is worth it, how to score
  candidates, whether a result is real, or why a run stalled →
  `skills/evolve/SKILL.md` (advisory, read-only; creates nothing).
- The user wants an experiment designed, or hands over code plus a target metric
  → `skills/design/SKILL.md`.
- The user says "run the experiment", "keep going", "do N generations" →
  `skills/runner/SKILL.md`.
- The user asks how the run is doing, or wants the final report →
  `skills/monitor/SKILL.md`.
- The user just wants the thing optimized end to end →
  `skills/orchestrator/SKILL.md`, which chains the other three and detects where
  you already are.

Skills reference deeper material in their `references/` directories - load those
on demand, exactly as the skill instructs. Do not summarize a skill from memory;
read the file.

## The harness

The runnable part is a stdlib-only Python harness in `skills/design/assets/ae/`
(`evolve_db.py`, `evolve_run.py`, `evolve_report.py`) plus templates in
`skills/design/assets/templates/`. It is *copied into* each experiment directory
as `.ae/` and always invoked as `python3 <file>` - no packages, no network,
nothing to install beyond python3.

To locate the harness from an installed copy of this plugin, search the plugin
roots your platform uses; the skills use:

```bash
AE=$(find ~/.claude/plugins ~/.gemini/config/plugins ~/.codex/plugins \
       ~/.grok/plugins .agents/plugins -path '*evolve*/skills/design/assets/ae' \
       -type d 2>/dev/null | head -1)
```

If that finds nothing, locate your platform's checkout of this repository and
set `AE` to its `skills/design/assets/ae` directory.

## Non-negotiables, whatever the platform

- Candidate code is executed by the harness only (`evolve_run.py`), never by
  hand - the gate, the timeout, the snapshot and the lock come with it.
- The gate, evaluator, benchmark data, and tests live outside every
  `EVOLVE-BLOCK` region; a candidate must never be able to edit the thing that
  judges it.
- Timed measurement is serialized machine-wide by the harness's lock. Never run
  two timed experiments on one machine expecting parallel throughput.
- The user's working tree is never touched; targets are copied into the
  experiment's `program/`, and integrating a winner back is a separate,
  explicitly requested step.
- Every reported gain carries its noise floor, or it is not a claim.

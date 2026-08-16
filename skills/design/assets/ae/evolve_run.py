#!/usr/bin/env python3
"""Evaluate one candidate program and record it in the evolution database.

This is the only place candidate code is ever executed. Routing every
evaluation through one script is what makes the run trustworthy: the
correctness gate cannot be skipped, timeouts cannot be forgotten, a NaN
cannot reach the database, and every candidate is measured the same way as
every other one. An agent that runs a candidate by hand has silently opted
out of all of that.

Order of operations, and why:

  1. correctness gate --- the project's own tests, run against the candidate.
     A wrong answer computed faster is not an improvement, so correctness is
     checked before the score is even read. A failed gate is recorded, not
     discarded: knowing *how* candidates break is most of the signal.
  2. evaluator --- the user's harness, invoked as
        <command...> --program-dir DIR --output-file OUT
     writing JSON: {"score": float|null, "metrics": {...}, "insights": [...]}
     When experiment.json declares `objectives` (multi-objective mode), the
     evaluator additionally writes {"objectives": {axis: float, ...}} with
     every declared axis present and finite; `score` stays the first axis.
     An evaluator over a *suite* may also write {"cases": {name: float}} ---
     the per-case vector a scalar aggregate hides, and the only thing that
     can tell "8% faster everywhere" from "12% faster on four inputs and
     3x slower on the fifth". See evolve_db.py, preserve-and-extend.
  3. repeats --- for noisy measurements (anything timing-based), the
     evaluator runs `repeats` times and the median is recorded along with
     the spread. A single timing sample cannot distinguish a real 3% win
     from machine noise, and a hill-climber fed noise will happily climb it.

A failure that was the MACHINE's fault, not the candidate's, is recorded
with status "infra_failed" and kept out of the failure rate --- see
InfrastructureFailure. The evaluator declares it with {"failure":
"infrastructure"}; the harness never guesses.

Usage:
  evolve_run.py --experiment DIR --candidate-dir DIR --id ID [--parent ID]
            [--policy greedy|novel] [--strategy-file F] [--repeats N]
            [--skip-gate] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

try:
    import fcntl
except ImportError:  # non-POSIX platform: no lock, measurements may interleave
    fcntl = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evolve_db  # noqa: E402

MAX_INSIGHT_CHARS = 8000


class InfrastructureFailure(Exception):
    """The measurement did not happen, as distinct from happening badly.

    A candidate whose evaluator was killed by an out-of-memory event from an
    unrelated job on the box has told the run nothing about itself, and
    recording it beside candidates that produced wrong answers costs twice:
    it pushes the failure-rate check toward the "the harness is wrong" stop,
    and it writes a technique into the negative record as *refuted* when it
    was never actually tested. A future run then avoids an idea nobody tried.

    The boundary is not "did it fail" but "was the candidate the reason".
    A timeout at the declared budget is a GENUINE failure --- the budget is
    part of the problem statement, and a candidate too slow to finish inside
    it has been measured. What lands here is the machine or the harness
    breaking: the evaluator command not existing, or the evaluator itself
    saying so.

    Raised rather than threaded through the return tuples: every layer
    between here and main() would otherwise grow a field it only forwards."""


def load_spec(experiment: str) -> dict:
    path = os.path.join(experiment, "experiment.json")
    if not os.path.exists(path):
        raise SystemExit(f"no experiment spec at {path}")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def clip(text: str) -> str:
    """Truncate loudly. Silent truncation has bitten every log pipeline that
    ever tried it --- the sentinel you need is always just past the cut."""
    if len(text) <= MAX_INSIGHT_CHARS:
        return text
    return text[:MAX_INSIGHT_CHARS] + f"\n...[truncated, {len(text)} chars total]"


def run(cmd, cwd, timeout) -> tuple[int, str, str, float]:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr, time.monotonic() - started
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout or ""
        err = exc.stderr or ""
        if isinstance(out, bytes):
            out = out.decode("utf-8", "replace")
        if isinstance(err, bytes):
            err = err.decode("utf-8", "replace")
        return 124, out, err + f"\n[timeout after {timeout}s]", time.monotonic() - started
    except FileNotFoundError as exc:
        return 127, "", f"{exc}", time.monotonic() - started


def machine_lock_path() -> str:
    """One lock file per user in the system temp dir, shared by every
    experiment and every tune.py sweep this user runs on the machine. Two
    users benchmarking one box still have to talk to each other."""
    return os.path.join(tempfile.gettempdir(), f"evolve-measure-{os.getuid()}.lock")


def acquire_experiment_lock(experiment: str):
    """Serialize this experiment's candidates against each other.

    Strategists and implementers parallelize fine, but benchmarks racing are
    timing each other's cache pressure, and the scores stop being comparable
    candidate-to-candidate. Held through the gate, the evaluation, the
    snapshot and the database append --- the last of which also closes the
    load-modify-save race between two candidates finishing at the same
    moment. The handle is returned so it outlives this function; the lock
    releases when the process exits."""
    if fcntl is None:
        return None
    # noqa SIM115: deliberately not a context manager --- the handle must
    # outlive this function, or the lock releases mid-measurement.
    fh = open(os.path.join(experiment, ".ae-lock"), "w")  # noqa: SIM115
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("waiting for another candidate's measurement to finish...", file=sys.stderr)
        fcntl.flock(fh, fcntl.LOCK_EX)
    return fh


class MachineLock:
    """The machine-wide measurement lock, with reader-writer semantics.

    The per-experiment lock cannot see a SECOND experiment. Two performance
    runs measuring at once time each other's cache pressure and thermal
    state, and a multithreaded benchmark contends for every core on the box.
    The corruption is silent --- both runs complete, both record numbers,
    both sets of numbers are wrong --- and it was observed in practice,
    which is why this is a lock and not a paragraph of advice.

    Not all evaluation is timing, though, and flock gives the honest split
    for free:

      exclusive (LOCK_EX) --- anything timed. One holder on the machine.
      shared    (LOCK_SH) --- anything untimed: correctness gates, numerical
        accuracy, code size, output quality. Any number run together, but
        all of them wait while an exclusive holder measures, and an
        exclusive measurement waits until they finish --- untimed work is
        parallel-safe against itself, never against someone's benchmark,
        because it still costs cores.

    Which mode a stage gets is planned in experiment.json at design time:
    `measurement.machine_exclusive` (default true) sets the experiment's
    default, and a cascade stage may override with its own
    `machine_exclusive` --- the common shape being an untimed correctness
    screen that runs shared while only the timed final stage serializes.
    The correctness gate always runs shared: its output is pass/fail, not a
    number.

    Mode changes release and reacquire (flock upgrades can deadlock); the
    gap between stages is a safe place to lose the lock. Lock order is
    fixed --- experiment first, then machine --- and tune.py takes only the
    machine lock, so the two cannot deadlock. Per user, in the system temp
    dir: two users benchmarking one box still have to talk to each other."""

    def __init__(self) -> None:
        self.fh = None
        self.mode = None

    def ensure(self, exclusive: bool) -> None:
        if fcntl is None:
            return
        want = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        if self.fh is not None and self.mode == want:
            return
        self.release()
        fh = open(machine_lock_path(), "w")  # noqa: SIM115 --- held across stages
        try:
            fcntl.flock(fh, want | fcntl.LOCK_NB)
        except OSError:
            kind = "exclusively" if exclusive else "for shared use"
            print(f"waiting to hold the machine {kind} (another measurement is running)...", file=sys.stderr)
            fcntl.flock(fh, want)
        self.fh, self.mode = fh, want

    def release(self) -> None:
        if self.fh is not None:
            self.fh.close()
            self.fh, self.mode = None, None


def check_gate(spec: dict, candidate_dir: str, insights: list) -> bool:
    """Run the project's correctness gate against the candidate."""
    gate = spec.get("correctness_gate")
    if not gate:
        return True
    cmd = gate if isinstance(gate, list) else ["/bin/sh", "-c", gate]
    timeout = spec.get("gate_timeout_seconds", 600)
    code, out, err, secs = run(cmd, candidate_dir, timeout)
    if code == 127:
        raise InfrastructureFailure(f"correctness gate command not found: {clip(err)}")
    if code != 0:
        insights.append({"label": "correctness_gate_failed", "text": clip(out + "\n" + err)})
        return False
    insights.append({"label": "correctness_gate", "text": f"passed in {secs:.1f}s"})
    return True


def stages_of(spec: dict) -> list[dict]:
    """The evaluation cascade, as a list of stages.

    A flat `evaluator.command` is just a one-stage cascade, so the rest of the
    code has a single shape to handle and old experiments keep working."""
    ev = spec.get("evaluator") or {}
    if ev.get("stages"):
        return [dict(s) for s in ev["stages"]]
    return [{"name": "main", **{k: v for k, v in ev.items() if k != "stages"}}]


def run_cascade(
    spec: dict, experiment: str, candidate_dir: str, insights: list, mlock: MachineLock
) -> tuple[float | None, dict, str, dict | None, dict | None]:
    """Evaluate through stages of increasing cost, stopping at the first refusal.

    Most candidates are broken or obviously worse, and finding that out on a
    small input at low repeats costs a fraction of the real benchmark. The
    budget saved is not a nicety: redirected into repeats on the few survivors,
    it is usually what makes the noise floor narrow enough to resolve the
    effect being looked for at all.

    A candidate that fails to clear a stage is *screened out*, which is
    reported separately from a crash --- with a cascade, a high elimination
    rate is the system working, and conflating the two makes the health checks
    cry wolf on every run.
    """
    stages = stages_of(spec)
    # Only the LAST stage's objectives count, same rule as the score: earlier
    # stages are filters, and screening stages routinely measure a cheaper
    # proxy that has no business on the Pareto front.
    axes = evolve_db.objective_axes(spec)
    default_exclusive = (spec.get("measurement") or {}).get("machine_exclusive", True)
    metrics: dict = {}
    score: float | None = None
    objectives: dict | None = None
    cases: dict | None = None

    for i, stage in enumerate(stages):
        name = stage.get("name") or f"stage{i}"
        is_last = i == len(stages) - 1
        mlock.ensure(exclusive=bool(stage.get("machine_exclusive", default_exclusive)))
        score, stage_metrics, objectives, stage_cases = run_stage(
            stage, name, experiment, candidate_dir, insights, axes if is_last else []
        )
        # Same rule as the score and the objectives: a screening stage's cases
        # come from a cheaper proxy suite, and comparing a child's screen cases
        # against a parent's full-benchmark cases would report coverage the
        # candidate never demonstrated.
        cases = stage_cases if is_last else None
        for k, v in stage_metrics.items():
            metrics[f"{name}.{k}" if len(stages) > 1 else k] = v
        if score is None:
            return None, metrics, "eval_failed", None, None

        threshold = stage.get("promote_if_score_at_least")
        if not is_last and threshold is not None and score < float(threshold):
            insights.append(
                {
                    "label": "screened_out",
                    "text": f"stage {name!r} scored {score:.6g}, below the promotion threshold "
                    f"{float(threshold):.6g}; later stages were not run",
                }
            )
            metrics["screened_out_at"] = name
            return None, metrics, "screened_out", None, None

    # The last stage's score is the candidate's score; earlier stages are
    # filters, and their cheaper, noisier numbers must never rank anything.
    return score, metrics, "scored", objectives, cases


def run_stage(
    stage: dict, name: str, experiment: str, candidate_dir: str, insights: list, axes: list[str]
) -> tuple[float | None, dict, dict | None, dict | None]:
    cmd = stage.get("command")
    if not cmd:
        raise SystemExit(f"evaluator stage {name!r} has no command")
    if isinstance(cmd, str):
        cmd = ["/bin/sh", "-c", cmd]
    timeout = stage.get("timeout_seconds", 300)
    repeats = max(1, int(stage.get("repeats", 1)))

    samples: list[float] = []
    axis_samples: dict[str, list[float]] = {a: [] for a in axes}
    case_samples: dict[str, list[float]] = {}
    case_keys: set[str] | None = None
    metrics: dict = {}
    for i in range(repeats):
        with tempfile.NamedTemporaryFile("r+", suffix=".json", delete=False) as tmp:
            out_path = tmp.name
        try:
            full = [*cmd, "--program-dir", os.path.abspath(candidate_dir), "--output-file", out_path]
            # The evaluator runs from the experiment directory, so its command
            # and any relative paths inside it (benchmark inputs, held-out
            # sets) resolve the same way no matter where the candidate copy
            # lives --- candidates are routinely evaluated out of /tmp.
            code, out, err, secs = run(full, os.path.abspath(experiment), timeout)
            if out.strip():
                insights.append({"label": f"{name}_stdout_{i}", "text": clip(out)})
            if err.strip():
                insights.append({"label": f"{name}_stderr_{i}", "text": clip(err)})
            if code == 127 and not os.path.getsize(out_path):
                raise InfrastructureFailure(f"evaluator stage {name!r} command not found: {clip(err)}")
            if code != 0 and not os.path.getsize(out_path):
                insights.append({"label": f"{name}_evaluator_failed", "text": f"exit {code} after {secs:.1f}s"})
                return None, metrics, None, None
            try:
                with open(out_path, encoding="utf-8") as fh:
                    result = json.load(fh)
            except (OSError, json.JSONDecodeError) as exc:
                insights.append({"label": f"{name}_evaluator_output_unreadable", "text": f"{exc}"})
                return None, metrics, None, None
        finally:
            if os.path.exists(out_path):
                os.unlink(out_path)

        for ins in result.get("insights") or []:
            if isinstance(ins, dict) and "text" in ins:
                insights.append({"label": str(ins.get("label", "insight")), "text": clip(str(ins["text"]))})
        metrics.update(result.get("metrics") or {})

        # The evaluator is the only thing that can tell a candidate's fault
        # from the machine's, because it is the only thing that knows what it
        # was doing when it died. It says so here; the harness never guesses.
        if result.get("failure") == "infrastructure":
            raise InfrastructureFailure(
                f"evaluator stage {name!r} reported an infrastructure failure on repeat {i}"
            )

        score = result.get("score")
        if score is None:
            insights.append({"label": f"{name}_no_score", "text": "evaluator returned null score"})
            return None, metrics, None, None
        try:
            score = float(score)
        except (TypeError, ValueError):
            insights.append({"label": f"{name}_bad_score", "text": f"score not numeric: {score!r}"})
            return None, metrics, None, None
        # NaN and Inf are not valid JSON and will poison every downstream
        # statistic; reject them here rather than let them into the database.
        if math.isnan(score) or math.isinf(score):
            insights.append({"label": f"{name}_non_finite_score", "text": f"score was {score}"})
            return None, metrics, None, None
        samples.append(score)

        # Multi-objective mode: every declared axis must be present and
        # finite. A partial vector is a failure, not a smaller success ---
        # recorded with a hole, it would sit beside complete vectors looking
        # rankable while being incomparable to every one of them.
        for a in axes:
            raw = (result.get("objectives") or {}).get(a)
            v = float(raw) if isinstance(raw, (int, float)) else math.nan
            if math.isnan(v) or math.isinf(v):
                insights.append(
                    {
                        "label": f"{name}_bad_objective",
                        "text": f"declared axis {a!r} missing or non-finite in evaluator output",
                    }
                )
                return None, metrics, None, None
            axis_samples[a].append(v)

        # Per-case scores, when the evaluator reports a suite. The key set is
        # fixed by the first repeat and every later one must match it: a case
        # that appears in one sample and not the next gives each case a
        # different denominator, and the medians below would then be taken
        # over silently different populations. Same reasoning as a partial
        # objective vector --- a hole is a failure, not a smaller success.
        cases = result.get("cases")
        if i == 0:
            case_keys = set(cases) if isinstance(cases, dict) else None
        if (case_keys is not None) != isinstance(cases, dict) or (
            case_keys is not None and set(cases) != case_keys
        ):
            insights.append(
                {
                    "label": f"{name}_case_set_moved",
                    "text": "per-case scores must carry the same keys on every repeat",
                }
            )
            return None, metrics, None, None
        for k, raw in (cases or {}).items():
            v = float(raw) if isinstance(raw, (int, float)) else math.nan
            if math.isnan(v) or math.isinf(v):
                insights.append({"label": f"{name}_bad_case", "text": f"case {k!r} was {raw!r}"})
                return None, metrics, None, None
            case_samples.setdefault(str(k), []).append(v)

    objectives: dict | None = None
    if axes:
        objectives = {a: statistics.median(vs) for a, vs in axis_samples.items()}
        if repeats > 1:
            metrics["objective_ranges"] = {a: max(vs) - min(vs) for a, vs in axis_samples.items()}

    cases_out = {k: statistics.median(vs) for k, vs in case_samples.items()} or None

    if len(samples) > 1:
        metrics["score_samples"] = samples
        metrics["score_stdev"] = statistics.pstdev(samples)
        metrics["score_range"] = max(samples) - min(samples)
        return statistics.median(samples), metrics, objectives, cases_out
    return samples[0], metrics, objectives, cases_out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--experiment", required=True)
    ap.add_argument("--candidate-dir", required=True, help="directory holding this candidate's program")
    ap.add_argument("--id", required=True, help="program id, e.g. gen-007-b")
    ap.add_argument("--parent", default=None)
    # Free-form: the policy is a label for later analysis, not a control. A
    # closed set blocks legitimate uses (re-scoring under a new metric, repair
    # passes, hand-written controls) for no benefit.
    ap.add_argument("--policy", default=None, help="greedy | novel | seed | any label you want to group by")
    ap.add_argument("--strategy-file", default=None, help="markdown file with the strategy that produced this")
    ap.add_argument("--generation", type=int, default=None)
    ap.add_argument("--repeats", type=int, default=None, help="override evaluator.repeats")
    ap.add_argument("--skip-gate", action="store_true", help="skip the correctness gate (say why in --note)")
    ap.add_argument("--note", default=None)
    ap.add_argument(
        "--new-lineage",
        action="store_true",
        help="root a new lineage even though this has a parent --- use when a candidate "
        "restarts from the seed with a structurally different approach, so the diversity "
        "metric can see it",
    )
    ap.add_argument(
        "--sanity",
        action="store_true",
        help="a deliberate harness check (broken candidate, positive control), not a real "
        "attempt --- kept in the record but excluded from the failure rate",
    )
    ap.add_argument("--dry-run", action="store_true", help="evaluate but do not record")
    args = ap.parse_args()

    # The snapshot is written once and never overwritten, but evaluation.json
    # is written unconditionally --- so re-running an existing id with changed
    # source leaves the two describing DIFFERENT programs, silently. Observed
    # in the wild: an implementer scored a candidate, edited it in place to a
    # fallback variant, and re-ran the same id. The database refused the
    # duplicate (so it kept the first program's score) while evaluation.json
    # was replaced by the second program's numbers, next to the first
    # program's snapshot. Anyone re-deriving from the directory instead of the
    # database then reads a score that source never produced --- and the whole
    # claim of the snapshot is that every number stays re-derivable from a
    # stored artifact. Refuse the collision rather than half-record it.
    # Checked before the gate: failing fast costs nothing, failing after the
    # evaluation costs the whole measurement.
    if not args.dry_run:
        snap = os.path.join(args.experiment, "generations", args.id, "program")
        if os.path.exists(snap) and os.path.isdir(args.candidate_dir):
            differs = subprocess.run(
                ["diff", "-rq", snap, args.candidate_dir], capture_output=True
            ).returncode
            if differs:
                sys.exit(
                    f"refusing to score: generations/{args.id}/program already exists "
                    f"and differs from {args.candidate_dir}.\n"
                    f"Re-running an id with changed source would leave the snapshot and "
                    f"evaluation.json describing different programs.\n"
                    f"Use a new id (e.g. {args.id}-v2), or delete the stale generation "
                    f"directory if it was a mistake."
                )

    spec = load_spec(args.experiment)
    if args.repeats is not None:
        ev = spec.setdefault("evaluator", {})
        if ev.get("stages"):
            for st in ev["stages"]:
                st["repeats"] = args.repeats
        else:
            ev["repeats"] = args.repeats

    insights: list[dict] = []
    score: float | None = None
    valid = True

    # Held until process exit: gate, evaluation, snapshot, database append.
    _exp_lock = acquire_experiment_lock(args.experiment)  # noqa: F841
    mlock = MachineLock()

    metrics: dict = {}
    objectives: dict | None = None
    cases: dict | None = None
    status = "pending"
    try:
        if args.skip_gate:
            insights.append({"label": "correctness_gate", "text": f"SKIPPED: {args.note or 'no reason given'}"})
        else:
            # The gate is untimed (pass/fail), so it runs shared: parallel with
            # other untimed work, never during someone's exclusive measurement.
            mlock.ensure(exclusive=False)
            if not check_gate(spec, args.candidate_dir, insights):
                valid = False
                status = "gate_failed"

        if valid:
            score, metrics, status, objectives, cases = run_cascade(
                spec, args.experiment, args.candidate_dir, insights, mlock
            )
            valid = score is not None
    except InfrastructureFailure as exc:
        insights.append({"label": "infrastructure_failure", "text": str(exc)})
        valid, status = False, "infra_failed"
    mlock.release()

    strategy = ""
    if args.strategy_file and os.path.exists(args.strategy_file):
        with open(args.strategy_file, encoding="utf-8") as fh:
            strategy = fh.read().strip()

    gen_dir = os.path.join(args.experiment, "generations", args.id)
    os.makedirs(gen_dir, exist_ok=True)
    with open(os.path.join(gen_dir, "evaluation.json"), "w", encoding="utf-8") as fh:
        json.dump(
            {"score": score, "objectives": objectives, "cases": cases, "valid": valid, "status": status,
             "metrics": metrics, "insights": insights},
            fh, indent=2,
        )
    # Keep the exact program that produced this number. Without the snapshot
    # a winning score is unreproducible the moment the working copy moves on.
    snapshot = os.path.join(gen_dir, "program")
    if not args.dry_run and not os.path.exists(snapshot):
        shutil.copytree(args.candidate_dir, snapshot, dirs_exist_ok=False)

    record = {
        "id": args.id,
        "parent": args.parent,
        "generation": args.generation,
        "policy": args.policy,
        "score": score,
        "valid": valid,
        "status": status,
        "metrics": metrics,
        "strategy": strategy,
        "note": args.note,
        "evaluation": os.path.relpath(os.path.join(gen_dir, "evaluation.json"), args.experiment),
    }
    if objectives is not None:
        record["objectives"] = objectives
    if cases is not None:
        record["cases"] = cases
    if args.sanity:
        record["kind"] = "sanity"
    if args.new_lineage:
        # Without this a "fresh start from the seed" inherits the seed's
        # lineage_root, so the population looks converged even when the novel
        # policy is doing its job. Ancestry is not the same as approach.
        record["lineage_root"] = args.id

    if args.dry_run:
        print(json.dumps({k: v for k, v in record.items() if k != "strategy"}, indent=2))
        return

    prev = evolve_db.load(args.experiment)
    prev_best = prev.get("best_score")
    prev_front = set(prev.get("front") or [])
    evolve_db.add_record(args.experiment, record)
    db = evolve_db.load(args.experiment)
    best = db.get("best_score")
    shown = f"{score:.6g}" if score is not None else status.upper()
    if objectives:
        shown += "  " + "  ".join(f"{a}={v:.6g}" for a, v in objectives.items())
    marker = ""
    axes = evolve_db.objective_axes(spec)
    if axes:
        # Front membership is noise-aware: it means "beaten beyond noise
        # nowhere", so within-noise ties coexist on the front rather than
        # displacing each other --- displacing is the beyond-noise claim.
        front = db.get("front") or []
        if args.id in front:
            displaced = prev_front - set(front)
            marker = f"  <-- on the Pareto front (size {len(front)}"
            marker += f", displaced {len(displaced)})" if displaced else ")"
    elif db.get("best") == args.id:
        marker = "  <-- new best"
        floor = spec.get("noise_floor")
        # A "new best" inside the noise floor is a tie the measurement cannot
        # resolve, and celebrating it is how noise gets climbed.
        if (
            isinstance(floor, (int, float))
            and isinstance(prev_best, (int, float))
            and score is not None
            and score - prev_best <= floor
        ):
            marker = "  <-- new best (within noise of previous best --- not yet a claim)"
    print(f"{args.id}: score={shown}  best={best if best is None else f'{best:.6g}'}{marker}")
    # A candidate can beat its parent on the aggregate while giving up whole
    # cases, and that trade is invisible in every number printed above ---
    # which is the entire reason the per-case vector exists. Say it here, at
    # the moment the number lands, or it will only ever be found by someone
    # reading the database.
    cov = evolve_db.by_id(db, args.id).get("coverage") or {}
    if cov.get("lost") or cov.get("dropped"):
        gave_up = ", ".join((cov.get("lost") or []) + [f"{k} (not reported)" for k in cov.get("dropped") or []])
        held = "" if cov.get("eligible", True) else " --- not eligible as a parent"
        print(f"  gave up: {gave_up}  (regression {cov.get('regression', 0):.6g}){held}", file=sys.stderr)
    if status == "infra_failed":
        print(
            "  the measurement did not happen --- this says nothing about the candidate. "
            "Fix the machine or the harness and re-score it under a NEW id; do not record "
            "its strategy as a dead end.",
            file=sys.stderr,
        )
    if not valid:
        labels = ", ".join(i["label"] for i in insights)
        print(f"  failure insights: {labels}", file=sys.stderr)


if __name__ == "__main__":
    main()

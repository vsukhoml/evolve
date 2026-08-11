#!/usr/bin/env python3
"""Parameter search that runs to completion in ONE process, with no LLM in the loop.

Use this whenever the thing being optimized is a *parameter* rather than a
*structure*: booleans, categoricals, numeric constants, build flags. An LLM
loop spends minutes of agent time per candidate to wrap seconds of
measurement; this spends the seconds. It is not a smarter search, it is the
same search without the tax, and it is usually 20-100x more evaluations for
the same wall clock.

The LLM's job around this script is to design the space, launch it, and read
the progress file occasionally. Not to drive iterations.

Design rules, all of which exist because a long unattended run is only useful
if an interruption costs nothing:

  * **Every result is appended and flushed immediately** to results.jsonl
    (flush + fsync). A kill -9 at any moment loses at most the evaluation in
    flight.
  * **The best point is written atomically** to best.json on every improvement
    (temp file + os.replace). You can never end a run holding a corrupt or
    empty best.
  * **Restart resumes.** On start it reads results.jsonl and skips points
    already measured, so stopping and restarting is free and safe.
  * **Progress is a line per evaluation on stderr, flushed**, plus a heartbeat,
    so `tail -f` distinguishes "working" from "hung".
  * **It stops early on convergence** and on a wall-clock cap, and SIGINT /
    SIGTERM finish the current evaluation and exit cleanly with the best kept.

Evaluator contract (same shape as the main harness):

    <command...> --params PARAMS.json --output-file OUT.json
    OUT.json: {"score": <float, higher is better>, "metrics": {...}}

A null / missing / non-finite score is recorded as a failure, not a zero --
zero is a legitimate score in many problems and silently coercing to it is how
a search learns to prefer crashes.

Usage:
    tune.py --space space.json --command "python3 evaluator/evaluate_params.py" \\
            --out tuning/ --method grid --repeats 3 --noise-floor 0.5 \\
            --patience 40 --max-seconds 3600

space.json:
    {"BLOCK": {"type": "int", "values": [8, 12, 16, 20, 24]},
     "USE_FAST_PATH": {"type": "bool"},
     "MODE": {"type": "cat", "values": ["a", "b", "c"]},
     "THRESH": {"type": "float", "low": 0.1, "high": 4.0, "steps": 12}}
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import random
import signal
import statistics
import subprocess
import sys
import tempfile
import time

STOP = False


def _stop(signum, _frame):
    """Finish the evaluation in flight, then exit cleanly. Never lose the best."""
    global STOP
    STOP = True
    log(f"signal {signum} received -- finishing current evaluation, then stopping")


def log(msg: str) -> None:
    """Progress goes to stderr, flushed, so `tail -f` is live rather than buffered."""
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def expand(space: dict) -> tuple[list[str], list[list]]:
    """Turn the space spec into (names, per-name candidate value lists)."""
    names, axes = [], []
    for name, spec in space.items():
        kind = spec.get("type", "cat")
        if kind == "bool":
            vals = [False, True]
        elif kind in ("int", "cat"):
            vals = list(spec["values"])
        elif kind == "float":
            lo, hi, n = spec["low"], spec["high"], int(spec.get("steps", 10))
            vals = [lo + (hi - lo) * i / (n - 1) for i in range(n)] if n > 1 else [lo]
        else:
            raise SystemExit(f"unknown parameter type {kind!r} for {name!r}")
        names.append(name)
        axes.append(vals)
    return names, axes


def key_of(point: dict) -> str:
    """Stable identity for a point, so resume can skip what is already measured."""
    return json.dumps(point, sort_keys=True, default=str)


def measure(command: list[str], point: dict, repeats: int, workdir: str) -> tuple[float | None, dict]:
    """Run the evaluator `repeats` times; return the MEDIAN score and last metrics.

    Median rather than mean: one scheduler hit should not decide a parameter.
    """
    scores, metrics = [], {}
    for _ in range(repeats):
        with tempfile.TemporaryDirectory(dir=workdir) as td:
            pf, of = os.path.join(td, "params.json"), os.path.join(td, "out.json")
            with open(pf, "w") as fh:
                json.dump(point, fh)
            try:
                subprocess.run([*command, "--params", pf, "--output-file", of],
                               capture_output=True, timeout=3600, check=False)
                with open(of) as fh:
                    res = json.load(fh)
            # noqa BLE001: the search must survive any evaluator failure --- a crash,
            # a timeout, or no output file at all is just a failed point, not a
            # reason to abandon the run. The reason is recorded, not raised.
            except Exception as exc:  # noqa: BLE001
                return None, {"error": f"{type(exc).__name__}: {exc}"}
            s = res.get("score")
            if s is None or not math.isfinite(float(s)):
                return None, res.get("metrics", {})
            scores.append(float(s))
            metrics = res.get("metrics", {})
    return statistics.median(scores), metrics


def order_points(method: str, names, axes, seed: int) -> list[dict]:
    """Enumerate the search order. Keep this dumb and inspectable.

    `grid`   -- every combination, in order. Right when the space is small.
    `random` -- every combination, shuffled. Right when you may stop early:
                a truncated random order is an unbiased sample, a truncated
                grid is a biased one (it has only explored low values of the
                first axis).
    `coord`  -- coordinate descent from the first value of each axis: sweep one
                axis at a time, keep the winner, move on. Cheap when the
                parameters are roughly separable -- but VERIFY separability
                rather than assuming it, or this converges confidently to a
                point no full grid would pick.
    """
    if method in ("grid", "random"):
        pts = [dict(zip(names, combo, strict=True)) for combo in itertools.product(*axes)]
        if method == "random":
            random.Random(seed).shuffle(pts)
        return pts
    if method == "coord":
        base = {n: a[0] for n, a in zip(names, axes, strict=True)}
        pts, seen = [], set()
        for n, a in zip(names, axes, strict=True):
            for v in a:
                p = dict(base, **{n: v})
                if key_of(p) not in seen:
                    seen.add(key_of(p))
                    pts.append(p)
        return pts
    raise SystemExit(f"unknown method {method!r} (grid | random | coord)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--space", required=True, help="JSON file describing the parameter space")
    ap.add_argument("--command", required=True, help="evaluator command (quoted)")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--method", default="random", help="grid | random | coord")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--noise-floor", type=float, default=0.0,
                    help="improvements smaller than this do not count as improvements")
    ap.add_argument("--patience", type=int, default=0,
                    help="stop after N consecutive evaluations with no improvement above the floor (0 = never)")
    ap.add_argument("--max-seconds", type=float, default=0.0, help="wall-clock cap (0 = none)")
    ap.add_argument("--seed", type=int, default=42, help="recorded, so the run is reproducible")
    args = ap.parse_args()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    os.makedirs(args.out, exist_ok=True)
    results_path = os.path.join(args.out, "results.jsonl")
    best_path = os.path.join(args.out, "best.json")

    with open(args.space) as fh:
        space = json.load(fh)
    names, axes = expand(space)
    points = order_points(args.method, names, axes, args.seed)

    # Resume: anything already in results.jsonl is not re-measured.
    done, best, best_point = {}, None, None
    if os.path.exists(results_path):
        with open(results_path) as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue  # a torn final line from a hard kill; ignore it
                done[key_of(row["point"])] = row
                if row.get("score") is not None and (best is None or row["score"] > best):
                    best, best_point = row["score"], row["point"]
        log(f"resumed: {len(done)} point(s) already measured, best so far {best}")

    total = len(points)
    log(f"space {total} point(s), method={args.method}, repeats={args.repeats}, "
        f"floor={args.noise_floor}, patience={args.patience or 'off'}, "
        f"cap={args.max_seconds or 'none'}s")

    started, since_improve, evaluated, failed = time.time(), 0, 0, 0
    with open(results_path, "a") as fh:
        for i, point in enumerate(points, 1):
            if STOP:
                log("stopping: signal")
                break
            if args.max_seconds and time.time() - started > args.max_seconds:
                log(f"stopping: wall-clock cap after {evaluated} evaluation(s)")
                break
            if args.patience and since_improve >= args.patience:
                log(f"stopping: converged -- {since_improve} evaluations with no gain above {args.noise_floor}")
                break
            if key_of(point) in done:
                continue

            t0 = time.time()
            score, metrics = measure(args.command.split(), point, args.repeats, args.out)
            evaluated += 1
            row = {"point": point, "score": score, "metrics": metrics,
                   "seconds": round(time.time() - t0, 3), "at": time.strftime("%Y-%m-%dT%H:%M:%S")}

            # Append + flush + fsync BEFORE anything else: a result that exists is
            # never lost, whatever happens next.
            fh.write(json.dumps(row, default=str) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

            if score is None:
                failed += 1
                since_improve += 1
                log(f"[{i}/{total}] FAILED {point}  ({row['seconds']}s)")
                continue

            improved = best is None or score > best + args.noise_floor
            if improved:
                best, best_point, since_improve = score, point, 0
                tmp = best_path + ".tmp"
                with open(tmp, "w") as bf:
                    json.dump({"score": best, "point": best_point, "metrics": metrics,
                               "evaluated": evaluated, "at": row["at"]}, bf, indent=2)
                os.replace(tmp, best_path)  # atomic: best.json is never half-written
                log(f"[{i}/{total}] NEW BEST {score:.6g}  {point}  ({row['seconds']}s)")
            else:
                since_improve += 1
                log(f"[{i}/{total}] {score:.6g} (best {best:.6g}, {since_improve} since gain)  "
                    f"{point}  ({row['seconds']}s)")

    elapsed = time.time() - started
    log(f"done: {evaluated} evaluated ({failed} failed) in {elapsed:.0f}s; best {best} at {best_point}")
    print(json.dumps({"best_score": best, "best_point": best_point,
                      "evaluated": evaluated, "failed": failed,
                      "seconds": round(elapsed, 1), "results": results_path}, indent=2))


if __name__ == "__main__":
    main()

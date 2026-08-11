#!/usr/bin/env python3
"""Evaluator template --- copy to <experiment>/evaluator/evaluate.py and fill in.

Contract (see the skill's references/evaluator_contract.md):
    invoked as: evaluate.py --program-dir DIR --output-file OUT
    writes JSON: {"score": float|null, "metrics": {...}, "insights": [...]}
    higher score is always better; negate anything you want small.

The three things this template exists to get right, because they are the three
that are always wrong in a hand-written first draft:

  1. It builds and measures from --program-dir. Nothing is baked in, so
     evaluating a candidate cannot accidentally measure the original.
  2. It takes repeated samples and reports the median plus the spread. A
     single timing sample cannot tell a real 3% win from machine noise.
  3. It verifies the result is still correct on a checksum before reporting a
     score, which closes the "instant because it computes nothing" hole.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import subprocess
import sys
import time

# --- configure these three ------------------------------------------------

# Command to build the candidate, run inside --program-dir. None if none.
BUILD_CMD: list[str] | None = None          # e.g. ["cargo", "build", "--release"]

# Command that runs the benchmark and prints one number (nanoseconds, or
# whatever your metric is) to stdout, plus a correctness checksum on the
# second line. Run inside --program-dir.
BENCH_CMD: list[str] = ["python3", "bench.py"]

# Repeats performed inside this script. evolve_run.py can repeat on top of this;
# internal repeats are cheaper, external ones also capture build variance.
REPEATS = 5

# The checksum the benchmark must produce for the answer to count. Compute it
# once from the untouched seed program and paste it here. Without this, a
# candidate that returns nothing looks infinitely fast.
EXPECTED_CHECKSUM: str | None = None

# Smaller is better for a latency metric, so the score is negated. Set to
# +1 if your metric is already "higher is better" (throughput, density).
SIGN = -1

# --------------------------------------------------------------------------


def run(cmd: list[str], cwd: str, timeout: int) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)
    return proc.returncode, proc.stdout, proc.stderr


def evaluate(program_dir: str) -> dict:
    insights: list[dict] = []
    metrics: dict = {}

    def fail(label: str, text: str) -> dict:
        insights.append({"label": label, "text": text[:8000]})
        return {"score": None, "metrics": metrics, "insights": insights}

    if BUILD_CMD:
        started = time.monotonic()
        try:
            code, out, err = run(BUILD_CMD, program_dir, timeout=600)
        except subprocess.TimeoutExpired:
            return fail("build_timeout", "build exceeded 600s")
        if code != 0:
            return fail("build_failed", out + "\n" + err)
        metrics["build_seconds"] = round(time.monotonic() - started, 2)

    samples: list[float] = []
    for i in range(REPEATS):
        try:
            code, out, err = run(BENCH_CMD, program_dir, timeout=300)
        except subprocess.TimeoutExpired:
            return fail("bench_timeout", f"benchmark exceeded 300s on repeat {i}")
        if code != 0:
            return fail("bench_failed", out + "\n" + err)

        lines = [ln.strip() for ln in out.strip().splitlines() if ln.strip()]
        if not lines:
            return fail("bench_no_output", "benchmark printed nothing")

        try:
            value = float(lines[0])
        except ValueError:
            return fail("bench_unparseable", f"first line was not a number: {lines[0]!r}")

        # Correctness check. A candidate that stopped computing the answer
        # would otherwise post the best score in the run.
        if EXPECTED_CHECKSUM is not None:
            got = lines[1] if len(lines) > 1 else "<missing>"
            if got != EXPECTED_CHECKSUM:
                return fail("wrong_result", f"checksum {got!r} != expected {EXPECTED_CHECKSUM!r}")

        samples.append(value)

    median = statistics.median(samples)
    metrics["samples"] = samples
    metrics["median"] = median
    metrics["stdev"] = statistics.pstdev(samples)
    metrics["range"] = max(samples) - min(samples)

    score = SIGN * median
    # NaN is not valid JSON and Inf wins every comparison forever; neither
    # belongs in the database.
    if math.isnan(score) or math.isinf(score):
        return fail("non_finite_score", f"score was {score}")

    insights.append({"label": "measurement", "text": f"median={median:.6g} over {REPEATS} repeats, spread={metrics['range']:.6g}"})
    return {"score": score, "metrics": metrics, "insights": insights}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--program-dir", required=True)
    ap.add_argument("--output-file", required=True)
    args = ap.parse_args()

    try:
        result = evaluate(os.path.abspath(args.program_dir))
    except Exception as exc:  # noqa: BLE001 --- the loop needs the reason, not a stack unwind
        import traceback

        result = {
            "score": None,
            "metrics": {},
            "insights": [{"label": "evaluator_crashed", "text": traceback.format_exc()[:8000]}],
        }
        print(f"evaluator crashed: {exc}", file=sys.stderr)

    # Always write the file, even on failure --- a loop that gets no output
    # cannot tell "broken candidate" from "broken evaluator".
    with open(args.output_file, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)


if __name__ == "__main__":
    main()

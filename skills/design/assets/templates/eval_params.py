#!/usr/bin/env python3
"""Parameter-mode evaluator --- copy to <experiment>/evaluator/eval_params.py.

This is the entry point `tune.py` drives. It exists so the parametric half of
the change space can be searched by a script with no LLM in its loop, while
still being measured by the *same* instrument as an LLM candidate.

Contract (deliberately different from the candidate evaluator's):
    invoked as: eval_params.py --params PARAMS.json --output-file OUT.json
    writes JSON: {"score": float|null, "metrics": {...}, "insights": [...]}
    higher score is always better --- same units, same sign, as evaluate.py.

The one thing this template exists to get right: **it does not re-implement
scoring.** It materialises a parameterised copy of the program and then calls
the candidate evaluator's own `evaluate()` on it. Two hand-written scorers drift
--- a repeat count here, a warmup there --- and the moment they do, the sweep's
winner cannot be folded back into the seed and compared, because you no longer
have one experiment. Delegating makes the agreement structural instead of
something to remember.

Fill in `apply_params` and nothing else. Two patterns cover most targets, and
both are shown below: rewriting named constants in the source, and emitting a
config file the program reads at startup.

Usage:
    # one point, by hand --- this is gate check 7's probe
    echo '{"BLOCK": 64}' > /tmp/p.json
    python3 evaluator/eval_params.py --params /tmp/p.json --output-file /tmp/o.json

    # the whole space, unattended
    python3 .ae/tune.py --space tuning/space.json \\
        --command "python3 evaluator/eval_params.py" \\
        --out tuning/ --method grid --repeats 3 --noise-floor <floor> \\
        --patience 40 --max-seconds 3600 2> tuning/progress.log
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evaluate  # noqa: E402 --- same directory; the import needs the path above

# The program tree the parameters are applied to. Relative to the experiment
# root, which is where the evaluator is run from.
PROGRAM_DIR = "program"

# Which file each parameter lives in, for the constant-rewriting pattern.
# Delete this if you use the config-file pattern instead.
PARAM_FILES: dict[str, str] = {
    # "BLOCK_THRESHOLD": "src/lookup.rs",
}


def apply_params(program_dir: str, params: dict) -> list[str]:
    """Write `params` into the copied program. Return one note per applied value.

    Raise on anything unapplied. A parameter that silently fails to land is the
    worst outcome available here: the sweep runs to completion, every point
    measures the same program, and the flat response reads as "this knob does
    not matter" --- which is indistinguishable from the truth and much more
    expensive.
    """
    notes = []

    # --- Pattern A: rewrite a named constant in the source ------------------
    # Matches `NAME = 123`, `NAME: usize = 123`, `#define NAME 123`, etc. Adapt
    # the regex to the host language rather than trusting this one.
    for name, value in params.items():
        rel = PARAM_FILES.get(name)
        if rel is None:
            raise KeyError(f"parameter {name!r} has no entry in PARAM_FILES")
        path = os.path.join(program_dir, rel)
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        pattern = rf"(\b{re.escape(name)}\b[^=\n]*=\s*)([^;\n]+)"
        repl = lambda m, v=value: m.group(1) + json.dumps(v)  # noqa: E731 --- bind v per iteration
        new_src, n = re.subn(pattern, repl, src, count=1)
        if n != 1:
            raise ValueError(f"parameter {name!r} matched {n} times in {rel} --- expected exactly 1")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(new_src)
        notes.append(f"{name}={value!r} -> {rel}")

    # --- Pattern B: emit a config the program reads at startup --------------
    # Simpler and harder to get wrong, when the program can be made to read it.
    # Replace the loop above with:
    #
    #     with open(os.path.join(program_dir, "params.json"), "w") as fh:
    #         json.dump(params, fh)
    #     notes.append(f"wrote params.json: {params}")
    #
    # Prefer this when you control the program. Rewriting source is for targets
    # whose constants must stay compile-time.

    return notes


def evaluate_point(params: dict) -> dict:
    """Copy the program, apply the point, and score it with the candidate evaluator."""
    src = os.path.abspath(PROGRAM_DIR)
    with tempfile.TemporaryDirectory(prefix="ae-params-") as tmp:
        work = os.path.join(tmp, "program")
        shutil.copytree(src, work)
        notes = apply_params(work, params)
        result = evaluate.evaluate(work)

    result.setdefault("metrics", {})["params"] = params
    result.setdefault("insights", []).append({"label": "params_applied", "text": "; ".join(notes)})
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", required=True)
    ap.add_argument("--output-file", required=True)
    args = ap.parse_args()

    try:
        with open(args.params, encoding="utf-8") as fh:
            point = json.load(fh)
        result = evaluate_point(point)
    except Exception as exc:  # noqa: BLE001 --- a bad point is a failed point, not a dead sweep
        result = {
            "score": None,
            "metrics": {},
            "insights": [{"label": "eval_params_crashed", "text": traceback.format_exc()[:8000]}],
        }
        print(f"eval_params crashed: {exc}", file=sys.stderr)

    # Always write the file, even on failure --- tune.py reads this, not the
    # exit code, and a missing file is indistinguishable from a hung evaluator.
    with open(args.output_file, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)


if __name__ == "__main__":
    main()

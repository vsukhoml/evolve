#!/usr/bin/env python3
"""Render the state of an experiment: leaderboard, trajectory, health checks.

Reads `evolution.json` and writes nothing but a report, so it is safe to run
against a live experiment at any time --- including from a second terminal
while the loop is mid-generation.

The health checks exist because the two ways these runs fail quietly are
(a) the population collapsing onto one lineage, after which every "new"
candidate is a cousin of the last twenty, and (b) improvements that are
smaller than the measurement noise, which look like progress on a chart and
vanish on re-measurement. Both are invisible in a leaderboard.

Usage:
  evolve_report.py --experiment DIR [--write dashboard.md] [--json] [--top N]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evolve_db  # noqa: E402  (dominance helpers; the report must rank exactly as the database does)

CRASH_SENTINEL = -1e9
SPARK = "▁▂▃▄▅▆▇█"


def load(experiment: str) -> dict:
    with open(os.path.join(experiment, "evolution.json"), encoding="utf-8") as fh:
        return json.load(fh)


def load_spec(experiment: str) -> dict:
    path = os.path.join(experiment, "experiment.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def usable(p: dict) -> bool:
    s = p.get("score")
    if not isinstance(s, (int, float)) or not math.isfinite(s) or s <= CRASH_SENTINEL:
        return False
    if not p.get("valid", True):
        return False
    return (p.get("review") or {}).get("verdict") != "reject"


def sparkline(values: list[float]) -> str:
    if not values:
        return ""
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        return SPARK[0] * len(values)
    return "".join(SPARK[min(7, int((v - lo) / (hi - lo) * 7.999))] for v in values)


def running_best(programs: list[dict]) -> list[float]:
    out, best = [], None
    for p in programs:
        if usable(p):
            best = p["score"] if best is None else max(best, p["score"])
        if best is not None:
            out.append(best)
    return out


def hypervolume_2d(vectors: list[list[float]], ref: list[float]) -> float:
    """Area dominated by a 2-D front, measured from a reference point.

    The one scalar that summarizes a front's progress: it grows when the
    front extends OR fills in, where any single axis's best would miss half
    of that. Only defined for two axes --- exact hypervolume is exponential
    in dimensions, and a front the owner is meant to read should be 2-D
    anyway. Points at or below the reference contribute nothing.
    """
    pts = sorted(((v[0], v[1]) for v in vectors if v[0] > ref[0] and v[1] > ref[1]), reverse=True)
    hv, last1 = 0.0, ref[1]
    for p0, p1 in pts:
        if p1 > last1:
            hv += (p0 - ref[0]) * (p1 - last1)
            last1 = p1
    return hv


def since_front_change(programs: list[dict], pool: list[dict], spec: dict) -> int:
    """Candidates since the Pareto front last changed.

    Replays the run and recomputes the front after each scored program ---
    quadratic-ish, fine at the tens-to-hundreds this loop produces. This is
    the plateau signal in Pareto mode: the primary axis can stall for a long
    time while the front is still genuinely filling in, and a scalar
    "no improvement in N" check would call that a plateau and stop a run
    that is working.
    """
    seen: list[dict] = []
    last_change = 0
    prev: set[str] = set()
    members = {id(p) for p in pool}
    for i, p in enumerate(programs):
        if id(p) in members:
            seen.append(p)
            ids = {q["id"] for q in evolve_db.pareto_front(seen, spec)}
            if ids != prev:
                last_change = i
                prev = ids
    return max(0, len(programs) - 1 - last_change)


def analyze(db: dict, spec: dict) -> dict:
    programs = db.get("programs", [])
    pool = [p for p in programs if usable(p)]
    rejected = [p for p in programs if (p.get("review") or {}).get("verdict") == "reject"]
    # Screened-out candidates are the cascade working as designed --- counting
    # them as crashes would make the health check cry wolf on every staged run.
    screened = [p for p in programs if p.get("status") == "screened_out"]
    # Deliberate harness checks are meant to fail; counting them as crashes
    # makes a well-validated experiment look broken.
    sanity = [p for p in programs if p.get("kind") == "sanity"]
    failed = [
        p for p in programs
        if not usable(p) and p not in rejected and p not in screened and p not in sanity
    ]

    lineages = {p.get("lineage_root") or p["id"] for p in pool}
    curve = running_best(programs)

    since_best = 0

    # The noise floor: the largest spread any single candidate showed across
    # its own repeated measurements. An improvement smaller than this is not
    # distinguishable from the machine having a bad afternoon.
    noise = 0.0
    for p in pool:
        # Cascade stages namespace their metrics ("full.score_range"), so an
        # exact-key lookup silently reports a zero noise floor --- which then
        # disables the "gain is inside the noise" check entirely, the single
        # most important guard in the report.
        for k, rng in (p.get("metrics") or {}).items():
            if not (k == "score_range" or k.endswith(".score_range")):
                continue
            if isinstance(rng, (int, float)) and math.isfinite(rng):
                noise = max(noise, rng)
    spec_floor = spec.get("noise_floor")
    if isinstance(spec_floor, (int, float)) and spec_floor > noise:
        noise = float(spec_floor)

    baseline = spec.get("baseline_score")
    # Derive rather than trust `db["best_score"]`: a reviewer verdict recorded
    # after the fact (the veto path) changes who the best is, and a stale stored
    # field then reports a winner the leaderboard has already removed.
    ranked_now = sorted(pool, key=lambda p: p["score"], reverse=True)
    best_score = ranked_now[0]["score"] if ranked_now else None
    best_id = ranked_now[0]["id"] if ranked_now else None
    gain = None
    if isinstance(baseline, (int, float)) and isinstance(best_score, (int, float)):
        gain = best_score - baseline

    if best_id:
        ids = [p["id"] for p in programs]
        if best_id in ids:
            since_best = len(ids) - 1 - ids.index(best_id)

    checks = []
    if screened:
        checks.append(
            (
                "OK",
                f"{len(screened)} candidate(s) screened out by the evaluation cascade "
                f"before the full benchmark",
                "This is the cascade doing its job --- cheap stages killing weak candidates so "
                "the repeats get spent on survivors. It is not a failure rate.",
            )
        )
    if programs:
        crash_pct = 100.0 * len(failed) / max(1, len(programs) - len(screened) - len(sanity))
        checks.append(
            (
                "OK" if crash_pct < 25 else ("WARN" if crash_pct < 60 else "BAD"),
                f"{crash_pct:.0f}% of evaluated candidates failed to produce a score "
                f"({len(failed)}/{len(programs) - len(screened) - len(sanity)})",
                "High failure rates usually mean the strategist is being asked to change "
                "too much at once, or the evolve block does not contain enough context to "
                "edit safely.",
            )
        )
    if len(pool) >= 6:
        checks.append(
            (
                "OK" if len(lineages) >= 3 else "WARN",
                f"{len(lineages)} distinct lineage(s) among {len(pool)} scored programs",
                "One lineage means the population has converged on a single family; the "
                "novel-policy strategist is either not running or its proposals are all "
                "being rejected.",
            )
        )
    if since_best >= 10:
        checks.append(
            (
                "WARN" if since_best < 25 else "BAD",
                f"no improvement in the last {since_best} candidates",
                "Either the search space around the current best is exhausted (try a novel-"
                "policy generation or a fresh seed), or the fitness function has stopped "
                "discriminating.",
            )
        )
    if gain is not None and noise > 0 and abs(gain) <= noise:
        checks.append(
            (
                "BAD",
                f"best gain ({gain:+.6g}) is inside the measurement noise (±{noise:.6g})",
                "Nothing has been demonstrated yet. Raise evaluator.repeats or make the "
                "benchmark bigger before trusting any of this.",
            )
        )

    # Multi-objective mode: the front, its progress scalar, and its own
    # plateau signal. The scalar checks above still run --- score is the
    # first axis --- but the plateau question must be asked of the front:
    # the primary axis can stall while the front genuinely fills in.
    axes = evolve_db.objective_axes(spec)
    front_ids: list[str] = []
    hypervolume = None
    since_front = None
    if axes:
        front = evolve_db.pareto_front(pool, spec)
        front_ids = [p["id"] for p in front]
        ref = (spec.get("objectives") or {}).get("hypervolume_ref")
        if len(axes) == 2 and isinstance(ref, dict):
            r0, r1 = ref.get(axes[0]), ref.get(axes[1])
            if isinstance(r0, (int, float)) and isinstance(r1, (int, float)):
                vecs = [v for p in front if (v := evolve_db.objective_vector(p, axes)) is not None]
                hypervolume = hypervolume_2d(vecs, [float(r0), float(r1)])
        since_front = since_front_change(programs, pool, spec)
        if since_front >= 10:
            checks.append(
                (
                    "WARN" if since_front < 25 else "BAD",
                    f"Pareto front unchanged for the last {since_front} candidates",
                    "The front neither extended nor filled in. Either the trade-off surface "
                    "is exhausted at this granularity, or every candidate is chasing the "
                    "same corner of it --- check which front points recent parents came from.",
                )
            )

    return {
        "programs": len(programs),
        "scored": len(pool),
        "failed": len(failed),
        "screened_out": len(screened),
        "sanity_checks": len(sanity),
        "rejected": len(rejected),
        "lineages": len(lineages),
        "best": best_id,
        "best_score": best_score,
        "baseline_score": baseline,
        "gain": gain,
        "noise_floor": noise,
        "since_best": since_best,
        "curve": curve,
        "objectives": axes or None,
        "front": front_ids or None,
        "front_size": len(front_ids) if axes else None,
        "hypervolume": hypervolume,
        "since_front_change": since_front,
        "checks": [{"level": lvl, "finding": f, "why": w} for lvl, f, w in checks],
    }


def render(db: dict, spec: dict, stats: dict, top: int) -> str:
    ranked = sorted((p for p in db.get("programs", []) if usable(p)), key=lambda p: p["score"], reverse=True)
    lines = []
    lines.append(f"# {spec.get('name') or db.get('experiment', 'experiment')}")
    lines.append("")
    if spec.get("objective"):
        lines.append(f"**Objective** — {spec['objective']}")
    if spec.get("metric"):
        lines.append(f"**Metric** — {spec['metric']}")
    lines.append(f"**Updated** — {db.get('updated', '?')}  ")
    lines.append("")

    best = stats["best_score"]
    base = stats["baseline_score"]
    head = f"**Best** {best:.6g}" if isinstance(best, (int, float)) else "**Best** none yet"
    if isinstance(base, (int, float)):
        head += f" vs baseline {base:.6g}"
        if stats["gain"] is not None:
            head += f" ({stats['gain']:+.6g})"
    head += f"  |  {stats['scored']}/{stats['programs']} scored"
    head += f"  |  {stats['lineages']} lineage" + ("s" if stats["lineages"] != 1 else "")
    if stats["noise_floor"]:
        head += f"  |  noise ±{stats['noise_floor']:.3g}"
    if stats.get("front_size"):
        head += f"  |  front {stats['front_size']} pt" + ("s" if stats["front_size"] != 1 else "")
    if stats.get("hypervolume") is not None:
        head += f"  |  HV {stats['hypervolume']:.6g}"
    lines.append(head)
    lines.append("")

    if stats.get("objectives"):
        axes = stats["objectives"]
        by_id = {p["id"]: p for p in db.get("programs", [])}
        lines.append(f"## Pareto front ({', '.join(axes)})")
        lines.append("")
        for pid in stats.get("front") or []:
            p = by_id.get(pid) or {}
            vals = "  ".join(f"{a}={((p.get('objectives') or {}).get(a, float('nan'))):.6g}" for a in axes)
            strat = (p.get("strategy") or "").splitlines()
            tail = f" — {strat[0][:60]}" if strat else ""
            lines.append(f"- `{pid}` — {vals} — {p.get('policy') or '—'}{tail}")
        if not stats.get("front"):
            lines.append("_No complete objective vectors yet._")
        lines.append("")

    if stats["curve"]:
        lines.append("## Trajectory (running best)")
        lines.append("")
        lines.append("```")
        lines.append(sparkline(stats["curve"]))
        lines.append("```")
        lines.append("")

    lines.append("## Leaderboard")
    lines.append("")
    if not ranked:
        lines.append("_No scored programs yet._")
    else:
        lines.append("| # | id | score | policy | strategy |")
        lines.append("|---|----|-------|--------|----------|")
        for i, p in enumerate(ranked[:top], 1):
            # Seed and hand-scored rows carry no strategy at all, so guard the
            # empty case rather than indexing into an empty split.
            head = (p.get("strategy") or "").splitlines()
            strat = (head[0][:70] if head else "—").replace("|", "\\|")
            lines.append(f"| {i} | `{p['id']}` | {p['score']:.6g} | {p.get('policy') or '—'} | {strat} |")
    lines.append("")

    if stats["checks"]:
        lines.append("## Health")
        lines.append("")
        for c in stats["checks"]:
            lines.append(f"- **[{c['level']}]** {c['finding']}")
            lines.append(f"  - {c['why']}")
        lines.append("")

    failures = [p for p in db.get("programs", []) if not usable(p)]
    if failures:
        lines.append("## Recent failures")
        lines.append("")
        for p in failures[-5:]:
            verdict = (p.get("review") or {}).get("verdict")
            reason = "rejected by review" if verdict == "reject" else "no valid score"
            note = (p.get("note") or "").splitlines()
            lines.append(f"- `{p['id']}` — {reason}: {note[0][:100] if note else ''}")
        lines.append("")

    lines.append(f"_Generated {datetime.now().isoformat(timespec='seconds')}_")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--experiment", required=True)
    ap.add_argument("--write", default=None, help="write markdown here (relative to the experiment dir)")
    ap.add_argument("--json", action="store_true", help="emit stats as JSON instead of markdown")
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()

    db = load(args.experiment)
    spec = load_spec(args.experiment)
    stats = analyze(db, spec)

    if args.json:
        print(json.dumps(stats, indent=2))
        return

    md = render(db, spec, stats, args.top)
    if args.write:
        path = args.write if os.path.isabs(args.write) else os.path.join(args.experiment, args.write)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(md)
        print(os.path.abspath(path))
    else:
        print(md)


if __name__ == "__main__":
    main()

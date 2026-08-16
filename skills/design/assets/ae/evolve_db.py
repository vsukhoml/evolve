#!/usr/bin/env python3
"""Evolution database for an evolution experiment.

Everything the run has learned lives in one JSON file, `evolution.json`:
each program's score, its parent, the strategy that produced it, and the
reviewer's verdict. Plain JSON rather than a service is deliberate --- an
experiment directory stays inspectable with `cat`, diffable in git, portable
between machines, and resumable after any interruption. The loop is allowed
to crash; the database is the memory that survives it.

Single-scalar by default. When `experiment.json` declares `objectives`
(see the multi-objective section below), records additionally carry an
objective vector, the ranking becomes noise-aware Pareto dominance, and
`best` prints the front instead of a leaderboard. `score` stays the first
axis either way, so every scalar tool keeps working.

Two further opt-ins narrow what may be built on without touching how
anything is ranked: `preserve_and_extend` compares a child to its parent
case by case and stops a program that traded cases away from becoming an
ancestor, and `promotion.confirm_before_steering` makes greedy selection
wait for a higher-fidelity re-measurement. Both are declared in
`experiment.json`; see the coverage section below.

Only the Python standard library is used, so this runs anywhere python3 does.

Usage:
  evolve_db.py init    --experiment DIR
  evolve_db.py add     --experiment DIR --record FILE|-
  evolve_db.py best    --experiment DIR [--top N] [--json]
  evolve_db.py select  --experiment DIR --n K [--policy greedy|novel|mix] [--seed S]
  evolve_db.py show    --experiment DIR --id ID
  evolve_db.py lineage --experiment DIR --id ID
  evolve_db.py review  --experiment DIR --id ID --verdict accept|reject|suspect [--reason TEXT]...
  evolve_db.py confirm --experiment DIR --id ID [--score S] [--repeats N] [--cases FILE]
  evolve_db.py label   --experiment DIR --id ID --failure-mode LABEL
  evolve_db.py stats   --experiment DIR
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import tempfile
from datetime import datetime, timezone

DB_NAME = "evolution.json"

# A score below this is treated as a crash sentinel rather than a real
# measurement. Evaluators that return large negative numbers on failure
# (a common shortcut) would otherwise drag every statistic with them.
CRASH_SENTINEL = -1e9


# --------------------------------------------------------------------------
# storage
# --------------------------------------------------------------------------


def db_path(experiment: str) -> str:
    return os.path.join(experiment, DB_NAME)


def load(experiment: str) -> dict:
    path = db_path(experiment)
    if not os.path.exists(path):
        raise SystemExit(f"no database at {path} --- run `evolve_db.py init` first")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def save(experiment: str, db: dict) -> None:
    """Write atomically: a half-written database after a crash would lose the
    whole run, and the loop writes on every generation."""
    path = db_path(experiment)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(db, fh, indent=2, sort_keys=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_spec(experiment: str) -> dict:
    """The experiment spec, or {} --- the database must stay usable (init,
    add, stats) before a spec exists, and after one is deleted."""
    path = os.path.join(experiment, "experiment.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------
# multi-objective (Pareto) support
# --------------------------------------------------------------------------
#
# Off unless experiment.json declares it:
#
#   "objectives": {"axes": ["neg_median_ns", "neg_code_bytes"],
#                  "noise_floors": {"neg_median_ns": 0.5}}
#
# Every axis keeps the scalar convention --- higher is better, negate what
# should shrink --- and `score` remains the FIRST axis, so the scalar
# machinery (crash sentinel, baselines, trajectory) needs no second code
# path. Dominance is noise-aware: a per-axis difference inside that axis's
# declared floor counts as equal, so a candidate reaches the front only by
# being better beyond noise somewhere and worse beyond noise nowhere.
#
# Deliberately NO NSGA-II machinery (crowding, tournaments, generations):
# populations here are tens of programs and plain dominance is enough. A
# run that genuinely needs more implements it in its own experiment
# harness, after the owner has confirmed the extra moving parts are wanted.


def objective_axes(spec: dict) -> list[str]:
    """The declared axes, or [] when the experiment is single-scalar."""
    axes = (spec.get("objectives") or {}).get("axes") or []
    return [str(a) for a in axes] if len(axes) >= 2 else []


def objective_floors(spec: dict) -> list[float]:
    floors = (spec.get("objectives") or {}).get("noise_floors") or {}
    return [float(floors.get(a) or 0.0) for a in objective_axes(spec)]


def objective_vector(p: dict, axes: list[str]) -> list[float] | None:
    """A program's objective values, or None if any axis is missing or
    non-finite --- a partial vector cannot be ranked and must not sit on
    the front looking complete."""
    vals = p.get("objectives") or {}
    out = []
    for a in axes:
        v = vals.get(a)
        if not isinstance(v, (int, float)) or not math.isfinite(v):
            return None
        out.append(float(v))
    return out


def dominates(a: list[float], b: list[float], floors: list[float]) -> bool:
    """True when `a` is at least as good as `b` everywhere (within each
    axis's noise floor) and strictly better beyond noise somewhere."""
    better = False
    for x, y, floor in zip(a, b, floors, strict=True):
        if x < y - floor:
            return False
        if x > y + floor:
            better = True
    return better


def pareto_front(pool: list[dict], spec: dict) -> list[dict]:
    """The non-dominated programs, sorted by the first axis descending.
    O(n^2) comparisons --- fine at the population sizes this loop produces."""
    axes = objective_axes(spec)
    floors = objective_floors(spec)
    vecs = [(p, v) for p in pool if (v := objective_vector(p, axes)) is not None]
    front = [p for p, v in vecs if not any(dominates(w, v, floors) for q, w in vecs if q is not p)]
    return sorted(front, key=lambda p: objective_vector(p, axes) or [], reverse=True)


def reindex_derived(db: dict, spec: dict) -> None:
    """Recompute every derived pointer (best, best_score, front) from the
    records. All three must move together: a late review veto changes both
    who the best is and who is on the front, and a stale pointer at either
    place reports a winner the ranking has already removed."""
    board = leaderboard(db, 1)
    db["best"] = board[0]["id"] if board else None
    db["best_score"] = board[0]["score"] if board else None
    if objective_axes(spec):
        db["front"] = [p["id"] for p in pareto_front(scored(db), spec)]
    db["updated"] = now()


# --------------------------------------------------------------------------
# per-case coverage: the preserve-and-extend contract
# --------------------------------------------------------------------------
#
# Off unless experiment.json declares it:
#
#   "preserve_and_extend": {"max_regression": 0.0, "case_floor": 0.25}
#
# A scalar score is a sum over the benchmark, and a sum hides a trade: the
# candidate that is 8% faster on average because it is 12% faster on four
# inputs and 3x slower on the fifth outranks the one that is 5% faster
# everywhere. On a single-input benchmark that cannot happen; on a suite it
# is the normal failure, and it is invisible until someone ships the winner
# and hears about input five.
#
# So when the evaluator reports `cases`, each child is compared to its parent
# case by case: `gain` is the summed change, `regression` the summed size of
# the losses, and a child that gave up more than `max_regression` may score,
# rank, and be reported --- it just may not be built on. Nothing is thrown
# away: the archive keeps it, because the edit that loses two cases here may
# be the one that unlocks a case nothing else reaches, and its lessons are
# worth as much as a winner's.
#
# `case_floor` (or per-case `case_floors`) is the noise floor of ONE case,
# which is wider than the aggregate's --- a median over N cases averages
# noise the individual case still carries. Only losses beyond that floor
# count toward `regression`; summing within-floor wiggle across a large
# suite would manufacture a regression out of nothing but sampling.


def preserve_config(spec: dict) -> dict | None:
    """The declared contract, or None when the experiment is aggregate-only."""
    cfg = spec.get("preserve_and_extend")
    return dict(cfg) if isinstance(cfg, dict) else None


def case_floor(cfg: dict, name: str) -> float:
    floors = cfg.get("case_floors")
    if isinstance(floors, dict) and isinstance(floors.get(name), (int, float)):
        return float(floors[name])
    return float(cfg.get("case_floor") or 0.0)


def coverage(child_cases: dict, parent_cases: dict, cfg: dict) -> dict | None:
    """Per-case change from parent to child, or None if they share no case."""
    shared = [k for k in parent_cases if k in child_cases]
    if not shared:
        return None
    gain, regression, gained, lost = 0.0, 0.0, [], []
    for k in shared:
        delta = float(child_cases[k]) - float(parent_cases[k])
        gain += delta
        if delta > case_floor(cfg, k):
            gained.append(k)
        elif -delta > case_floor(cfg, k):
            lost.append(k)
            regression += -delta
    # A case the parent reported and the child did not is not a tie --- it is
    # a case whose result is unknown, and an unknown cannot be preserved.
    dropped = [k for k in parent_cases if k not in child_cases]
    cov = {"gain": gain, "regression": regression, "gained": gained, "lost": lost, "dropped": dropped}
    cov["eligible"] = not dropped and regression <= float(cfg.get("max_regression") or 0.0)
    return cov


def eligible_parent(p: dict) -> bool:
    """True when this program may be built on.

    Programs with no coverage record pass: the seed, anything whose parent
    reported no cases, and every program in an experiment that never declared
    the contract. Absence of evidence is not a regression."""
    cov = p.get("coverage")
    return cov.get("eligible", True) if isinstance(cov, dict) else True


# --------------------------------------------------------------------------
# queries
# --------------------------------------------------------------------------


def scored(db: dict) -> list[dict]:
    """Programs that produced a real, usable measurement.

    A program counts only if it ran, scored finite, and survived review. The
    reviewer's veto sits here rather than in the scoring path on purpose: a
    candidate that games the benchmark can score beautifully, and the only
    thing standing between it and the leaderboard is that veto."""
    out = []
    for p in db["programs"]:
        s = p.get("score")
        if s is None or not isinstance(s, (int, float)):
            continue
        if not math.isfinite(s) or s <= CRASH_SENTINEL:
            continue
        if not p.get("valid", True):
            continue
        if (p.get("review") or {}).get("verdict") == "reject":
            continue
        out.append(p)
    return out


def first_line(text: str | None, width: int, fallback: str = "") -> str:
    """First line of a possibly-empty, possibly-missing strategy blurb.

    Seed and hand-scored programs carry no strategy at all, so the naive
    `.splitlines()[0]` raises on exactly the rows a leaderboard must show."""
    lines = (text or "").splitlines()
    return lines[0][:width] if lines else fallback


def by_id(db: dict, pid: str) -> dict:
    for p in db["programs"]:
        if p["id"] == pid:
            return p
    raise SystemExit(f"no program with id {pid!r}")


def leaderboard(db: dict, top: int | None = None) -> list[dict]:
    ranked = sorted(scored(db), key=lambda p: p["score"], reverse=True)
    return ranked[:top] if top else ranked


def lineage_of(db: dict, pid: str) -> list[dict]:
    chain, seen = [], set()
    cur = pid
    while cur and cur not in seen:
        seen.add(cur)
        node = by_id(db, cur)
        chain.append(node)
        cur = node.get("parent")
    return list(reversed(chain))


# --------------------------------------------------------------------------
# parent selection
# --------------------------------------------------------------------------


def select_parents(db: dict, n: int, policy: str, seed: int | None = None, spec: dict | None = None) -> list[dict]:
    """Choose which programs to build on next.

    Two pressures, deliberately kept separate so a run can be diagnosed:

      greedy --- sample near the top. Exploits what already works, and is
        what produces most of the small wins.
      novel  --- sample from under-explored lineages. Without it the
        population collapses onto one family within a few generations and
        the run stops finding anything genuinely new; with it you pay some
        evaluations for coverage.

    `mix` alternates, which is the sane default. If you find yourself wanting
    a cleverer scheme, first check whether the run is actually diversity-
    starved (`evolve_report.py` reports distinct lineages) --- usually it is not
    the selection rule that is the problem but a fitness function that only
    rewards one kind of change.

    Two optional filters narrow what may be built on, both declared in
    experiment.json and both off by default:

      preserve_and_extend --- a program that gave up cases its parent solved
        is dropped from the pool entirely. It keeps its place on the
        leaderboard and in the archive; it just stops being an ancestor, so
        a lineage accumulates capabilities instead of trading them.
      promotion.confirm_before_steering --- greedy draws only from programs
        re-measured at higher fidelity (`evolve_db.py confirm`), while novel
        keeps drawing from everything. Exploration on a promising but noisy
        signal is cheap and reversible; exploitation of one is how a lucky
        measurement becomes the ancestor of the next twenty candidates.
    """
    rng = random.Random(seed)
    pool = scored(db)
    if not pool:
        # Nothing has scored yet: everything descends from the seed.
        seeds = [p for p in db["programs"] if p.get("parent") is None]
        return (seeds or db["programs"])[:1] * n if db["programs"] else []

    spec = spec or {}
    if preserve_config(spec):
        # `or pool`: a contract that admits nobody is a max_regression that
        # needs raising, not a reason to stall the run on the seed forever.
        pool = [p for p in pool if eligible_parent(p)] or pool

    steer = pool
    if (spec.get("promotion") or {}).get("confirm_before_steering"):
        steer = [p for p in pool if p.get("confirmed")] or pool

    ranked = sorted(steer, key=lambda p: p["score"], reverse=True)
    axes = objective_axes(spec)
    front = pareto_front(steer, spec) if axes else []

    def greedy_pick() -> dict:
        # Pareto mode: uniform over the front. Every non-dominated trade-off
        # is equally a "best", and weighting by any one axis would quietly
        # reintroduce the scalar ranking the front exists to avoid.
        if front:
            return rng.choice(front)
        k = max(3, len(ranked) // 10)
        head = ranked[:k]
        # Weight by rank, not by score: score scales are arbitrary across
        # problems and a raw-score weighting silently becomes near-uniform
        # (or near-deterministic) depending on the units.
        weights = [1.0 / (i + 1) for i in range(len(head))]
        return rng.choices(head, weights=weights, k=1)[0]

    def novel_pick() -> dict:
        counts: dict[str, int] = {}
        for p in pool:
            root = p.get("lineage_root") or p["id"]
            counts[root] = counts.get(root, 0) + 1
        # Favour thin lineages; a lineage with one member is as attractive as
        # a top scorer under the greedy rule.
        weights = [1.0 / counts.get(p.get("lineage_root") or p["id"], 1) for p in pool]
        return rng.choices(pool, weights=weights, k=1)[0]

    picks = []
    for i in range(n):
        if policy == "greedy":
            picks.append(greedy_pick())
        elif policy == "novel":
            picks.append(novel_pick())
        else:
            picks.append(greedy_pick() if i % 2 == 0 else novel_pick())
    return picks


# --------------------------------------------------------------------------
# mutation
# --------------------------------------------------------------------------


def add_record(experiment: str, record: dict) -> dict:
    db = load(experiment)
    if any(p["id"] == record["id"] for p in db["programs"]):
        raise SystemExit(f"duplicate program id {record['id']!r}")

    parent = record.get("parent")
    if parent and not record.get("lineage_root"):
        record["lineage_root"] = by_id(db, parent).get("lineage_root") or parent
    else:
        record.setdefault("lineage_root", record["id"])
    record.setdefault("created", now())
    record.setdefault("valid", record.get("score") is not None)

    # Coverage is computed here rather than in the runner because it is the
    # only place the parent's record is in hand.
    cfg = preserve_config(load_spec(experiment))
    if cfg and parent and record.get("cases"):
        cov = coverage(record["cases"], by_id(db, parent).get("cases") or {}, cfg)
        if cov is not None:
            record["coverage"] = cov

    db["programs"].append(record)

    reindex_derived(db, load_spec(experiment))
    save(experiment, db)
    return record


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def cmd_init(args) -> None:
    path = db_path(args.experiment)
    if os.path.exists(path) and not args.force:
        raise SystemExit(f"{path} already exists (pass --force to reset)")
    os.makedirs(args.experiment, exist_ok=True)
    save(
        args.experiment,
        {
            "experiment": os.path.basename(os.path.abspath(args.experiment)),
            "created": now(),
            "updated": now(),
            "best": None,
            "best_score": None,
            "programs": [],
        },
    )
    print(path)


def cmd_add(args) -> None:
    if args.record == "-":
        raw = sys.stdin.read()
    else:
        with open(args.record, encoding="utf-8") as fh:
            raw = fh.read()
    rec = add_record(args.experiment, json.loads(raw))
    print(json.dumps({"id": rec["id"], "score": rec.get("score"), "lineage_root": rec["lineage_root"]}))


def cmd_best(args) -> None:
    db = load(args.experiment)
    spec = load_spec(args.experiment)
    axes = objective_axes(spec)
    if axes:
        # The front IS the answer in Pareto mode: a top-N by any single axis
        # would rank trade-offs the experiment declared incomparable.
        front = pareto_front(scored(db), spec)
        if args.json:
            print(json.dumps(front, indent=2))
            return
        if not front:
            print("no scored programs yet")
            return
        print(f"Pareto front: {len(front)} point(s) over ({', '.join(axes)})")
        for p in front:
            vals = "  ".join(f"{a}={p['objectives'][a]:.6g}" for a in axes)
            print(f"  {p['id']:<24} {vals}  {first_line(p.get('strategy'), 50, '-')}")
        return
    board = leaderboard(db, args.top)
    if args.json:
        print(json.dumps(board, indent=2))
        return
    if not board:
        print("no scored programs yet")
        return
    print(f"{'rank':<5} {'id':<24} {'score':>14}  strategy")
    for i, p in enumerate(board, 1):
        print(f"{i:<5} {p['id']:<24} {p['score']:>14.6g}  {first_line(p.get('strategy'), 60, '—')}")


def cmd_select(args) -> None:
    db = load(args.experiment)
    picks = select_parents(db, args.n, args.policy, args.seed, load_spec(args.experiment))
    print(
        json.dumps(
            [
                {
                    "id": p["id"],
                    "score": p.get("score"),
                    "lineage_root": p.get("lineage_root"),
                    "strategy": p.get("strategy"),
                }
                for p in picks
            ],
            indent=2,
        )
    )


def cmd_show(args) -> None:
    print(json.dumps(by_id(load(args.experiment), args.id), indent=2))


def cmd_lineage(args) -> None:
    for depth, p in enumerate(lineage_of(load(args.experiment), args.id)):
        score = p.get("score")
        shown = f"{score:.6g}" if isinstance(score, (int, float)) else "none"
        print(f"{'  ' * depth}{p['id']}  score={shown}  {first_line(p.get('strategy'), 70, 'seed')}")


def cmd_review(args) -> None:
    """Record a reviewer verdict and recompute the winner, in one step.

    The two must land together: a `reject` can dethrone the stored best, and
    editing the JSON by hand leaves a stale winner pointing at a vetoed
    candidate — while also skipping the atomic write that protects the
    database from a mid-write crash."""
    db = load(args.experiment)
    p = by_id(db, args.id)
    p["review"] = {"verdict": args.verdict, "reasons": args.reason or [], "reviewed": now()}
    reindex_derived(db, load_spec(args.experiment))
    save(args.experiment, db)
    out = {"id": args.id, "verdict": args.verdict, "best": db["best"], "best_score": db["best_score"]}
    if "front" in db:
        out["front"] = db["front"]
    print(json.dumps(out))


def cmd_confirm(args) -> None:
    """Record a higher-fidelity re-measurement of a program.

    This is what earns the right to steer: under
    `promotion.confirm_before_steering`, greedy selection draws only from
    confirmed programs, so a candidate can enter the archive on a cheap noisy
    signal and still not become the ancestor of a whole branch until the
    signal has been re-earned. The confirmation deliberately does NOT replace
    the recorded score --- the record stays as measured, and a run whose
    selection data quietly absorbed its own re-measurements has thrown away
    the split-sample guarantee that makes the final number honest.

    Its cases, though, DO replace the coverage record: it is the same
    quantity measured better, and a preservation probe that re-samples the
    parent's solved cases is the whole point of running one."""
    db = load(args.experiment)
    p = by_id(db, args.id)
    entry: dict = {"repeats": args.repeats, "at": now()}
    if args.score is not None:
        entry["score"] = args.score
    if args.note:
        entry["note"] = args.note
    if args.cases:
        with open(args.cases, encoding="utf-8") as fh:
            cases = json.load(fh)
        if not isinstance(cases, dict):
            raise SystemExit(f"{args.cases} must hold a JSON object of case-name -> score")
        entry["cases"] = cases
        cfg = preserve_config(load_spec(args.experiment))
        parent = p.get("parent")
        if cfg and parent:
            cov = coverage(entry["cases"], by_id(db, parent).get("cases") or {}, cfg)
            if cov is not None:
                p["coverage"] = cov
    p["confirmed"] = entry
    save(args.experiment, db)
    print(json.dumps({"id": args.id, "confirmed": entry, "coverage": p.get("coverage")}, indent=2))


def cmd_label(args) -> None:
    """Attach a failure-mode label to a program.

    One small vocabulary across the run --- `timeout-setup`, `wrong-output`,
    `tool-error`, `gate-failed` --- so `evolve_report.py` can name the theme
    that dominates the whole benchmark. What that buys is a strategist brief
    aimed at the systemic bottleneck ("setup cost dominates the timeouts;
    invent a cheaper setup") instead of at one candidate's stack trace, which
    is the difference between inventing a capability and patching a task."""
    db = load(args.experiment)
    p = by_id(db, args.id)
    p["failure_mode"] = args.failure_mode
    save(args.experiment, db)
    print(json.dumps({"id": args.id, "failure_mode": args.failure_mode}))


def cmd_reindex(args) -> None:
    """Recompute `best`/`best_score` from the records.

    Reviewer verdicts are written into the database after scoring, and a veto
    changes who the winner is. Without this the stored pointer keeps naming a
    candidate the leaderboard has already removed."""
    db = load(args.experiment)
    old = db.get("best")
    reindex_derived(db, load_spec(args.experiment))
    save(args.experiment, db)
    print(f"best: {old} -> {db['best']} ({db['best_score']})")
    if "front" in db:
        print(f"front: {', '.join(db['front']) or 'empty'}")


def cmd_stats(args) -> None:
    db = load(args.experiment)
    spec = load_spec(args.experiment)
    pool = scored(db)
    total = len(db["programs"])
    lineages = {p.get("lineage_root") or p["id"] for p in pool}
    rejected = sum(1 for p in db["programs"] if (p.get("review") or {}).get("verdict") == "reject")
    # Never measured: the machine broke, not the candidate. Held apart from the
    # crash count so the negative record does not file an untested technique as
    # a refuted one.
    never_measured = sum(1 for p in db["programs"] if p.get("status") == "infra_failed")
    crashed = total - len(pool) - rejected - never_measured
    best = leaderboard(db, 1)
    since = 0
    if best:
        ids = [p["id"] for p in db["programs"]]
        since = len(ids) - 1 - ids.index(best[0]["id"])
    out = {
        "programs": total,
        "scored": len(pool),
        "rejected_by_review": rejected,
        "failed_or_crashed": crashed,
        "never_measured": never_measured,
        "distinct_lineages": len(lineages),
        # Derived, not the stored pointer: a late review verdict can
        # dethrone the stored best, and stats must not report a winner
        # the leaderboard has already removed.
        "best": best[0]["id"] if best else None,
        "best_score": best[0]["score"] if best else None,
        "programs_since_best": since,
    }
    if preserve_config(spec):
        # Counted over the scored pool: these are programs that measured fine
        # and are simply barred from being built on, which is a different
        # thing from a failure and must not be read as one.
        out["ineligible_parents"] = sum(1 for p in pool if not eligible_parent(p))
    if (spec.get("promotion") or {}).get("confirm_before_steering"):
        out["confirmed"] = sum(1 for p in pool if p.get("confirmed"))
    if objective_axes(spec):
        front = pareto_front(pool, spec)
        out["objectives"] = objective_axes(spec)
        out["front"] = [p["id"] for p in front]
        out["front_size"] = len(front)
    print(json.dumps(out, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_common(p):
        p.add_argument("--experiment", required=True, help="experiment directory")
        return p

    p = add_common(sub.add_parser("init", help="create an empty database"))
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)

    p = add_common(sub.add_parser("add", help="append a program record (JSON file or -)"))
    p.add_argument("--record", required=True)
    p.set_defaults(func=cmd_add)

    p = add_common(sub.add_parser("best", help="leaderboard"))
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_best)

    p = add_common(sub.add_parser("select", help="choose parents for the next generation"))
    p.add_argument("--n", type=int, default=2)
    p.add_argument("--policy", choices=["greedy", "novel", "mix"], default="mix")
    p.add_argument("--seed", type=int, default=None)
    p.set_defaults(func=cmd_select)

    p = add_common(sub.add_parser("show", help="one program record"))
    p.add_argument("--id", required=True)
    p.set_defaults(func=cmd_show)

    p = add_common(sub.add_parser("lineage", help="parent chain of a program"))
    p.add_argument("--id", required=True)
    p.set_defaults(func=cmd_lineage)

    p = add_common(sub.add_parser("review", help="record a reviewer verdict and recompute best"))
    p.add_argument("--id", required=True)
    p.add_argument("--verdict", required=True, choices=["accept", "reject", "suspect"])
    p.add_argument("--reason", action="append", default=None, help="repeatable; one line each")
    p.set_defaults(func=cmd_review)

    p = add_common(sub.add_parser("confirm", help="record a higher-fidelity re-measurement"))
    p.add_argument("--id", required=True)
    p.add_argument("--score", type=float, default=None, help="the confirmation score (never replaces the record's)")
    p.add_argument("--repeats", type=int, default=None, help="repeats the confirmation was measured at")
    p.add_argument("--cases", default=None, help="JSON file of per-case scores from the preservation probe")
    p.add_argument("--note", default=None)
    p.set_defaults(func=cmd_confirm)

    p = add_common(sub.add_parser("label", help="attach a failure-mode label"))
    p.add_argument("--id", required=True)
    p.add_argument("--failure-mode", required=True, help="short kebab-case label, small shared vocabulary")
    p.set_defaults(func=cmd_label)

    p = add_common(sub.add_parser("reindex", help="recompute best after hand edits to the database"))
    p.set_defaults(func=cmd_reindex)

    p = add_common(sub.add_parser("stats", help="population summary"))
    p.set_defaults(func=cmd_stats)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

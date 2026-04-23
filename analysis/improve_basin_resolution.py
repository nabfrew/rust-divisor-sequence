#!/usr/bin/env python3
"""Fill gaps in `random_seed_basin_raw.csv` to sharpen the §E.6 plot.

Reads the existing raw CSV, picks new m's that bisect the largest log-spaced
gaps between m's already sampled, sizes the new work list to fit a wall-clock
budget, then drives `divisor_series basin-scan --resume` for the remainder of
that budget. The Rust binary flushes each completed trial to disk, so killing
the process at the deadline only loses in-flight trials; a follow-up run
continues seamlessly.

Usage:
    python analysis/improve_basin_resolution.py [--runtime 60]

Re-run as often as you like — each invocation finds whatever gaps remain and
fits as many new m's into the budget as the calibrated cost model allows.
"""

import argparse
import csv
import heapq
import math
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "analysis"
RAW_OUTPUT = ANALYSIS / "random_seed_basin_raw.csv"
SEED_1_CSV = ROOT / "results_new.csv"
POSTPROCESS_SCRIPT = ANALYSIS / "build_random_seed_basin.py"

BIN_CANDIDATES = [
    ROOT / "target" / "release" / "divisor_series.exe",
    ROOT / "target" / "release" / "divisor_series",
    ROOT / "divisor_series.exe",
]


def find_binary():
    for p in BIN_CANDIDATES:
        if p.exists():
            return p
    sys.exit("divisor_series binary not found; run `cargo build --release` first.")


def load_existing(path):
    """Return (sorted_unique_ms, m -> [repeat_after,...] for timed_out==0)."""
    if not path.exists():
        return [], {}
    seen = set()
    rows = defaultdict(list)
    with open(path, newline="") as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            try:
                m = int(r["m"])
            except (KeyError, ValueError):
                continue
            seen.add(m)
            if r.get("timed_out", "0") != "0":
                continue
            try:
                rows[m].append(int(r["repeat_after"]))
            except (KeyError, ValueError):
                continue
    return sorted(seen), rows


def fit_power_law(rows):
    """Fit log(repeat_after) = log(A) + b * log(m) on geometric means per m.
    Returns (A, b) or None if too few points."""
    pts = []
    for m, ras in rows.items():
        if not ras:
            continue
        log_mean = sum(math.log(ra) for ra in ras) / len(ras)
        pts.append((math.log(m), log_mean))
    n = len(pts)
    if n < 2:
        return None
    sx = sum(x for x, _ in pts)
    sy = sum(y for _, y in pts)
    sxx = sum(x * x for x, _ in pts)
    sxy = sum(x * y for x, y in pts)
    denom = n * sxx - sx * sx
    if denom == 0:
        return None
    b = (n * sxy - sx * sy) / denom
    log_A = (sy - b * sx) / n
    return math.exp(log_A), b


def expected_repeat_after(m, model):
    A, b = model
    return A * (m ** b)


def pick_candidates(existing_ms, m_lo, m_hi, trials, model, K, budget_sec,
                    overshoot_frac, dense_below):
    """Pick new m's that fit inside the budget.

    For m in [m_lo, dense_below] every missing integer is included (costs
    are tiny down there — cap is bounded by 100·m²). Above `dense_below`,
    greedily bisect the largest log-gaps between existing m's. Stops once
    projected wall cost exceeds (1 + overshoot_frac) * budget_sec.

    Returns (chosen_ms_sorted, projected_cost_sec).
    """
    chosen = set()
    spent = 0.0
    cap = budget_sec * (1.0 + overshoot_frac)

    # Dense enumeration in the cheap low-m range.
    if dense_below >= m_lo:
        for m in range(m_lo, dense_below + 1):
            if m in existing_ms:
                continue
            # Floor per-trial cost at ~1ms of fixed overhead — the power-law
            # extrapolates to ~0 for m≈1, but rayon scheduling and file I/O
            # still cost something per trial.
            cost = trials * max(K * expected_repeat_after(m, model), 1e-3)
            if spent + cost > cap:
                break
            chosen.add(m)
            spent += cost
        bisect_lo = max(dense_below + 1, m_lo)
    else:
        bisect_lo = m_lo

    # Greedy log-gap bisection above the dense range.
    anchors = sorted({m for m in existing_ms if bisect_lo <= m <= m_hi}
                     | chosen | {bisect_lo, m_hi})
    heap = []  # (-log_gap, lo, hi)
    for lo, hi in zip(anchors[:-1], anchors[1:]):
        if hi - lo > 1:
            heapq.heappush(heap, (-(math.log(hi) - math.log(lo)), lo, hi))

    while heap:
        gap, lo, hi = heapq.heappop(heap)
        # Geometric midpoint, fall back to arithmetic if the geometric one
        # collides with an existing or already-chosen m.
        mid = round(math.sqrt(lo * hi))
        if mid <= lo or mid >= hi or mid in chosen or mid in existing_ms:
            mid = (lo + hi) // 2
            if mid <= lo or mid >= hi or mid in chosen or mid in existing_ms:
                continue
        cost = trials * K * expected_repeat_after(mid, model)
        if spent + cost > cap:
            # Skip this m; keep popping smaller gaps in case any cheaper
            # candidate still fits. Stop only when the heap empties.
            continue
        chosen.add(mid)
        spent += cost
        for a, b in ((lo, mid), (mid, hi)):
            if b - a > 1:
                heapq.heappush(heap, (-(math.log(b) - math.log(a)), a, b))
    return sorted(chosen), spent


def calibrate_K(binary, args, probe_m, probe_trials, probe_budget_sec):
    """Run a brief basin-scan probe in a temp CSV to measure
    K = wall_seconds / sum(repeat_after_completed).

    Uses an XOR'd rng_seed so probe trials don't collide with the main CSV.
    """
    with tempfile.TemporaryDirectory() as td:
        probe_csv = Path(td) / "calib.csv"
        cmd = [
            str(binary),
            "--threads", str(args.threads),
            "--progress-interval", "0",
            "basin-scan",
            "--m-list", str(probe_m),
            "--trials", str(probe_trials),
            "--sigma", str(args.sigma),
            "--rng-seed", str(args.rng_seed ^ 0xCAFEBABE),
            "--seed-1-csv", str(SEED_1_CSV),
            "--cap-multiplier", str(args.cap_multiplier),
            "--cap-floor-c-m-sq", str(args.cap_floor_c_m_sq),
            "--output", str(probe_csv),
        ]
        print(f"calibration probe: m={probe_m}, trials={probe_trials}, "
              f"budget={probe_budget_sec}s")
        t0 = time.monotonic()
        proc = subprocess.Popen(cmd, cwd=ROOT,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE)
        deadline = t0 + probe_budget_sec
        try:
            while True:
                try:
                    proc.wait(timeout=max(0.5, deadline - time.monotonic()))
                    break
                except subprocess.TimeoutExpired:
                    if time.monotonic() >= deadline:
                        proc.terminate()
                        try:
                            proc.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                        break
        except KeyboardInterrupt:
            proc.terminate()
            raise
        elapsed = time.monotonic() - t0

        total_work = 0
        n_finished = 0
        if probe_csv.exists():
            with open(probe_csv) as f:
                rdr = csv.DictReader(f)
                for r in rdr:
                    if r.get("timed_out", "0") != "0":
                        continue
                    try:
                        total_work += int(r["repeat_after"])
                        n_finished += 1
                    except (KeyError, ValueError):
                        pass
    if total_work == 0 or n_finished == 0:
        sys.exit("calibration finished no successful trials; bump --calibrate-seconds.")
    K = elapsed / total_work
    print(f"calibration: {n_finished} trials, sum(repeat_after)={total_work:,}, "
          f"elapsed={elapsed:.1f}s -> K={K:.3e} s/repeat_after_step")
    return K


def run_basin_with_deadline(binary, args, m_list_str, deadline_sec):
    cmd = [
        str(binary),
        "--threads", str(args.threads),
        "--progress-interval", "0",
        "basin-scan",
        "--m-list", m_list_str,
        "--trials", str(args.trials),
        "--sigma", str(args.sigma),
        "--seed-1-csv", str(SEED_1_CSV),
        "--cap-multiplier", str(args.cap_multiplier),
        "--cap-floor-c-m-sq", str(args.cap_floor_c_m_sq),
        "--output", str(RAW_OUTPUT),
        "--resume",
    ]
    print("running:", " ".join(cmd))
    t0 = time.monotonic()
    proc = subprocess.Popen(cmd, cwd=ROOT)
    deadline = t0 + deadline_sec
    interrupted = False
    try:
        while True:
            try:
                proc.wait(timeout=max(1.0, min(15.0, deadline - time.monotonic())))
                break
            except subprocess.TimeoutExpired:
                if time.monotonic() >= deadline:
                    print(f"\n[budget] deadline reached after "
                          f"{(time.monotonic() - t0) / 60.0:.1f} min; "
                          f"terminating subprocess (rows on disk are durable)...")
                    proc.terminate()
                    try:
                        proc.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    interrupted = True
                    break
    except KeyboardInterrupt:
        print("\n[interrupt] user Ctrl-C; terminating subprocess...")
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        interrupted = True
    return interrupted, time.monotonic() - t0


def post_process():
    cmd = [sys.executable, str(POSTPROCESS_SCRIPT), "--skip-binary"]
    print("post-process:", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=False)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--runtime", type=float, default=60.0,
                   help="Total wall-clock budget in minutes (default 60).")
    p.add_argument("--trials", type=int, default=200,
                   help="Trials per new m (default 200, matches existing rows).")
    p.add_argument("--sigma", type=float, default=0.71)
    p.add_argument("--rng-seed", type=int, default=42)
    p.add_argument("--cap-multiplier", type=int, default=20)
    p.add_argument("--cap-floor-c-m-sq", type=int, default=500)
    p.add_argument("--threads", type=int, default=0)
    p.add_argument("--m-lo", type=int, default=None,
                   help="Override low end of m-range. Default: 1 if --dense-below "
                        "is set, otherwise min existing m.")
    p.add_argument("--m-hi", type=int, default=None,
                   help="Override high end (default: max existing m).")
    p.add_argument("--dense-below", type=int, default=0,
                   help="Sample every integer m in [m_lo, dense_below] (cheap at "
                        "low m). Set to 100 to sweep the full lower range 1..100.")
    p.add_argument("--calibrate-seconds", type=float, default=30.0,
                   help="Wall budget for the calibration probe (default 30).")
    p.add_argument("--calibrate-trials", type=int, default=64,
                   help="Trials in the calibration probe (default 64).")
    p.add_argument("--overshoot-frac", type=float, default=0.10,
                   help="Allow planned cost to exceed budget by this fraction "
                        "(the wall-clock kill enforces the hard cap).")
    p.add_argument("--no-postprocess", action="store_true",
                   help="Skip the build_random_seed_basin.py --skip-binary step.")
    p.add_argument("--dry-run", action="store_true",
                   help="Plan candidates and print, but do not run basin-scan.")
    args = p.parse_args()

    binary = find_binary()
    existing_ms, existing_rows = load_existing(RAW_OUTPUT)
    if not existing_ms:
        sys.exit(f"{RAW_OUTPUT} has no rows yet; run "
                 f"`python analysis/build_random_seed_basin.py` first to seed it.")
    model = fit_power_law(existing_rows)
    if model is None:
        sys.exit("Not enough successful rows in the raw CSV to fit a cost model.")
    A, b = model
    if args.m_lo is not None:
        m_lo = args.m_lo
    elif args.dense_below > 0:
        m_lo = 1
    else:
        m_lo = existing_ms[0]
    m_hi = args.m_hi if args.m_hi is not None else existing_ms[-1]
    print(f"existing: {len(existing_ms)} m's in [{existing_ms[0]}, {existing_ms[-1]}], "
          f"target range [{m_lo}, {m_hi}]"
          + (f", dense fill <= {args.dense_below}" if args.dense_below else ""))
    print(f"cost model: E[repeat_after] ~ {A:.3g} * m^{b:.3f}")

    total_budget_sec = args.runtime * 60.0
    if total_budget_sec <= args.calibrate_seconds + 30.0:
        sys.exit(f"--runtime {args.runtime} min is too short to leave room for "
                 f"calibration ({args.calibrate_seconds:.0f}s) + safety (30s).")

    # Calibration probe on a representative m: geometric midpoint of the range,
    # snapped to an existing m so we don't burn the probe on a slow outlier.
    target_probe_m = round(math.sqrt(m_lo * m_hi))
    probe_m = min(existing_ms, key=lambda m: abs(math.log(m) - math.log(target_probe_m)))
    K = calibrate_K(binary, args, probe_m, args.calibrate_trials,
                    args.calibrate_seconds)

    # Spend the rest of the budget on the main run.
    spent_so_far = args.calibrate_seconds  # upper bound
    remaining = total_budget_sec - spent_so_far - 30.0  # 30s safety margin
    print(f"budget: total={total_budget_sec:.0f}s, calibration~{spent_so_far:.0f}s, "
          f"remaining~{remaining:.0f}s for new trials")

    chosen, planned_cost = pick_candidates(
        set(existing_ms), m_lo, m_hi, args.trials, model, K,
        remaining, args.overshoot_frac, args.dense_below,
    )
    if not chosen:
        print("No new m's would fit in the remaining budget; nothing to do.")
        if not args.no_postprocess:
            post_process()
        return
    print(f"plan: {len(chosen)} new m's, projected cost {planned_cost:.0f}s "
          f"({planned_cost / 60:.1f} min)")
    print(f"  candidates: {chosen}")

    if args.dry_run:
        print("dry-run: stopping before basin-scan.")
        return

    interrupted, elapsed = run_basin_with_deadline(
        binary, args, ",".join(str(m) for m in chosen), remaining,
    )
    print(f"basin-scan {'killed at deadline' if interrupted else 'finished'} "
          f"after {elapsed:.0f}s ({elapsed / 60:.1f} min)")

    if not args.no_postprocess:
        post_process()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Run the E.6 random-seed basin scan and post-process the output.

Pipeline:
  1. Build the m sample plan: N log-stepped from [m_lo, m_hi] plus the
     fixed-point primes from `analysis/fixed_points.csv`.
  2. Invoke `divisor_series.exe basin-scan` (uncapped — every trial runs to
     cycle detection; the binary's u16-truncation fix removed the need for
     per-trial caps that were emitting partial-trial corrupted rows).
  3. Post-process the binary's CSV to add `attractor_id` by SHA256-hashing
     each row's distinct value set the same way `build_attractors.py` does,
     then joining to `analysis/attractors.csv`.

Usage:
    python analysis/build_random_seed_basin.py [--trials K] [--m-count N]
                                                [--sigma s] [--rng-seed S]
                                                [--no-resume]

`--resume` (default on) keeps successful rows from a prior run by passing
`--resume` to the binary. Pre-fix timeout rows in the existing raw CSV are
dropped first so they get retried under the un-truncated dynamics; partial
rows whose `max_value` was clamped at 65,535 should also be cleared and
re-run (they'll resolve to a different number now). With `--no-resume`
the raw CSV is overwritten.

Defaults (K=200, N=80) match the ROADMAP §E.6 target. Smaller settings
(K=100, N=30) cut wall-clock ~5× at the cost of per-m basin density.
"""

import argparse
import csv
import hashlib
import math
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "analysis"
RAW_OUTPUT = ANALYSIS / "random_seed_basin_raw.csv"
FINAL_OUTPUT = ANALYSIS / "random_seed_basin.csv"
FIXED_POINTS_CSV = ANALYSIS / "fixed_points.csv"
ATTRACTORS_CSV = ANALYSIS / "attractors.csv"
SEED_1_CSV = ROOT / "results_new.csv"

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


def fixed_point_primes(path):
    if not path.exists():
        return []
    primes = []
    with open(path) as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            if row["prime"].strip().lower() == "true":
                primes.append(int(row["m"]))
    return primes


def log_step_ms(m_lo, m_hi, count):
    if count <= 0:
        return []
    if count == 1:
        return [m_lo]
    log_lo = math.log(m_lo)
    log_hi = math.log(m_hi)
    out = []
    for i in range(count):
        t = i / (count - 1)
        v = round(math.exp(log_lo + t * (log_hi - log_lo)))
        v = max(m_lo, min(m_hi, v))
        if not out or out[-1] != v:
            out.append(v)
    return out


def value_set_hash(value_set_str):
    """SHA256[:16] of the sorted distinct values, one-per-line. Matches the
    `value_set_hash` column in analysis/attractors.csv."""
    if not value_set_str:
        return ""
    h = hashlib.sha256()
    for v in value_set_str.split(";"):
        h.update(v.encode())
        h.update(b"\n")
    return h.hexdigest()[:16]


def drop_timeouts(path):
    """Rewrite `path` keeping only header + rows with timed_out == 0. Returns
    (kept, dropped). Used in `--resume` mode so the binary re-runs timed-out
    trials under the new cap-floor instead of skipping them."""
    with open(path, newline="") as fin:
        rdr = csv.reader(fin)
        rows = list(rdr)
    if not rows:
        return 0, 0
    header, body = rows[0], rows[1:]
    try:
        timed_out_idx = header.index("timed_out")
    except ValueError:
        return len(body), 0
    keep = [r for r in body if r[timed_out_idx] == "0"]
    dropped = len(body) - len(keep)
    if dropped == 0:
        return len(keep), 0
    with open(path, "w", newline="") as fout:
        wtr = csv.writer(fout, lineterminator="\n")
        wtr.writerow(header)
        wtr.writerows(keep)
    return len(keep), dropped


def load_attractor_index(path):
    """Map value_set_hash -> attractor_id from analysis/attractors.csv."""
    if not path.exists():
        return {}
    out = {}
    with open(path) as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            out[row["value_set_hash"]] = int(row["attractor_id"])
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--trials", type=int, default=200)
    p.add_argument("--m-count", type=int, default=80,
                   help="Number of log-stepped m's in [100, 1500].")
    p.add_argument("--m-lo", type=int, default=100)
    p.add_argument("--m-hi", type=int, default=1500)
    p.add_argument("--sigma", type=float, default=0.71)
    p.add_argument("--rng-seed", type=int, default=42)
    # The cap flags are no-ops post u16-fix; keep parsing them so older invocations
    # don't break, but the binary's `basin-scan` ignores them and warns once.
    p.add_argument("--cap-multiplier", type=int, default=5,
                   help="(deprecated) ignored — basin-scan now runs uncapped.")
    p.add_argument("--cap-floor-c-m-sq", type=int, default=100,
                   help="(deprecated) ignored — basin-scan now runs uncapped.")
    p.add_argument("--threads", type=int, default=0,
                   help="Worker threads (0 = rayon default).")
    p.add_argument("--skip-binary", action="store_true",
                   help="Reuse existing raw CSV instead of re-running the scan.")
    p.add_argument("--no-resume", dest="resume", action="store_false",
                   help="Overwrite the raw CSV instead of resuming.")
    p.set_defaults(resume=True)
    args = p.parse_args()

    binary = find_binary()
    log_ms = log_step_ms(args.m_lo, args.m_hi, args.m_count)
    primes = fixed_point_primes(FIXED_POINTS_CSV)
    combined = sorted(set(log_ms) | set(primes))
    m_list = ",".join(str(m) for m in combined)
    print(f"basin scan: {len(combined)} m's × {args.trials} trials = "
          f"{len(combined) * args.trials} total")
    print(f"  log-stepped: {log_ms}")
    print(f"  fixed-point primes: {primes}")

    if not args.skip_binary:
        if args.resume and RAW_OUTPUT.exists():
            kept, dropped = drop_timeouts(RAW_OUTPUT)
            print(f"resume: kept {kept} successful rows, dropped {dropped} timeouts "
                  f"(they will be retried with the new cap-floor)")
        cmd = [
            str(binary),
            "--threads", str(args.threads),
            "--progress-interval", "0",
            "basin-scan",
            "--m-list", m_list,
            "--trials", str(args.trials),
            "--sigma", str(args.sigma),
            "--rng-seed", str(args.rng_seed),
            "--output", str(RAW_OUTPUT),
        ]
        if args.resume:
            cmd.append("--resume")
        print("running:", " ".join(cmd))
        proc = subprocess.run(cmd, cwd=ROOT)
        if proc.returncode != 0:
            sys.exit(f"basin-scan failed with code {proc.returncode}")

    # Post-process: add attractor_id by joining on value_set_hash.
    if not RAW_OUTPUT.exists():
        sys.exit(f"missing {RAW_OUTPUT}; rerun without --skip-binary")
    attractor_index = load_attractor_index(ATTRACTORS_CSV)
    print(f"attractors.csv: {len(attractor_index)} known attractors")

    with open(RAW_OUTPUT) as fin, open(FINAL_OUTPUT, "w", newline="") as fout:
        rdr = csv.DictReader(fin)
        out_cols = [
            "m", "trial_idx", "rng_seed", "timed_out",
            "attractor_id", "value_set_hash",
            "repeat_after", "max_value", "cycle_length",
            "cycle_min", "cycle_max", "distinct_tail_values",
        ]
        wtr = csv.DictWriter(fout, fieldnames=out_cols)
        wtr.writeheader()
        seen_unknown = set()
        for row in rdr:
            vs_str = row["value_set"]
            vsh = value_set_hash(vs_str)
            aid = attractor_index.get(vsh)
            if vs_str and aid is None and vsh not in seen_unknown:
                seen_unknown.add(vsh)
            wtr.writerow({
                "m": row["m"],
                "trial_idx": row["trial_idx"],
                "rng_seed": row["rng_seed"],
                "timed_out": row["timed_out"],
                "attractor_id": "" if aid is None else aid,
                "value_set_hash": vsh,
                "repeat_after": row["repeat_after"],
                "max_value": row["max_value"],
                "cycle_length": row["cycle_length"],
                "cycle_min": row["cycle_min"],
                "cycle_max": row["cycle_max"],
                "distinct_tail_values": row["distinct_tail_values"],
            })
    print(f"wrote {FINAL_OUTPUT}")
    if seen_unknown:
        print(f"  {len(seen_unknown)} value-set hashes have no match in attractors.csv "
              f"(novel attractors discovered by random seeds)")


if __name__ == "__main__":
    main()

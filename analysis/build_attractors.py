"""Build the attractor catalog from results_new*.csv.

The natural attractor unit turned out to be the **value-set** (the set of distinct
values the cycle visits), not the multiset (value->count). Across all 1299 resolved
m's every multiset is unique because cycle lengths differ — the proportions of each
value rebalance with the period — but 290 distinct value-sets cover all 1299 m's,
with the largest cluster at 196 members. So the catalog clusters by value-set.

Outputs:
- `analysis/attractors.csv`: one row per value-set cluster. Lists the value-set hash,
  cluster size, distinct-value count, cycle-min, cycle-max, the smallest m as
  representative, and the full member list. `multiset_variant_count` reports how
  many distinct multisets exist within the cluster (= cluster size when cycle
  lengths all differ, fewer when some m's share both value-set and cycle length).
- `analysis/cycle_signatures/<m>.csv`: per-m value->count signature. One file per
  resolved m so any member is inspectable. The ordered period is never
  materialised — periods of 10^7+ terms exist at large m.

Idempotent: existing per-m signature files are reused. Re-runs are cheap if no
new m's were resolved.
"""

import csv
import hashlib
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANALYSIS = ROOT / "analysis"
SIG_DIR = ANALYSIS / "cycle_signatures"
ATTRACTORS_CSV = ANALYSIS / "attractors.csv"
INPUT_CSVS = [ROOT / "results_new.csv", ROOT / "results_new_4.csv"]

BINARY = ROOT / "target" / "release" / ("divisor_series.exe" if sys.platform == "win32" else "divisor_series")
BINARY_ARGS = [str(BINARY),
               "--progress-interval", "0",
               "--threads", "1",
               "--max-steps", "100000000000"]

PARALLEL = 8


def parse_results():
    """Yield (m, cycle_min, cycle_max, distinct) for every resolved m, deduped across input CSVs."""
    seen_m = set()
    for path in INPUT_CSVS:
        if not path.exists():
            print(f"warn: {path} missing, skipping", file=sys.stderr)
            continue
        with path.open() as f:
            r = csv.reader(f)
            next(r)
            for row in r:
                if not row:
                    continue
                cells = [c.strip() for c in row]
                if cells[1] == "None":
                    continue
                m = int(cells[0])
                if m in seen_m:
                    continue
                seen_m.add(m)
                cmax = int(cells[5])
                cmin = int(cells[6])
                dv = int(cells[7])
                yield m, cmin, cmax, dv


def hashes(path):
    """Return (multiset_hash, value_set_hash, distinct, cmin, cmax) for a signature CSV.
    Hashes are sha256 hex (16-char prefix).
    """
    multiset_h = hashlib.sha256()
    valueset_h = hashlib.sha256()
    values = []
    with open(path) as f:
        next(f)  # skip header
        for line in f:
            line = line.strip()
            if not line:
                continue
            v_str, c_str = line.split(",")
            v = int(v_str)
            values.append(v)
            multiset_h.update(line.encode())
            multiset_h.update(b"\n")
            valueset_h.update(v_str.encode())
            valueset_h.update(b"\n")
    return (multiset_h.hexdigest()[:16],
            valueset_h.hexdigest()[:16],
            len(values),
            min(values),
            max(values))


def dump_one(m, output_path):
    if output_path.exists() and output_path.stat().st_size > 0:
        return  # idempotent reuse
    cmd = BINARY_ARGS + ["dump-signature", "--m", str(m), "--output", str(output_path)]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"dump-signature m={m} failed: {proc.stderr}")


def main():
    SIG_DIR.mkdir(parents=True, exist_ok=True)

    if not BINARY.exists():
        print("building release binary first...")
        subprocess.run(["cargo", "build", "--release", "--quiet"], cwd=ROOT, check=True)

    rows = list(parse_results())
    rows.sort(key=lambda r: r[0])
    print(f"resolved m's: {len(rows)} (m_min={rows[0][0]}, m_max={rows[-1][0]})")

    # Phase 1: dump every m's signature (idempotent — skip existing).
    todo = [(m, SIG_DIR / f"{m}.csv") for (m, _, _, _) in rows]
    pending = [(m, p) for (m, p) in todo if not (p.exists() and p.stat().st_size > 0)]
    print(f"signatures to dump: {len(pending)} new + {len(todo) - len(pending)} cached "
          f"(parallel={PARALLEL})")

    if pending:
        failed = []
        with ThreadPoolExecutor(max_workers=PARALLEL) as pool:
            futs = {pool.submit(dump_one, m, p): m for (m, p) in pending}
            done = 0
            for fut in as_completed(futs):
                m = futs[fut]
                try:
                    fut.result()
                except Exception as e:
                    failed.append((m, str(e)))
                    print(f"  ! m={m} failed: {e}", file=sys.stderr)
                done += 1
                if done % 50 == 0 or done == len(pending):
                    print(f"  dump progress: {done}/{len(pending)}")
        if failed:
            sys.exit(f"aborting: {len(failed)} dumps failed")

    # Phase 2: hash each m's signature.
    print("hashing signatures...")
    by_m = {}  # m -> (multiset_hash, value_set_hash, distinct, cmin, cmax)
    for m, _, _, _ in rows:
        path = SIG_DIR / f"{m}.csv"
        by_m[m] = hashes(path)

    # Phase 3: cluster.
    multiset_clusters = {}  # multiset_hash -> [m's]
    valueset_clusters = {}  # value_set_hash -> [m's]
    for m, (mh, vh, _, _, _) in by_m.items():
        multiset_clusters.setdefault(mh, []).append(m)
        valueset_clusters.setdefault(vh, []).append(m)
    for k in multiset_clusters:
        multiset_clusters[k].sort()
    for k in valueset_clusters:
        valueset_clusters[k].sort()

    print(f"  multiset clusters:  {len(multiset_clusters):>4} (singletons: "
          f"{sum(1 for v in multiset_clusters.values() if len(v) == 1)})")
    print(f"  value-set clusters: {len(valueset_clusters):>4} (singletons: "
          f"{sum(1 for v in valueset_clusters.values() if len(v) == 1)})")

    # Phase 4: write attractors.csv (value-set clusters; multiset clustering was
    # all singletons across this dataset and adds no information).
    sorted_vs = sorted(valueset_clusters.items(), key=lambda kv: kv[1][0])
    print(f"writing {ATTRACTORS_CSV}")
    with ATTRACTORS_CSV.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["attractor_id", "size", "distinct_count", "cycle_min", "cycle_max",
                    "value_set_hash", "multiset_variant_count",
                    "representative_m", "member_m_list"])
        for vid, (vh, members) in enumerate(sorted_vs):
            rep = members[0]
            _, _, dv, cmin, cmax = by_m[rep]
            variants = len({by_m[m][0] for m in members})
            w.writerow([
                vid, len(members), dv, cmin, cmax, vh,
                variants, rep,
                " ".join(str(m) for m in members),
            ])

    print(f"done: {len(sorted_vs)} attractors (value-set clusters); "
          f"multiset uniqueness: {len(multiset_clusters)} distinct multisets / "
          f"{sum(len(v) for v in valueset_clusters.values())} m's")


if __name__ == "__main__":
    main()

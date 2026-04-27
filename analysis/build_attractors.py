"""Build the attractor catalog from results_new*.csv.

Two clusterings, both true (verified pairwise by construction):

- **Multiset clusters** (`analysis/attractors.csv`): m's whose cycle has an identical
  value->count multiset. signature_hash is sha256 of the sorted "value,count\\n" lines.
- **Value-set clusters** (`analysis/value_set_clusters.csv`): m's whose cycle visits
  the same SET of values (but possibly with different frequencies — the cycle
  lengths can differ). value_set_hash is sha256 of the sorted "value\\n" lines.
  Roll-up of the multiset clusters: each value-set cluster contains 1+ multiset
  variants. The (cycle_min, cycle_max, distinct) triple is a value-set proxy in
  practice but not provably so — see the NOTES.md research log.

Per-m signature files are written to `analysis/cycle_signatures/<m>.csv` (one per
resolved m, ~few MB total). The ordered period is never materialised — periods
of 10^7+ ordered terms exist at large m.

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
VALUE_SET_CSV = ANALYSIS / "value_set_clusters.csv"
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

    # Map value_set_hash -> stable id (sorted by representative m).
    sorted_vs = sorted(valueset_clusters.items(), key=lambda kv: kv[1][0])
    vs_id_of = {h: i for i, (h, _) in enumerate(sorted_vs)}

    # Phase 4: write attractors.csv (multiset clusters).
    sorted_ms = sorted(multiset_clusters.items(), key=lambda kv: kv[1][0])
    print(f"writing {ATTRACTORS_CSV}")
    with ATTRACTORS_CSV.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["signature_id", "distinct_count", "cycle_min", "cycle_max",
                    "signature_hash", "value_set_id", "value_set_hash",
                    "size", "representative_m", "member_m_list"])
        for sid, (mh, members) in enumerate(sorted_ms):
            rep = members[0]
            _, vh, dv, cmin, cmax = by_m[rep]
            w.writerow([
                sid, dv, cmin, cmax, mh,
                vs_id_of[vh], vh,
                len(members), rep,
                " ".join(str(m) for m in members),
            ])

    # Phase 5: write value_set_clusters.csv (value-set clusters, with multiset variant
    # counts as roll-up).
    print(f"writing {VALUE_SET_CSV}")
    with VALUE_SET_CSV.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["value_set_id", "distinct_count", "cycle_min", "cycle_max",
                    "value_set_hash", "multiset_variant_count", "total_size",
                    "representative_m", "member_m_list"])
        for vh, members in sorted_vs:
            vid = vs_id_of[vh]
            rep = members[0]
            _, _, dv, cmin, cmax = by_m[rep]
            variants = len({by_m[m][0] for m in members})
            w.writerow([
                vid, dv, cmin, cmax, vh,
                variants, len(members), rep,
                " ".join(str(m) for m in members),
            ])

    print(f"done: {len(sorted_ms)} multiset clusters, {len(sorted_vs)} value-set clusters")


if __name__ == "__main__":
    main()

"""Generate OEIS b-files from results_new*.csv.

Each b-file is plain text, one `n value` per line, strictly increasing n.
Output goes to analysis/oeis_bfiles/ with one file per derived sequence.

Sequences emitted:
- b_repeat_after.txt:        repeat_after(m)
- b_max_value.txt:           max_value(m)
- b_cycle_max.txt:           cycle_max(m)
- b_cycle_min.txt:           cycle_min(m)
- b_distinct_tail_values.txt: distinct_tail_values(m)
- b_cycle_max_minus_min.txt: cycle_max(m) - cycle_min(m)
- b_cycle_length_nontrivial.txt: cycle_length(m), restricted to m where
                                  cycle_length != m + 1 (the trivial majority)

Per ROADMAP §7: cycle_length(m) is uninteresting for the cycle_length = m+1 cluster
(over half of all rows), so we publish only the non-trivial subseries.

None rows are skipped — OEIS sequences must be gap-free in n. We emit the longest
gap-free prefix from m=1.
"""

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANALYSIS = ROOT / "analysis"
BFILES = ANALYSIS / "oeis_bfiles"
INPUT_CSVS = [ROOT / "results_new.csv", ROOT / "results_new_4.csv"]


def load_rows():
    """m -> dict of fields, only resolved (non-None) rows."""
    rows = {}
    for path in INPUT_CSVS:
        if not path.exists():
            continue
        with path.open() as f:
            r = csv.reader(f)
            next(r)
            for row in r:
                cells = [c.strip() for c in row]
                if cells[1] == "None":
                    continue
                m = int(cells[0])
                rows[m] = {
                    "repeat_after": int(cells[1]),
                    "max_value": int(cells[2]),
                    "most_common_tail_value": int(cells[3]),
                    "cycle_length": int(cells[4]),
                    "cycle_max": int(cells[5]),
                    "cycle_min": int(cells[6]),
                    "distinct_tail_values": int(cells[7]),
                }
    return rows


def write_bfile(name, pairs):
    """pairs: iterable of (n, value). Writes ASCII b-file at BFILES/<name>."""
    path = BFILES / name
    with path.open("w") as f:
        for n, v in pairs:
            f.write(f"{n} {v}\n")
    return path


def gapfree_prefix(rows, key):
    """Yield (m, rows[m][key]) for m=1,2,... while m is present, stop on first gap."""
    m = 1
    while m in rows:
        yield m, rows[m][key]
        m += 1


def main():
    BFILES.mkdir(parents=True, exist_ok=True)
    rows = load_rows()
    if not rows:
        raise SystemExit("no rows loaded")
    max_m_resolved = max(rows.keys())
    print(f"loaded {len(rows)} resolved rows; max m = {max_m_resolved}")

    # Identify the gap-free prefix length so we know how far each b-file goes.
    prefix_end = 0
    m = 1
    while m in rows:
        prefix_end = m
        m += 1
    gaps = sorted(set(range(1, max_m_resolved + 1)) - set(rows.keys()))
    print(f"gap-free prefix: m=1..{prefix_end}; gaps after that at: {gaps[:10]}{'...' if len(gaps) > 10 else ''}")

    targets = [
        ("b_repeat_after.txt", "repeat_after"),
        ("b_max_value.txt", "max_value"),
        ("b_cycle_max.txt", "cycle_max"),
        ("b_cycle_min.txt", "cycle_min"),
        ("b_distinct_tail_values.txt", "distinct_tail_values"),
    ]
    for fname, key in targets:
        p = write_bfile(fname, gapfree_prefix(rows, key))
        print(f"  wrote {p.name} (n=1..{prefix_end})")

    # cycle_max - cycle_min
    pairs = [(m, rows[m]["cycle_max"] - rows[m]["cycle_min"])
             for m in range(1, prefix_end + 1)]
    p = write_bfile("b_cycle_max_minus_min.txt", pairs)
    print(f"  wrote {p.name} (n=1..{prefix_end})")

    # Non-trivial cycle_length: m where cycle_length != m + 1. OEIS requires
    # gap-free n, so we re-index: n -> i-th m in increasing order with cycle_length != m+1,
    # and the value is cycle_length(m). The original m is recoverable via a sidecar but
    # OEIS submissions usually want a clean n. We instead emit (m, cycle_length(m))
    # over the gap-free prefix and let the OEIS submitter pick the encoding.
    nontriv = [(m, rows[m]["cycle_length"])
               for m in range(1, prefix_end + 1)
               if rows[m]["cycle_length"] != m + 1]
    p = write_bfile("b_cycle_length_nontrivial.txt", nontriv)
    print(f"  wrote {p.name} ({len(nontriv)} entries; original m preserved as n)")


if __name__ == "__main__":
    main()

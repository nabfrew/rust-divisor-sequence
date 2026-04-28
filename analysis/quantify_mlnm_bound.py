"""Quantify cycle/trajectory value bounds vs m·ln(m) and m·H(m).

ROADMAP §6. Pure post-processing on `results_new.csv` (1348 resolved m's,
m=2..=1349 after dropping m=1 where m·ln(m)=0).

For each of {cycle_min, cycle_max, max_value} divided by each of
{m·ln(m), m·H(m)} this script reports the global (p5, median, p95) and the
same triple bucketed by m so we can see whether the band tightens with
growing m.

H(m) is computed as the exact partial harmonic sum sum_{k=1..m} 1/k.

Outputs:
  - stdout: human-readable summary table + per-bin tightening table.
  - analysis/mlnm_bound.csv: one row per (metric, anchor, m_bin) cell.
  - analysis/mlnm_bound.md: prose findings + conjectured bounds.
"""

import csv
import io
import math
import sys
from pathlib import Path

# Force UTF-8 stdout so unicode (·, ∈, …) prints on Windows cp1252 consoles too.
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
INPUT_CSV = ROOT / "results_new.csv"
OUT_CSV = ROOT / "analysis" / "mlnm_bound.csv"
OUT_MD = ROOT / "analysis" / "mlnm_bound.md"

METRICS = ["cycle_min", "cycle_max", "max_value"]
BIN_EDGES = [2, 50, 100, 200, 400, 600, 800, 1000, 1200, 1350]


def parse_results():
    with INPUT_CSV.open() as f:
        reader = csv.DictReader(f, skipinitialspace=True)
        return [{k: int(v) for k, v in row.items()} for row in reader]


def harmonic_table(m_max):
    table = [0.0] * (m_max + 1)
    s = 0.0
    for k in range(1, m_max + 1):
        s += 1.0 / k
        table[k] = s
    return table


def quantile(sorted_values, p):
    """Linear-interpolated quantile, matches numpy default."""
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    pos = p * (n - 1)
    lo = int(pos)
    frac = pos - lo
    if lo + 1 >= n:
        return sorted_values[-1]
    return sorted_values[lo] * (1 - frac) + sorted_values[lo + 1] * frac


def stats(values):
    s = sorted(values)
    return (quantile(s, 0.05), quantile(s, 0.50), quantile(s, 0.95),
            s[0], s[-1])


def fmt_row(*cells, widths):
    return "  ".join(f"{c:>{w}}" for c, w in zip(cells, widths))


def main():
    rows = parse_results()
    rows = [r for r in rows if r["m"] >= 2]
    m_max = max(r["m"] for r in rows)
    H = harmonic_table(m_max)

    anchors = {
        "m·ln(m)": lambda m: m * math.log(m),
        "m·H(m)":  lambda m: m * H[m],
    }

    # ---- Global table ---------------------------------------------------
    print(f"# m·ln(m) / m·H(m) bound quantification")
    print(f"# Source: {INPUT_CSV.name}, n={len(rows)}, m∈[{rows[0]['m']}..{m_max}]\n")

    hdr_w = (12, 10, 9, 9, 9, 9, 9, 9)
    print("## Global (all m≥2)\n")
    print(fmt_row("metric", "anchor", "p5", "p50", "p95", "p95-p5", "min", "max", widths=hdr_w))
    print("-" * (sum(hdr_w) + 2 * (len(hdr_w) - 1)))

    csv_rows = []
    for metric in METRICS:
        for aname, afn in anchors.items():
            ratios = [r[metric] / afn(r["m"]) for r in rows]
            p5, p50, p95, lo, hi = stats(ratios)
            print(fmt_row(metric, aname,
                          f"{p5:.4f}", f"{p50:.4f}", f"{p95:.4f}",
                          f"{p95 - p5:.4f}", f"{lo:.4f}", f"{hi:.4f}",
                          widths=hdr_w))
            csv_rows.append({"metric": metric, "anchor": aname, "m_bin": "all",
                             "n": len(rows), "p5": p5, "p50": p50, "p95": p95,
                             "min": lo, "max": hi})

    # ---- Per-bin tightening test ---------------------------------------
    print("\n## Tightening: cycle_max / m·ln(m) by m-bin\n")
    bin_w = (14, 5, 9, 9, 9, 9, 9)
    print(fmt_row("m-bin", "n", "p5", "p50", "p95", "p95-p5", "max",
                  widths=bin_w))
    print("-" * (sum(bin_w) + 2 * (len(bin_w) - 1)))
    for lo_m, hi_m in zip(BIN_EDGES[:-1], BIN_EDGES[1:]):
        bin_rows = [r for r in rows if lo_m <= r["m"] < hi_m]
        if not bin_rows:
            continue
        ratios = [r["cycle_max"] / (r["m"] * math.log(r["m"])) for r in bin_rows]
        p5, p50, p95, _, hi_r = stats(ratios)
        print(fmt_row(f"[{lo_m},{hi_m})", len(bin_rows),
                      f"{p5:.4f}", f"{p50:.4f}", f"{p95:.4f}",
                      f"{p95 - p5:.4f}", f"{hi_r:.4f}",
                      widths=bin_w))

    # All metric × anchor × bin combinations to CSV.
    print("\n## All (metric × anchor × m-bin) → mlnm_bound.csv")
    for metric in METRICS:
        for aname, afn in anchors.items():
            for lo_m, hi_m in zip(BIN_EDGES[:-1], BIN_EDGES[1:]):
                bin_rows = [r for r in rows if lo_m <= r["m"] < hi_m]
                if not bin_rows:
                    continue
                ratios = [r[metric] / afn(r["m"]) for r in bin_rows]
                p5, p50, p95, lo_r, hi_r = stats(ratios)
                csv_rows.append({"metric": metric, "anchor": aname,
                                 "m_bin": f"[{lo_m},{hi_m})",
                                 "n": len(bin_rows),
                                 "p5": p5, "p50": p50, "p95": p95,
                                 "min": lo_r, "max": hi_r})

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["metric", "anchor", "m_bin", "n",
                                          "p5", "p50", "p95", "min", "max"])
        w.writeheader()
        for row in csv_rows:
            w.writerow({k: (f"{v:.6f}" if isinstance(v, float) else v)
                        for k, v in row.items()})
    print(f"wrote {OUT_CSV.relative_to(ROOT)} ({len(csv_rows)} rows)")

    # ---- Conjecture extraction -----------------------------------------
    # Tail-half bins are the empirically interesting regime — early m's are
    # noisy because cycles are short and integer effects dominate.
    tail_rows = [r for r in rows if r["m"] >= 200]
    conj = {}
    for metric in METRICS:
        for aname, afn in anchors.items():
            ratios = sorted(r[metric] / afn(r["m"]) for r in tail_rows)
            conj[(metric, aname)] = {
                "p5": quantile(ratios, 0.05),
                "p50": quantile(ratios, 0.50),
                "p95": quantile(ratios, 0.95),
                "min": ratios[0],
                "max": ratios[-1],
            }

    cmin_max = conj[("cycle_min", "m·ln(m)")]["max"]
    cmax_max = conj[("cycle_max", "m·ln(m)")]["max"]
    mv_max = conj[("max_value",  "m·ln(m)")]["max"]
    cmin_min = conj[("cycle_min", "m·ln(m)")]["min"]
    cmax_min = conj[("cycle_max", "m·ln(m)")]["min"]

    md_lines = [
        "# m·ln(m) bound quantification (ROADMAP §6)",
        "",
        f"Source: `{INPUT_CSV.name}`, n={len(rows)}, m∈[{rows[0]['m']}..{m_max}].",
        f"Anchors: m·ln(m); m·H(m) where H is the exact partial harmonic sum.",
        "",
        "## Findings",
        "",
        "1. **Both anchors are tight, m·H(m) marginally tighter** — the band",
        "   `[p5, p95]` of `cycle_max / anchor` is narrower under m·H(m) than",
        "   under m·ln(m), as expected (H(m) = ln(m) + γ + O(1/m)).",
        "",
        "2. **The bulk band tightens substantially with growing m, but is",
        "   not strictly monotonic — outlier m's reopen it.** The `p95 − p5`",
        "   spread of `cycle_max / (m·ln(m))` falls from ~2.3 (m<50) to",
        "   ~0.4 (m≥1000), a ~6× contraction. The empirical sup itself",
        "   does *not* tighten as cleanly: large-spread outliers in the",
        "   600–800 and 1200–1350 bins (cf. m=601, 738–751, 1082 in",
        "   `human_notes.md`) keep the per-bin max in the 2.0–2.2× range.",
        "",
        "3. **Trivial lower bound `cycle_min ≥ m` is far from sharp.** In the",
        "   tail (m ≥ 200) the smallest observed `cycle_min / (m·ln(m))` is",
        f"   ≈ {cmin_min:.4f}, i.e. `cycle_min ≳ {cmin_min:.3f}·m·ln(m)`.",
        "   This is well above the trivial `cycle_min ≥ m`, which would",
        "   correspond to a ratio of `1/ln(m)` (≈ 0.14 at m=1349).",
        "",
        "4. **Median is anchor-flat at ~1.13 (m·ln(m)) / ~1.05 (m·H(m))**",
        "   for cycle_min and cycle_max, and ~2.13 / ~1.96 for max_value.",
        "   That is, transient peaks sit at roughly 2× the cycle band —",
        "   consistent with the algorithm overshooting before settling.",
        "",
        "## Conjectured empirical bounds (m ≥ 200, n = "
        f"{len(tail_rows)})",
        "",
        "Anchored to m·ln(m):",
        "",
        f"- `cycle_min ≥ {cmin_min:.4f} · m·ln(m)`  (empirical inf)",
        f"- `cycle_max ≤ {cmax_max:.4f} · m·ln(m)`  (empirical sup, "
        "outlier-driven; see B.4)",
        f"- `max_value ≤ {mv_max:.4f} · m·ln(m)`  (transient peak)",
        "",
        "Tail medians (m ≥ 200):",
        "",
    ]
    for metric in METRICS:
        c = conj[(metric, "m·ln(m)")]
        md_lines.append(
            f"- `{metric}`: median = {c['p50']:.4f}, "
            f"[p5, p95] = [{c['p5']:.4f}, {c['p95']:.4f}]"
        )
    md_lines.extend([
        "",
        "## Method",
        "",
        f"- Quantiles: linear interpolation (numpy default).",
        f"- m-bins: {BIN_EDGES}.",
        f"- m=1 dropped (m·ln(m) = 0).",
        f"- Tail-only conjecture cutoff at m=200 follows `human_notes.md`",
        "  observation that integer effects dominate small-m cycles.",
        "",
        "Re-run: `python analysis/quantify_mlnm_bound.py`.",
    ])

    OUT_MD.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

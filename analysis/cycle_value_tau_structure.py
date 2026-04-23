"""Analyse the value/τ structure of every resolved cycle.

For each m with `analysis/cycle_signatures/<m>.csv`, compute:

- Conservation residual `mean_v - m * mean_tau`.
  Must be ~0 by the dynamical conservation law derived in `explore.ipynb` §7 (§B.9).
- Spearman correlation ρ(v, τ(v)) over the *distinct* cycle values
  (unweighted), and the count-weighted analogue.
- Gap structure: sort distinct values v_1<…<v_d, define
  gap_i = v_{i+1}-v_i and dtau_i = τ(v_i)-τ(v_{i+1}). Pearson ρ(gap, dtau).
  Sign convention: positive ρ means "bigger gaps where τ falls more steeply".
- mean_tau / ln(m): test of the human-notes mean-of-cycle ≈ m·ln(m)
  invariant (which, combined with conservation, becomes mean τ ≈ ln(m)).

Joins to results_new*.csv to expose per-m metadata
(cycle_length, cluster_size, etc.) and to bucket by:

- "well-behaved" = distinct ∈ [3,10] AND (cycle_max-cycle_min) ≤ 50
- "resonance" = cycle_length mod m ∈ {0,1,2,3, m-1, m-2, m-3} -- catches
  k·m and k·m±small
- "fixed point" = cycle_length == 1
- "wide-band outlier" = (cycle_max-cycle_min) > 100 OR distinct > 50
- "runaway" = cycle_length > 10*m

Outputs:
- analysis/cycle_value_tau_structure.csv -- one row per m
- analysis/cycle_value_tau_structure.md  -- bucketed summary tables
"""

import csv
import math
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent
ANALYSIS = ROOT / "analysis"
SIG_DIR = ANALYSIS / "cycle_signatures"
INPUT_CSVS = [ROOT / "results_new.csv", ROOT / "results_new_4.csv"]
OUT_CSV = ANALYSIS / "cycle_value_tau_structure.csv"
OUT_MD = ANALYSIS / "cycle_value_tau_structure.md"


def build_tau(n):
    """τ table via smallest-prime-factor sieve. tau[i] = number of divisors of i, i<n.
    Mirrors src/lib.rs::build_fac_table for parity."""
    tau = [0] * n
    if n > 1:
        tau[1] = 1
    spf = [0] * n
    for i in range(2, n):
        if spf[i] == 0:
            for j in range(i, n, i):
                if spf[j] == 0:
                    spf[j] = i
    cnt = [0] * n
    for i in range(2, n):
        p = spf[i]
        j = i // p
        if spf[j] == p:
            cnt[i] = cnt[j] + 1
            tau[i] = tau[j] * (cnt[i] + 1) // (cnt[j] + 1)
        else:
            cnt[i] = 1
            tau[i] = tau[j] * 2
    return tau


def spearman(xs, ys):
    """Spearman rank correlation. Returns NaN for n<2 or no variance."""
    n = len(xs)
    if n < 2:
        return float("nan")
    rx = _ranks(xs)
    ry = _ranks(ys)
    return pearson(rx, ry)


def _ranks(vs):
    indexed = sorted((v, i) for i, v in enumerate(vs))
    out = [0.0] * len(vs)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][0] == indexed[i][0]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            out[indexed[k][1]] = avg
        i = j + 1
    return out


def pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return float("nan")
    mx = sum(xs) / n
    my = sum(ys) / n
    sx = sum((x - mx) ** 2 for x in xs)
    sy = sum((y - my) ** 2 for y in ys)
    if sx == 0 or sy == 0:
        return float("nan")
    sxy = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    return sxy / math.sqrt(sx * sy)


def load_meta():
    """m -> (repeat_after, cycle_length, cycle_min, cycle_max, distinct)."""
    meta = {}
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
                if m in meta:
                    continue
                meta[m] = (int(cells[1]), int(cells[4]), int(cells[6]),
                           int(cells[5]), int(cells[7]))
    return meta


def load_signature(path):
    """sorted [(v, count)] from analysis/cycle_signatures/<m>.csv."""
    out = []
    with path.open() as f:
        next(f)
        for line in f:
            line = line.strip()
            if not line:
                continue
            v, c = line.split(",")
            out.append((int(v), int(c)))
    out.sort()
    return out


def analyse_m(m, sig, tau_tbl, meta_row):
    """Compute the per-m row. Returns dict of named columns."""
    rep, csv_cycle_length, csv_cmin, csv_cmax, csv_distinct = meta_row
    vs = [v for v, _ in sig]
    cs = [c for _, c in sig]
    taus = [tau_tbl[v] for v in vs]
    total_count = sum(cs)
    # Signature is authoritative — re-dumped with the current binary. The CSV's
    # cycle_length is from older runs and disagrees on a small set of m's where
    # an earlier `find_cycle_start` bug overstated the period (e.g. m=1103 is
    # length 1 — fixed point at 8824 — but the CSV says 1005).
    cycle_length = total_count
    cmin = vs[0] if vs else csv_cmin
    cmax = vs[-1] if vs else csv_cmax
    distinct = len(vs)
    csv_mismatch = (csv_cycle_length != cycle_length
                    or csv_cmin != cmin or csv_cmax != cmax
                    or csv_distinct != distinct)

    # Count-weighted mean v and τ.
    mean_v_w = sum(v * c for v, c in zip(vs, cs)) / total_count
    mean_tau_w = sum(t * c for t, c in zip(taus, cs)) / total_count

    # Conservation: mean_v = m * mean_tau (exact integer identity if you keep
    # numerators); residual must be 0.
    cons_residual = mean_v_w - m * mean_tau_w

    # Distinct-value (unweighted) Spearman ρ between v and τ.
    rho_distinct = spearman(vs, taus) if len(vs) >= 2 else float("nan")

    # Count-weighted Spearman: emulate by replicating ranks. Cheap given counts
    # are tiny multisets aside from huge cycles -- we cap weighting via stable
    # rank averaging on the distinct values, weighted by count.
    rho_weighted = _weighted_spearman(vs, taus, cs)

    # Gap/Δτ relationship.
    if len(vs) >= 2:
        gaps = [vs[i + 1] - vs[i] for i in range(len(vs) - 1)]
        dtaus = [taus[i] - taus[i + 1] for i in range(len(vs) - 1)]
        rho_gap_dtau = pearson(gaps, dtaus)
    else:
        rho_gap_dtau = float("nan")

    # mean_tau / ln(m): the key normaliser. ln(m) is the global τ-mean anchor.
    if m >= 2:
        mean_tau_norm = mean_tau_w / math.log(m)
    else:
        mean_tau_norm = float("nan")

    # Bucket flags.
    well_behaved = (3 <= distinct <= 10) and (cmax - cmin <= 50) and cycle_length > 1
    fixed_point = cycle_length == 1
    wide_band = (cmax - cmin > 100) or distinct > 50
    runaway = cycle_length > 10 * m
    if m == 0:
        cl_mod_m = 0
    else:
        cl_mod_m = cycle_length % m
    near_resonance = cl_mod_m <= 3 or cl_mod_m >= m - 3

    return {
        "m": m,
        "cycle_length": cycle_length,
        "cycle_min": cmin,
        "cycle_max": cmax,
        "distinct": distinct,
        "csv_mismatch": int(csv_mismatch),
        "mean_v": round(mean_v_w, 6),
        "mean_tau": round(mean_tau_w, 6),
        "cons_residual": round(cons_residual, 9),
        "rho_distinct": round(rho_distinct, 4) if not math.isnan(rho_distinct) else "",
        "rho_weighted": round(rho_weighted, 4) if not math.isnan(rho_weighted) else "",
        "rho_gap_dtau": round(rho_gap_dtau, 4) if not math.isnan(rho_gap_dtau) else "",
        "mean_tau_over_lnm": round(mean_tau_norm, 4) if not math.isnan(mean_tau_norm) else "",
        "well_behaved": int(well_behaved),
        "fixed_point": int(fixed_point),
        "wide_band": int(wide_band),
        "runaway": int(runaway),
        "near_resonance": int(near_resonance),
        "cl_mod_m": cl_mod_m,
    }


def _weighted_spearman(vs, taus, cs):
    if len(vs) < 2:
        return float("nan")
    # Build replicated samples up to a cap so giant cycles don't blow memory.
    # We reduce counts by gcd to keep proportions exact. Then if total still
    # huge we approximate via rank-corr on distinct values weighted analytically.
    g = cs[0]
    for c in cs[1:]:
        g = math.gcd(g, c)
    cs_red = [c // g for c in cs]
    if sum(cs_red) > 100_000:
        # Fall back: weighted Spearman using the count-weighted mean rank.
        rx = _ranks(vs)
        ry = _ranks(taus)
        n = sum(cs_red)
        mx = sum(rx[i] * cs_red[i] for i in range(len(vs))) / n
        my = sum(ry[i] * cs_red[i] for i in range(len(vs))) / n
        sxy = sum(cs_red[i] * (rx[i] - mx) * (ry[i] - my) for i in range(len(vs)))
        sx = sum(cs_red[i] * (rx[i] - mx) ** 2 for i in range(len(vs)))
        sy = sum(cs_red[i] * (ry[i] - my) ** 2 for i in range(len(vs)))
        if sx == 0 or sy == 0:
            return float("nan")
        return sxy / math.sqrt(sx * sy)
    xs_rep = []
    ys_rep = []
    for v, t, c in zip(vs, taus, cs_red):
        xs_rep.extend([v] * c)
        ys_rep.extend([t] * c)
    return spearman(xs_rep, ys_rep)


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    if n == 0:
        return float("nan")
    if n % 2:
        return xs[n // 2]
    return 0.5 * (xs[n // 2 - 1] + xs[n // 2])


def percentile(xs, p):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * p
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return xs[lo]
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def summarise(rows, predicate, label):
    """Return a markdown table row for the bucket."""
    sub = [r for r in rows if predicate(r)]
    n = len(sub)
    if n == 0:
        return f"| {label} | 0 | — | — | — | — | — |"
    rho_d = [float(r["rho_distinct"]) for r in sub if r["rho_distinct"] != ""]
    rho_w = [float(r["rho_weighted"]) for r in sub if r["rho_weighted"] != ""]
    rho_g = [float(r["rho_gap_dtau"]) for r in sub if r["rho_gap_dtau"] != ""]
    mt = [float(r["mean_tau_over_lnm"]) for r in sub if r["mean_tau_over_lnm"] != ""]
    res = [float(r["cons_residual"]) for r in sub]

    def fmt(xs, sig=3):
        if not xs:
            return "—"
        return f"{median(xs):.{sig}f}"

    def negfrac(xs, threshold=-0.9):
        if not xs:
            return "—"
        return f"{sum(1 for x in xs if x <= threshold) / len(xs) * 100:.1f}%"

    return (f"| {label} | {n} | {fmt(rho_d)} | {fmt(rho_w)} | "
            f"{fmt(rho_g)} | {fmt(mt)} | {negfrac(rho_d)} | "
            f"{max(abs(r) for r in res):.2e} |")


def main():
    meta = load_meta()
    print(f"meta loaded: {len(meta)} resolved m's")

    # Build τ table large enough for max observed cycle_max.
    max_cmax = max(cmax for _, _, _, cmax, _ in meta.values())
    tau_n = max(max_cmax + 1, 50_000)
    print(f"building τ sieve up to {tau_n}...")
    tau_tbl = build_tau(tau_n)

    rows = []
    skipped = []
    for m in sorted(meta.keys()):
        sig_path = SIG_DIR / f"{m}.csv"
        if not sig_path.exists():
            skipped.append(m)
            continue
        sig = load_signature(sig_path)
        rows.append(analyse_m(m, sig, tau_tbl, meta[m]))
    print(f"analysed {len(rows)} m's; skipped {len(skipped)} (no signature file)")

    mismatches = [r for r in rows if r["csv_mismatch"]]
    if mismatches:
        print(f"\n!! {len(mismatches)} m(s) where current signature disagrees with CSV "
              "(CSV likely stale from earlier binary):")
        for r in mismatches[:30]:
            print(f"   m={r['m']:>4} now: λ={r['cycle_length']} d={r['distinct']} "
                  f"range=[{r['cycle_min']},{r['cycle_max']}]")

    # Write the per-m CSV.
    cols = list(rows[0].keys())
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"wrote {OUT_CSV}")

    # Markdown summary.
    buckets = [
        ("All m", lambda r: True),
        ("Well-behaved (3≤d≤10, range≤50, λ>1)", lambda r: r["well_behaved"]),
        ("Wide-band outlier (range>100 or d>50)", lambda r: r["wide_band"]),
        ("Fixed point (λ=1)", lambda r: r["fixed_point"]),
        ("Runaway (λ > 10·m)", lambda r: r["runaway"]),
        ("Near-resonance (λ mod m ∈ ±3)", lambda r: r["near_resonance"] and not r["fixed_point"]),
        ("Off-resonance", lambda r: not r["near_resonance"] and not r["fixed_point"]),
        ("d≥10 (broader cycle)", lambda r: r["distinct"] >= 10),
    ]

    with OUT_MD.open("w", encoding="utf-8") as f:
        f.write("# Cycle value/τ structure — bucketed summary\n\n")
        f.write(f"Generated by `analysis/cycle_value_tau_structure.py` "
                f"from {len(rows)} resolved m's. "
                f"Per-m rows: `analysis/cycle_value_tau_structure.csv`.\n\n")
        f.write("Columns:\n\n")
        f.write("- **n**: m's in bucket.\n")
        f.write("- **ρ(v,τ) distinct**: median Spearman over distinct cycle values.\n")
        f.write("- **ρ(v,τ) weighted**: same, count-weighted by cycle frequency.\n")
        f.write("- **ρ(gap,Δτ)**: median Pearson — does τ fall more steeply across larger value gaps?\n")
        f.write("- **mean τ / ln m**: count-weighted mean of τ over cycle, divided by ln m. "
                "Conservation law (`explore.ipynb` §7 / §B.9) makes this equal `mean_v / (m · ln m)`.\n")
        f.write("- **% ρ_d ≤ −0.9**: fraction of bucket with strongly-negative distinct-value ρ.\n")
        f.write("- **|cons. residual| max**: largest |mean_v − m·mean_τ|. "
                "Must be 0 up to floating-point noise (it's the analytic conservation law).\n\n")
        f.write("| bucket | n | ρ(v,τ) distinct | ρ(v,τ) weighted | "
                "ρ(gap,Δτ) | mean τ / ln m | % ρ_d ≤ −0.9 | "
                "|cons. residual| max |\n")
        f.write("|---|---:|---:|---:|---:|---:|---:|---:|\n")
        for label, pred in buckets:
            f.write(summarise(rows, pred, label) + "\n")

        # Top wide-band outliers and runaways: list them so they're easy to find.
        outlier_rows = [r for r in rows if r["wide_band"]]
        runaway_rows = [r for r in rows if r["runaway"]]
        if outlier_rows:
            f.write("\n## Wide-band outliers (range > 100 or distinct > 50)\n\n")
            f.write("| m | range | distinct | λ | ρ(v,τ) distinct | mean τ / ln m |\n")
            f.write("|---:|---:|---:|---:|---:|---:|\n")
            for r in sorted(outlier_rows, key=lambda r: -(r["cycle_max"] - r["cycle_min"]))[:25]:
                f.write(f"| {r['m']} | {r['cycle_max']-r['cycle_min']} | "
                        f"{r['distinct']} | {r['cycle_length']} | "
                        f"{r['rho_distinct']} | {r['mean_tau_over_lnm']} |\n")
        if runaway_rows:
            f.write("\n## Runaway cycles (λ > 10·m)\n\n")
            f.write("| m | λ | λ/m | range | ρ(v,τ) distinct |\n")
            f.write("|---:|---:|---:|---:|---:|\n")
            for r in sorted(runaway_rows, key=lambda r: -r["cycle_length"])[:25]:
                f.write(f"| {r['m']} | {r['cycle_length']} | "
                        f"{r['cycle_length']/r['m']:.1f} | "
                        f"{r['cycle_max']-r['cycle_min']} | {r['rho_distinct']} |\n")

    print(f"wrote {OUT_MD}")


if __name__ == "__main__":
    main()

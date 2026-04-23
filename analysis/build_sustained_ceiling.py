"""Compute the sustained-ceiling locus M*(m) for m=1..M_MAX.

ROADMAP §E.1. Defined by `analysis/system_limits.md`:

    M*(m) = max{ M ∈ ℕ : M ≤ m · τ(M) }

— the largest value the window can sustain (a flat window of M's maps
to a_next = m·τ(M) ≥ M). Above M*(m) the next term is strictly
smaller; below it, the orbit can grow.

By the bounded-orbits proof (system_limits.md), τ(M) ≤ 2√M gives
M*(m) ≤ 4m² as a hard upper bound. The actual M*(m) is set by HCN
density and is much smaller — that's exactly what we measure here.

Algorithm. Inverting the inequality, M is sustainable for m iff
m ≥ ⌈M/τ(M)⌉. So if we let

    m_min(M) = ⌈M / τ(M)⌉,

then M*(m) = max{ M : m_min(M) ≤ m }, a prefix-max over m. One τ
sieve up to 4·M_MAX² then a single pass gives M*(m) for all m.

Cross-check against §C.1: every fixed-point x = m·τ(x) trivially
satisfies x ≤ m·τ(x) with equality, so x is in the candidate set
and M*(m) ≥ x. For all 8 known fixed points (m ∈ {127, 167, 211,
613, 733, 1103, 1117, 1291} with x = 8m, plus m=1 with x=1) we
confirm M*(m) ≥ x and report the slack M*(m) - x.

Outputs:
  - analysis/sustained_ceiling.csv: m, M_star, tau, m_times_tau, slack
  - analysis/sustained_ceiling.md: headline numbers, fixed-point
    cross-check, asymptotic fit for M*(m).
"""

import csv
import io
import math
import sys
from pathlib import Path

import numpy as np

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
FIXED_POINTS_CSV = ROOT / "analysis" / "fixed_points.csv"
OUT_CSV = ROOT / "analysis" / "sustained_ceiling.csv"
OUT_MD = ROOT / "analysis" / "sustained_ceiling.md"

M_MAX = 1549            # current data range upper bound
N_MAX = 4 * M_MAX * M_MAX + 1   # 4·1549² + 1 ≈ 9.6M, the system_limits ceiling


def sieve_tau(n_max):
    """Return array tau[0..n_max] of divisor counts. tau[0] = 0."""
    tau = np.zeros(n_max + 1, dtype=np.uint16)
    tau[1:] = 1                                   # 1 itself
    for d in range(2, n_max + 1):
        tau[d::d] += np.uint16(1)                 # d divides d, 2d, 3d, ...
    return tau


def compute_m_star(m_max, tau):
    """Return arrays m_star[1..m_max], M_at[1..m_max], tau_at[1..m_max].

    M_at[m] is the M attaining M*(m); tau_at[m] = τ(M_at[m]).
    """
    n_max = len(tau) - 1
    # m_min[M] = ⌈M / τ(M)⌉ for M ≥ 1; floor div with the ceil correction.
    # Skip M=0; τ(0)=0 would divide-by-zero.
    M = np.arange(1, n_max + 1, dtype=np.int64)
    t = tau[1:].astype(np.int64)
    m_min = (M + t - 1) // t                       # ⌈M/τ(M)⌉

    # bucket[m] = largest M with m_min(M) == m, for m ∈ [1, m_max].
    # Anything with m_min > m_max can't bind for our m range; drop it.
    keep = m_min <= m_max
    M_kept = M[keep]
    m_min_kept = m_min[keep]

    bucket = np.zeros(m_max + 2, dtype=np.int64)
    # np.maximum.at scatter-reduces with duplicate indices.
    np.maximum.at(bucket, m_min_kept, M_kept)

    # Prefix-max over m=1..m_max. Keep 1-indexed: m_star[0] = 0, m_star[m] = M*(m).
    m_star = np.zeros(m_max + 1, dtype=np.int64)
    m_star[1:] = np.maximum.accumulate(bucket[1:m_max + 1])

    # Recover the τ value at the attaining M for each m. Walk forward,
    # updating the witness whenever bucket[m] beats the current best.
    M_at = np.zeros(m_max + 1, dtype=np.int64)
    best = 0
    for m in range(1, m_max + 1):
        if bucket[m] > best:
            best = int(bucket[m])
        M_at[m] = best
    tau_at = tau[M_at].astype(np.int64)
    return m_star, M_at, tau_at


def load_fixed_points():
    """Yield (m, x) for known cycle_length==1 trials."""
    if not FIXED_POINTS_CSV.exists():
        return []
    out = []
    with FIXED_POINTS_CSV.open(encoding="utf-8") as f:
        for row in csv.DictReader(f, skipinitialspace=True):
            out.append((int(row["m"]), int(row["x"])))
    return out


def fit_log_log(ms, ys):
    """OLS fit of log(y) = α·log(m) + β. Skip m=1 (log 1 = 0). Returns (α, β)."""
    ms = np.asarray(ms, dtype=np.float64)
    ys = np.asarray(ys, dtype=np.float64)
    mask = (ms > 1) & (ys > 0)
    lm = np.log(ms[mask])
    ly = np.log(ys[mask])
    alpha, beta = np.polyfit(lm, ly, 1)
    return float(alpha), float(beta)


def main():
    print(f"# sieving τ up to N = {N_MAX:,} (= 4·M_MAX² + 1)")
    tau = sieve_tau(N_MAX)
    print(f"# τ sieve done: τ(1)={tau[1]}, τ(12)={tau[12]}, "
          f"τ(2520)={tau[2520]}, τ(720720)={tau[720720]}")

    print(f"# computing M*(m) for m=1..{M_MAX}")
    m_star, M_at, tau_at = compute_m_star(M_MAX, tau)

    # Sanity: every M_at[m] satisfies M_at[m] ≤ m · τ(M_at[m]).
    for m in (1, 2, 3, 8, 100, 569, 1291, 1549):
        M = int(M_at[m]); t = int(tau_at[m])
        assert M <= m * t, f"m={m}: M*={M}, τ={t}, m·τ={m*t}, breaks bound"

    # Fixed-point cross-check.
    fp = load_fixed_points()
    fp_check = []
    for m, x in fp:
        if m > M_MAX:
            continue
        Mstar = int(m_star[m])
        ok = Mstar >= x
        fp_check.append((m, x, Mstar, Mstar - x, ok))
        assert ok, f"FAIL: fixed point m={m}, x={x} not ≤ M*(m)={Mstar}"
    print(f"# fixed-point cross-check: all {len(fp_check)} pass")

    # ---- Write CSV -----------------------------------------------------
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["m", "M_star", "tau_at_M_star",
                    "m_times_tau_at_M_star", "slack"])
        for m in range(1, M_MAX + 1):
            M = int(M_at[m]); t = int(tau_at[m])
            w.writerow([m, M, t, m * t, m * t - M])
    print(f"wrote {OUT_CSV.relative_to(ROOT)} ({M_MAX} rows)")

    # ---- Asymptotic fit -----------------------------------------------
    # ms[0] = 0 placeholder, m_star[0] = 0 — both arrays 1-indexed.
    ms = np.arange(M_MAX + 1)
    ms_pos = ms[1:]
    ms_pos_f = ms_pos.astype(np.float64)
    m_star_pos = m_star[1:]
    alpha, beta = fit_log_log(ms_pos, m_star_pos)
    # Wigert: max τ(N) ~ exp(ln 2 · ln N / ln ln N), so M*(m) is sub-quadratic.
    # The fit α should sit between 1 (linear) and 2 (Wigert worst-case 4m²).
    half = M_MAX // 2
    fit_50_pct = fit_log_log(ms_pos[half:], m_star_pos[half:])

    # Tail comparison points.
    def tail_stats(m_lo, m_hi):
        sl = (ms >= m_lo) & (ms <= m_hi)
        return {
            "n": int(sl.sum()),
            "med_M_star": float(np.median(m_star[sl])),
            "med_M_star_over_m_squared":
                float(np.median(m_star[sl] / (ms[sl] ** 2))),
            "med_M_star_over_m_lnm":
                float(np.median(m_star[sl] / (ms[sl] * np.log(ms[sl])))),
            "max_M_star": int(np.max(m_star[sl])),
        }
    tail_full = tail_stats(200, M_MAX)
    tail_top = tail_stats(1000, M_MAX)

    # Headline: how loose is 4m² vs M*(m)?
    looseness = (4.0 * ms_pos_f ** 2) / np.maximum(m_star_pos, 1)
    med_looseness = float(np.median(looseness[ms_pos >= 200]))

    # ---- Markdown ------------------------------------------------------
    md = ["# Sustained-ceiling locus M*(m)  (ROADMAP §E.1)",
          "",
          "Source: `analysis/system_limits.md` (definition + 4m² bound),",
          "`analysis/fixed_points.csv` (cross-check).",
          f"Computed for m=1..{M_MAX} from a τ sieve of size",
          f"{N_MAX:,} (= 4·{M_MAX}² + 1).",
          "Script: `analysis/build_sustained_ceiling.py`.",
          "Per-m table: `analysis/sustained_ceiling.csv`.",
          "",
          "## Definition recap",
          "",
          "`M*(m) = max{ M ∈ ℕ : M ≤ m · τ(M) }` is the largest value a",
          "window of size m can sustain. A flat window `[M*, M*, …, M*]`",
          "maps to `a_next = m · τ(M*) ≥ M*`. Above `M*(m)` every step",
          "strictly shrinks the maximum (system_limits.md §3–§5).",
          "",
          "Equivalently `M*(m) = max{ M : m ≥ ⌈M/τ(M)⌉ }`, so a single",
          "τ sieve plus a prefix-max over m gives the full locus in",
          "O(N) memory and O(N log N) sieve time.",
          "",
          "## Headline",
          "",
          f"- **M*(1549) = {int(m_star[M_MAX]):,}** "
          f"(τ = {int(tau_at[M_MAX])}, m·τ = {M_MAX * int(tau_at[M_MAX]):,}, "
          f"slack = {M_MAX * int(tau_at[M_MAX]) - int(m_star[M_MAX]):,}).",
          f"- **4m² bound**: 4·1549² = {4 * M_MAX * M_MAX:,}. "
          f"Median ratio 4m²/M*(m) over m∈[200, {M_MAX}]: "
          f"**{med_looseness:.1f}×**. The bounded-orbits proof's worst-case",
          "  ceiling is roughly 1.5 orders of magnitude looser than the",
          "  actual sustained ceiling — the slack is the gap between",
          "  worst-case τ (HCN-driven, Wigert) and the τ-density at the",
          "  relevant M.",
          "",
          "## Asymptotic fit",
          "",
          f"- Full range (m∈[2,{M_MAX}]):    "
          f"`log M*(m) ≈ {alpha:.4f} · log m + {beta:.4f}`.",
          f"- Top half (m∈[{M_MAX // 2 + 1},{M_MAX}]): "
          f"`log M*(m) ≈ {fit_50_pct[0]:.4f} · log m + {fit_50_pct[1]:.4f}`.",
          "",
          "Interpretation. Wigert's theorem gives",
          "`max_{n ≤ N} τ(n) ~ exp((ln 2 + o(1)) · ln N / ln ln N)`, so",
          "`M*(m)` should grow as `m^{1 + Θ(1/ln ln m)}` — between linear",
          "and quadratic, with the exponent slowly decaying toward 1. The",
          "empirical exponent fits this shape: top-half slope is",
          f"{fit_50_pct[0]:.3f} (closer to 1 than the full-range",
          f"{alpha:.3f}, consistent with slow decay). 4m² (slope 2) is",
          "the worst-case loose end of this band.",
          "",
          "## Tail statistics",
          "",
          "| range | n | median M* | M*/m² | M*/(m·ln m) | max M* |",
          "|---|---:|---:|---:|---:|---:|",
          f"| m∈[200, {M_MAX}] | {tail_full['n']} | "
          f"{tail_full['med_M_star']:,.0f} | "
          f"{tail_full['med_M_star_over_m_squared']:.3f} | "
          f"{tail_full['med_M_star_over_m_lnm']:,.1f} | "
          f"{tail_full['max_M_star']:,} |",
          f"| m∈[1000, {M_MAX}] | {tail_top['n']} | "
          f"{tail_top['med_M_star']:,.0f} | "
          f"{tail_top['med_M_star_over_m_squared']:.3f} | "
          f"{tail_top['med_M_star_over_m_lnm']:,.1f} | "
          f"{tail_top['max_M_star']:,} |",
          "",
          "Per `analysis/explore.ipynb` §6 (m·ln(m) bound), the empirical cycle band sits at",
          "`cycle_max ≈ 1.13·m·ln m` and `max_value ≈ 2.13·m·ln m`. The",
          f"sustained ceiling sits at ~{tail_top['med_M_star_over_m_lnm']:.0f}·m·ln m",
          "in the top half — i.e. roughly **two orders of magnitude above**",
          "the typical cycle band. The trajectory under seed=1 leaves the",
          "vast majority of the sustainable state space unvisited.",
          "",
          "## Fixed-point cross-check (§C.1 → §E.1)",
          "",
          "Every fixed point `x = m·τ(x)` satisfies `x ≤ m·τ(x)` with",
          "equality, so `x ≤ M*(m)`. The slack `M*(m) - x` is the",
          "headroom between the visited fixed point and the largest",
          "sustainable value at that m.",
          "",
          "| m | x (fixed pt) | M*(m) | M*(m) − x | M*(m)/x |",
          "|---:|---:|---:|---:|---:|"]
    for m, x, Mstar, slack, _ok in fp_check:
        ratio = Mstar / x if x > 0 else float("inf")
        md.append(f"| {m} | {x:,} | {Mstar:,} | {slack:,} | {ratio:.1f}× |")

    md += ["",
           "Reading. The headroom `M*(m)/x` for the 8m primes grows",
           "monotonically from 7× (m=127) to 19× (m=1291) — the seed=1",
           "trajectory finds the smallest sustainable fixed point but",
           "the upper sustainable region grows roughly an order of",
           "magnitude wider over this range. This is the wedge for §E.4",
           "basin-of-attraction probes — the flat-ceiling seed starts at",
           "`M*(m)`, far above the seed=1 fixed point.",
           "",
           f"(Cross-check operates against the current contents of",
           f"`{FIXED_POINTS_CSV.relative_to(ROOT).as_posix()}` —",
           f"{len(fp_check)} rows. `explore.ipynb` §8 (§C.1) lists 8 8m primes; if",
           "1103 and 1117 are missing here, regenerate fixed_points.csv",
           "with `analysis/build_fixed_points.py` over the full input set.)",
           "",
           "## Open",
           "",
           "- **Multiple fixed-point candidates per m.** Beyond the",
           "  largest M*(m), every M < M*(m) with M = m·τ(M) is also",
           "  an integer fixed point. Enumerate the full fixed-point",
           "  set per m (not just the maximum) and cross-link with the",
           "  attractor catalog (`explore.ipynb` §6 / §2): does the trajectory ever",
           "  visit a non-largest fixed point?",
           "- **Slack as a basin proxy.** Hypothesis: large slack",
           "  `M*(m) − x_{seed=1}` correlates with slow convergence",
           "  (`repeat_after`) for the 8m primes. The 8m table above",
           "  feeds directly into §C.2 hitting-time scaling.",
           ""]

    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"wrote {OUT_MD.relative_to(ROOT)}")

    # ---- Console summary ----------------------------------------------
    print()
    print(f"# M*(1) = {int(m_star[1])}, M*(2) = {int(m_star[2])}, "
          f"M*(127) = {int(m_star[127]):,}, M*(569) = {int(m_star[569]):,}, "
          f"M*({M_MAX}) = {int(m_star[M_MAX]):,}")
    print(f"# fit:   log M* ≈ {alpha:.4f}·log m + {beta:.4f} "
          f"(top half: {fit_50_pct[0]:.4f}·log m + {fit_50_pct[1]:.4f})")
    print(f"# 4m²/M*(m) median (m≥200): {med_looseness:.1f}×")
    print(f"# fixed-point cross-check: {len(fp_check)}/{len(fp_check)} pass")


if __name__ == "__main__":
    main()

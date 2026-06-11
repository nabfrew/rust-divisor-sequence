"""Generator for analysis/explore.ipynb — the consolidated analysis document.

Run with `python analysis/_build_explore_nb.py` from the repo root. Produces
`analysis/explore.ipynb` with cleared outputs; populate by opening it in
JupyterLab and running all cells (`jupyter nbconvert --execute --inplace`
also works where the nbclient async kernel handshake is healthy).

The notebook is the **single consolidated document** for the project: it
absorbs the former standalone write-ups (`system_limits.md`, `mlnm_bound.md`,
`cycle_value_tau_structure.md`, `fixed_points.md`, `sustained_ceiling.md`,
`length_mp1_invariant.md`, `review_2026-06-10.md`, `Invariant.md`,
`human_notes.md`, `summary.md`, and the ROADMAP's open analysis items) into
one narrative, from problem statement to the current state of understanding,
ending with a Further-work section.

Kept as a script (not the notebook itself) so the source of truth is text-
diffable. Re-run if the chart set, merge logic, or write-up changes.
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf

nb = nbf.v4.new_notebook()
cells: list = []


def md(src: str) -> None:
    cells.append(nbf.v4.new_markdown_cell(src.strip()))


def code(src: str) -> None:
    cells.append(nbf.v4.new_code_cell(src.strip()))


# ---------------------------------------------------------------------------
# §0 Introduction
# ---------------------------------------------------------------------------

md(
    r"""
# The divisor-window sequence

This notebook is the consolidated record of everything we currently know
about the sequence

$$a_n = \sum_{i=1}^{m} \tau(a_{n-i}), \qquad a_1 = a_2 = \dots = a_m = 1,$$

where $\tau(k)$ is the number of divisors of $k$ and $m$ is the **window
size**. Each new term is the sum of the divisor counts of the previous $m$
terms. The parameter $m$ is the only knob; everything below studies how the
long-run behaviour depends on it.

### A worked example, m = 2

Seed `1, 1`. Then:

| step | window | next term |
|---|---|---|
| 3 | (1, 1) | τ(1)+τ(1) = **2** |
| 4 | (1, 2) | τ(1)+τ(2) = **3** |
| 5 | (2, 3) | τ(2)+τ(3) = **4** |
| 6 | (3, 4) | τ(3)+τ(4) = **5** |
| 7 | (4, 5) | τ(4)+τ(5) = **5** |
| 8 | (5, 5) | τ(5)+τ(5) = **4** |
| 9 | (5, 4) | τ(5)+τ(4) = **5** |
| 10 | (4, 5) | **5** … |

The sequence grows out of the all-ones seed, overshoots, and locks into the
period-3 cycle `4, 5, 5` — period $m+1$, a pattern that turns out to
dominate at every scale (§2.3, §5).

### What is measured

A Rust scanner (`src/lib.rs`, Brent cycle detection with a rolling-hash
window comparison) runs the sequence for each $m$ until the sliding-window
state repeats, then records one CSV row per $m$:

| column | meaning |
|---|---|
| `repeat_after` | steps until the window state first revisits an earlier state (= transient length μ + cycle length λ) |
| `max_value` | largest term ever produced (the transient peak) |
| `cycle_length` | λ, the period of the limit cycle |
| `cycle_min`, `cycle_max` | smallest / largest value inside the cycle |
| `most_common_tail_value` | the cycle value visited most often per period |
| `distinct_tail_values` | number of distinct values in the cycle |
| `steps_to_lock_in` | steps until the window's τ-multiset stops changing (transient/closed-loop split; recent column, `None` on legacy rows) |

Per-$m$ **cycle signatures** (the multiset `value → count` over one period)
are dumped to `analysis/cycle_signatures/<m>.csv`, and several derived
catalogues (attractors, fixed points, sustained ceilings, K-level-sets) live
alongside this notebook in `analysis/`.

### Terminology and notation

Used consistently throughout this document:

- **τ(x)** — the number of divisors of x (written d(x) in some sources;
  τ everywhere here).
- **window** — the last m terms of the sequence; the window is the full
  dynamical state. **m** is always the window size.
- **seed** — the initial window contents. **seed=1** means the all-ones
  window, the default for every scan; alternatives appear only in the
  basin scans (§11).
- **transient (μ)** — the number of steps the orbit wanders before
  entering its cycle. **period (λ)** — the cycle length (`cycle_length`).
  `repeat_after` = μ + λ: the step at which the window state first equals
  an earlier state.
- **cycle band** — the interval `[cycle_min, cycle_max]` of values visited
  inside the cycle, viewed as a function of m (§3).
- **fixed point** — a cycle with λ = 1; equivalently an integer solution
  of x = m·τ(x) (§7).
- **resonance** — a cycle with λ = m + 1, the dominant family (§5). A
  cycle is **well-behaved** iff λ = m + 1 (older tables use the
  operational proxy "3 ≤ distinct ≤ 10, range ≤ 50, λ > 1", which captures
  essentially the same population).
- **cycle signature** — the multiset `value → count` over one period.
  **value set** — the *distinct* values only. An **attractor** is a value
  set shared verbatim by the cycles of many different m (§9); the CSV
  column `distinct_tail_values` (abbreviated **distinct**) is the value
  set's size, and **range** = `cycle_max − cycle_min`.
- **level set S(K)** = {x : x + τ(x) = K}. A **K-attractor** is a level
  set realised by length-(m+1) cycles; K is that family's invariant (§5).
- **wide-band outlier** — a trial with range > 100 or distinct > 50.
  **runaway cycle** — a trial with λ > 10·m. Both defined and tabulated
  in §10.
- **M\*(m)** — the sustained ceiling, the largest M with M ≤ m·τ(M)
  (§1, §8). **4m²** — the worst-case ceiling from the bounded-orbits
  proof (§1).
- **basin scan** — T = 200 random-seed trials per m (§11), seeds drawn
  per window slot from `round(LogNormal(ln(m·ln m), 0.71))`.

### Document map

1. Bounded orbits — why a cycle is inevitable, and the two ceilings
2. Empirical overview — `repeat_after`, `max_value`, `cycle_length`
3. The m·ln m cycle band
4. The conservation law `mean_v = m · mean_τ`
5. Length-(m+1) cycles and the invariant `x + τ(x) = K`
6. The 8m envelope
7. Fixed points — the full catalogue
8. The sustained ceiling M*(m) and the four-band picture
9. The attractor catalogue (and the `(2m−199)(m+1)` harmonic family)
10. Wide-band outliers and runaway cycles
11. Random-seed basin scans
12. Further work
"""
)

code(
    """
from pathlib import Path

import math

import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
import numpy as np
import pandas as pd

# Notebook is executed with CWD = analysis/ (jupyter convention) or repo root.
cwd = Path.cwd()
ROOT = cwd if (cwd / 'analysis').exists() else cwd.parent
ANA = ROOT / 'analysis'

results = pd.read_csv(ROOT / 'results_new.csv', skipinitialspace=True)
gaps = pd.read_csv(ROOT / 'gaps.csv', skipinitialspace=True)
# Header in results_new.csv uses 'most common tail value'; gaps.csv uses underscores. Normalise.
results = results.rename(columns={'most common tail value': 'most_common_tail_value'})
combined = (
    pd.concat([results, gaps], ignore_index=True)
      .drop_duplicates(subset='m', keep='last')
      .sort_values('m')
      .reset_index(drop=True)
)
combined['m'] = combined['m'].astype(int)
all_m = set(combined['m'])
missing = sorted(set(range(1, combined['m'].max() + 1)) - all_m)
print(f'rows: {len(combined)}, m range: {combined.m.min()}..{combined.m.max()}, missing: {missing}')

# Population labels: cycle_length=1 (fixed point), cycle_length=m+1
# (resonance with the natural period), everything else (multi-m clusters / runaway).
def label(row):
    if row.cycle_length == 1:
        return 'fixed_point'
    if row.cycle_length == row.m + 1:
        return 'resonance_m+1'
    return 'other'
combined['population'] = combined.apply(label, axis=1)
print(combined['population'].value_counts())
"""
)

# ---------------------------------------------------------------------------
# §1 Bounded orbits
# ---------------------------------------------------------------------------

md(
    r"""
## 1. Bounded orbits — why a cycle is inevitable

**Theorem.** For any window size $m \in \mathbb{N}$ and *any* initial window
$\{x_1, \dots, x_m\} \in \mathbb{N}^m$, the sequence is bounded above.
Consequently it must eventually enter a cycle.

**Proof.** Suppose the sequence diverges. The divisor function is strictly
sublinear: every divisor $d > \sqrt{x}$ pairs with a divisor $x/d < \sqrt{x}$,
so

$$\tau(x) \le 2\sqrt{x}.$$

Let $M_k$ be the maximum value in the window at step $k$. Each window entry
contributes at most $\tau(M_k)$ to the sum (τ is not monotone, but the
worst case over values $\le M_k$ is bounded by $2\sqrt{M_k}$), hence

$$a_k \;=\; \sum_{i=1}^m \tau(a_{k-i}) \;\le\; 2m\sqrt{M_k}.$$

The new term is *strictly smaller* than the current maximum whenever
$2m\sqrt{M_k} < M_k$, i.e. whenever

$$M_k > 4m^2.$$

A diverging sequence would have to push $M_k$ past $4m^2$, at which point
every new term is strictly below the window maximum — the growth is
self-quenching. Contradiction. $\blacksquare$

Since values are confined to $[m,\, \max(4m^2, M_0)]$ (the floor $m$ because
$\tau \ge 1$), the window lives in a **finite state space**; the update rule
is deterministic, so by pigeonhole the window state must repeat, and the
first repeat closes a cycle. Every trial terminates — slow $m$'s (m=569 at
154 M steps, m=1291 at 4.2 B steps) are walking a long path through a finite
room, not escaping.

### Two ceilings: worst-case 4m² vs the sustained ceiling M*(m)

The proof's $4m^2$ ceiling assumes the window is flat at the *worst-case* τ.
A sharper, still-rigorous ceiling is the **sustained-ceiling locus**

$$M^*(m) = \max\{\, M \in \mathbb{N} : M \le m \cdot \tau(M) \,\},$$

the largest value a window of size $m$ can support without immediate decay
(a flat window of $M$'s maps to $a_{\text{next}} = m\,\tau(M) \ge M$). Above
$M^*(m)$ every step strictly shrinks the maximum. §8 computes this locus —
it sits ~26× below $4m^2$, and the trajectory in turn never gets anywhere
near $M^*(m)$: the empirically occupied band is another two orders of
magnitude lower, at $\sim m\ln m$ (§3).
"""
)

# ---------------------------------------------------------------------------
# §2 Empirical overview
# ---------------------------------------------------------------------------

md(
    r"""
## 2. Empirical overview

Three populations recur throughout this document:

- **`resonance_m+1`** — trials with λ = m + 1 (the *resonance*), the
  dominant outcome (~52% of all m). §5 explains why this family is special.
- **`fixed_point`** — trials with λ = 1 (9 m's under seed=1; §7).
- **`other`** — everything else: multi-m attractor clusters, harmonic
  families (§9), and runaway cycles with λ up to $10^{10}$ (§10).

### 2.1 `repeat_after(m)` — how long until the state repeats
"""
)

code(
    """
fig, ax = plt.subplots(figsize=(9, 5))
colors = {'resonance_m+1': '#1f77b4', 'other': '#d62728', 'fixed_point': '#2ca02c'}
for pop, sub in combined.groupby('population'):
    ax.scatter(sub['m'], sub['repeat_after'], s=6, alpha=0.45, c=colors[pop], label=f'{pop} (n={len(sub)})')
ax.set_yscale('log'); ax.set_xscale('log')
ax.set_xlabel('m (log)'); ax.set_ylabel('repeat_after (log)')
ax.set_title('Steps to detect cycle vs m, by population')
ax.grid(alpha=0.3, which='both')

# Power-law fit on the dominant resonance population only — the m+1 band is the
# clean trend; the 'other' tail and the 8m fixed points are well-known outliers.
res = combined[combined['population'] == 'resonance_m+1']
res = res[(res.m >= 50) & (res.repeat_after > 0)]
slope, intercept = np.polyfit(np.log(res.m), np.log(res.repeat_after), 1)
xs = np.linspace(res.m.min(), res.m.max(), 200)
ax.plot(xs, np.exp(intercept) * xs ** slope, 'k--',
        label=f'fit (resonance, m≥50): slope ≈ {slope:.2f}')
ax.legend(loc='lower right', fontsize=8)
plt.tight_layout(); plt.show()
print(f'Resonance fit: log(repeat_after) ≈ {slope:.3f} · log(m) + {intercept:.3f} (m ≥ 50)')
"""
)

md(
    """
The resonance population follows a steep power law (slope ≈ 5.3): the cost
of resolving an m grows much faster than m itself, which is why the scan's
long tail is compute-bound. The wandering transient μ dominates this cost —
the cycle itself is short for the resonance family.

### 2.2 `max_value(m)` — the transient peak
"""
)

code(
    """
fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
axes[0].scatter(combined.m, combined.max_value, s=4, alpha=0.5, c='#1f77b4')
axes[0].set_xlabel('m'); axes[0].set_ylabel('max_value')
axes[0].set_title('Transient peak max_value(m)')
axes[0].grid(alpha=0.3)

ratio = combined.max_value / combined.m
axes[1].scatter(combined.m, ratio, s=4, alpha=0.5, c='#d62728')
axes[1].set_xlabel('m'); axes[1].set_ylabel('max_value / m')
axes[1].set_title('max_value / m  —  approximately log-linear in m (m·ln m anchor)')
axes[1].grid(alpha=0.3)
# Anchors on right plot.
mm = np.linspace(combined.m.min() + 1, combined.m.max(), 400)
axes[1].plot(mm, np.log(mm), 'k--', label='ln m')
axes[1].plot(mm, np.log(mm) * 2.13, 'k:', label='2.13·ln m  (§3 median for max_value)')
axes[1].legend(fontsize=8)
plt.tight_layout(); plt.show()
print(f'max_value/m  median: {ratio.median():.3f}, p95: {ratio.quantile(0.95):.3f}, max: {ratio.max():.3f}')
"""
)

md(
    """
### 2.3 `cycle_length(m)` — the m+1 resonance dominates
"""
)

code(
    """
fig, ax = plt.subplots(figsize=(9, 5))
for pop, sub in combined.groupby('population'):
    ax.scatter(sub.m, sub.cycle_length, s=6, alpha=0.5, c=colors[pop], label=pop)
xs = np.linspace(1, combined.m.max(), 300)
ax.plot(xs, xs + 1, 'k-', linewidth=0.8, alpha=0.7, label='cycle_length = m+1')
ax.set_yscale('log')
ax.set_xlabel('m'); ax.set_ylabel('cycle_length (log)')
ax.set_title('Cycle length by m  —  the m+1 resonance dominates')
ax.legend(fontsize=8); ax.grid(alpha=0.3, which='both')
plt.tight_layout(); plt.show()

share_resonance = (combined.population == 'resonance_m+1').mean()
print(f'Share of m landing on cycle_length = m+1: {share_resonance:.1%}')
"""
)

md(
    """
The cycle-length ranking over the resolved data (m ≤ 1788 snapshot):

| form               | count |
|--------------------|------:|
| m+1                | 801   |
| m+2                | 212   |
| k(m+1) for k ≥ 2   | 134   |
| 2(m+1)+1 = 2m+3    | 48    |
| (2m−199)(m+1)      | 20    |
| 3(m+1)+1 = 3m+4    | 9     |
| fixed (λ=1)        | 9     |
| 4(m+1)+1 = 4m+5    | 3     |
| other              | 282   |

The dominant family is period m+1 (§5), with m+2 a clear second; periods of
the form k(m+1) and k(m+1)+1 are harmonics of the same resonance. The
`(2m−199)(m+1)` curve is a single attractor with a closed-form period
(§9b).
"""
)

# ---------------------------------------------------------------------------
# §3 m·ln m band
# ---------------------------------------------------------------------------

md(
    r"""
## 3. The m·ln m cycle band

Where do the cycle values live? The natural anchor comes from the average
order of the divisor function: $\frac{1}{N}\sum_{n \le N} \tau(n) \approx
\ln N$. If cycle values were τ-typical of their height $v$, a window of m
of them would sum to $\approx m \ln v$, and self-consistency $v = m\ln v$
puts the band at $v \approx m \ln m$ (up to iterated-log corrections).

Empirically this anchor is tight. Quantified against `m·ln(m)` and
`m·H(m)` (exact harmonic sum; marginally tighter, as expected from
$H(m) = \ln m + \gamma + O(1/m)$), for m ≥ 200:

- `cycle_min ≥ 0.591 · m·ln(m)`  (empirical inf)
- `cycle_max ≤ 2.20 · m·ln(m)`  (empirical sup, outlier-driven; §10)
- `max_value ≤ 2.69 · m·ln(m)`  (transient peak)

Tail medians (m ≥ 200): `cycle_min` 1.12, `cycle_max` 1.13, `max_value`
2.11 — i.e. **transient peaks sit ~2× above the cycle band**, consistent
with the orbit overshooting before settling. The `[p5, p95]` spread of
`cycle_max/(m·ln m)` contracts ~6× from m<50 to m≥1000, though outlier
m's (601, 738–751, 1242–1254, …) keep the per-bin max in the 2.0–2.2×
range.

The trivial lower bound `cycle_min ≥ m` (from τ ≥ 1) corresponds to a
ratio of `1/ln(m)` ≈ 0.14 at m=1349 — the empirical inf 0.591 is ~4×
higher, so the data supports a much sharper lower bound than the trivial
argument gives. Detail tables: `analysis/mlnm_bound.csv` (regenerate with
`python analysis/quantify_mlnm_bound.py`).
"""
)

code(
    """
mm = combined.m.values
H = np.array([float(np.sum(1.0 / np.arange(1, m + 1))) for m in mm])

fig, ax = plt.subplots(figsize=(10, 5.5))
ax.scatter(mm, combined.cycle_min, s=4, alpha=0.5, c='#1f77b4', label='cycle_min')
ax.scatter(mm, combined.cycle_max, s=4, alpha=0.5, c='#d62728', label='cycle_max')

xs = np.linspace(2, mm.max(), 400)
H_xs = np.array([float(np.sum(1.0 / np.arange(1, int(x) + 1))) for x in xs])
ax.plot(xs, xs, 'k--', alpha=0.6, label='m')
ax.plot(xs, xs * np.log(xs), 'g-', alpha=0.7, label='m·ln m')
ax.plot(xs, xs * H_xs, 'b:', alpha=0.7, label='m·H(m)')

ax.set_yscale('log'); ax.set_xscale('log')
ax.set_xlabel('m (log)'); ax.set_ylabel('value (log)')
ax.set_title('Cycle band vs m·ln m / m·H(m) anchors')
ax.legend(fontsize=8); ax.grid(alpha=0.3, which='both')
plt.tight_layout(); plt.show()

mask = combined.m >= 200
ratio_min = (combined.loc[mask, 'cycle_min'] / (combined.loc[mask, 'm'] * np.log(combined.loc[mask, 'm']))).quantile(0.05)
ratio_max = (combined.loc[mask, 'cycle_max'] / (combined.loc[mask, 'm'] * np.log(combined.loc[mask, 'm']))).quantile(0.95)
print(f'sanity (m ≥ 200):  cycle_min/(m·ln m) p5 ≈ {ratio_min:.3f},  cycle_max/(m·ln m) p95 ≈ {ratio_max:.3f}')
"""
)

# ---------------------------------------------------------------------------
# §4 Conservation law
# ---------------------------------------------------------------------------

md(
    r"""
## 4. The conservation law `mean_v = m · mean_τ`

### The wandering-height identity

The recurrence itself says: **at every step, the new value is exactly m
times the window mean of τ** —

$$a_{n+1} = \sum_{\text{window}} \tau = m \cdot \overline{\tau}_{\text{window}}.$$

The orbit's height is a τ-thermometer of its own recent past, at all times,
not only inside cycles. The empirical "cycle values live in [4m, 9m]"
band (§6) is literally "the window mean of τ stays in [4, 9]".

### The cycle average (exact)

For any cycle with period λ and temporal values $a_1, \dots, a_\lambda$,
summing the recurrence over one period (cyclic indexing; each $\tau(a_k)$
appears in m consecutive window-sums) gives

$$\sum_t a_t = m \sum_t \tau(a_t), \qquad\text{equivalently}\qquad
\overline{v} = m \cdot \overline{\tau}$$

with the mean taken over the cycle's temporal sequence (= count-weighted
mean over the value multiset). This is an *exact integer identity* —
verified bit-exactly on every resolved m (max residual over all cycles: 0).

Combining it with the empirical band `mean_v ≈ m·ln m` (§3) implies
**`mean_τ ≈ ln m`**: the cycle's τ-multiset averages like τ over integers
near m·ln m. Per population bucket (`analysis/cycle_value_tau_structure.csv`):

| bucket                              |   n   | mean τ / ln m |
|-------------------------------------|------:|--------------:|
| Well-behaved (3 ≤ distinct ≤ 10, range ≤ 50) | 1225 |        1.095  |
| Wide-band outlier (range > 100 or distinct > 50) | 74 |        1.219  |
| Runaway (λ > 10·m)                  |   96  |        1.264  |
| Near-resonance (λ within ±3 of a multiple of m) | 1142 |        1.084  |
| Off-resonance                       |  298  |        1.230  |

### Value–τ anticorrelation

To hold `Σ a_t = m Σ τ(a_t)` inside a tight band, a cycle must mix values
above and below the mean τ: high-τ values sit at low v, low-τ values at
high v. For the dominant length-(m+1) family the relationship is *exactly
linear* — `τ(x) = K − x` (§5) — so Spearman ρ(v, τ) = −1. Empirically:

| bucket                              |   n   | median ρ(v,τ) | % ρ ≤ −0.9 |
|-------------------------------------|------:|--------------:|-----------:|
| Well-behaved (3 ≤ distinct ≤ 10, range ≤ 50) | 1225 | −1.000        |     63.4%  |
| Near-resonance (λ within ±3 of a multiple of m) | 1142 | −1.000        |     69.8%  |
| Wide-band outlier                   |   74  |  +0.012       |      0.0%  |
| Runaway (λ > 10·m)                  |   96  | −0.112        |      0.0%  |
| Off-resonance                       |  298  | −0.313        |      0.0%  |

Wide-band and runaway cycles span enough of the integer line that τ's
natural roughness washes the constraint out into a population average —
the same conservation law holds, but it no longer pins the order of the
values.

### Consequences

1. **Cycles need a balanced τ-neighbourhood.** m·ln m must lie in a range
   where some integers have τ > ln m and others τ < ln m, close enough for
   one m-window to mix them — automatic at large m by Hardy–Ramanujan, a
   real constraint near smooth-number confluences (§10).
2. **Fixed points are the equality limit**: λ=1 reduces conservation to
   `v = m·τ(v)` — exactly §7's fixed-point condition, and the equality
   boundary of the sustained ceiling §8.
3. The chart below computes per-m cycle means from the signature dumps:
   the exact law is `mean_v = m·mean_τ`; the *empirical* content is that
   `mean_τ` hovers near ln m (±~30%).
"""
)

code(
    """
SIG_DIR = ANA / 'cycle_signatures'
records = []
for sig in SIG_DIR.glob('*.csv'):
    try:
        m = int(sig.stem)
    except ValueError:
        continue
    df = pd.read_csv(sig)
    total = df['count'].sum()
    if total == 0:
        continue
    mean_v = float((df['value'] * df['count']).sum() / total)
    records.append((m, mean_v))
sigs = pd.DataFrame(records, columns=['m', 'mean_v']).sort_values('m').reset_index(drop=True)
sigs['mlnm'] = sigs.m * np.log(sigs.m.where(sigs.m > 0, 1))
sigs['ratio'] = sigs.mean_v / sigs.mlnm.replace(0, np.nan)

fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
axes[0].scatter(sigs.m, sigs.mean_v, s=4, alpha=0.5, c='#1f77b4', label='mean cycle value')
xs = np.linspace(2, sigs.m.max(), 400)
axes[0].plot(xs, xs * np.log(xs), 'k-', alpha=0.7, label='m·ln m')
axes[0].set_xlabel('m'); axes[0].set_ylabel('mean cycle value'); axes[0].set_yscale('log'); axes[0].set_xscale('log')
axes[0].legend(fontsize=8); axes[0].grid(alpha=0.3, which='both')
axes[0].set_title('mean cycle value vs m·ln m')

axes[1].scatter(sigs.m, sigs.ratio, s=4, alpha=0.5, c='#d62728')
axes[1].axhline(1.0, color='k', linestyle='--', alpha=0.5)
axes[1].set_xlabel('m'); axes[1].set_ylabel('mean_v / (m·ln m)')
axes[1].set_title('Deviation from m·ln m anchor')
axes[1].set_ylim(0.5, 2.0); axes[1].grid(alpha=0.3)
plt.tight_layout(); plt.show()

mask = sigs.m >= 200
print(f'mean_v / (m·ln m), m ≥ 200:  median {sigs.loc[mask, "ratio"].median():.4f}, '
      f'p5 {sigs.loc[mask, "ratio"].quantile(0.05):.4f}, '
      f'p95 {sigs.loc[mask, "ratio"].quantile(0.95):.4f}')
"""
)

# ---------------------------------------------------------------------------
# §5 Length-(m+1) invariant
# ---------------------------------------------------------------------------

md(
    r"""
## 5. Length-(m+1) cycles and the invariant `x + τ(x) = K`

### Derivation

The recurrence can be written incrementally:
$a_{n+1} = a_n + \tau(a_n) - \tau(a_{n-m})$. If the period is $P = m+1$,
then $a_{n-m} = a_{n-m+P} = a_{n+1}$ (because $-m \equiv 1 \pmod{m+1}$), so

$$a_{n+1} = a_n + \tau(a_n) - \tau(a_{n+1})
\;\Longrightarrow\;
a_{n+1} + \tau(a_{n+1}) = a_n + \tau(a_n) =: K.$$

**Every value in a length-(m+1) cycle lies in the level set
$S(K) = \{x : x + \tau(x) = K\}$ of a single integer K.** Verified
bit-exactly on every length-(m+1) cycle in the data (cell below).

The derivation only uses $-m \equiv 1 \pmod P$, i.e. **any period dividing
m+1 inherits the invariant**. In the data the only such periods are
P = m+1 itself and the nine λ = 1 fixed points (m = 1, 127, 167, 211,
613, 733, 1103, 1117, 1291 — all prime), where it holds vacuously with
$K = x + \tau(x)$ for the single value (and $x = m\tau(x)$ gives
$K = (m+1)\tau(x)$, the λ = 1 case of $K = (m+1)\overline{\tau}$). No
non-trivial proper divisor of m+1 ever appears as a period.

### Consequences

- $\tau(x) = K - x$ on the cycle: the value–τ anticorrelation of §4 is
  *exactly linear* here (ρ = −1), and the cycle's value range **equals**
  its τ-range: `cmax − cmin = τ_max − τ_min` (observed max: 28 — the band
  thickness is O(1), independent of m).
- $K = (m+1)\cdot\overline{\tau}$ (combine `mean_v = m·mean_τ` with
  `mean_v + mean_τ = K`).
- Each cycle element equals the sum of the other m elements' τ's
  (immediate from $\Sigma\tau = K$ and $x + \tau(x) = K$).
- The dynamics inside the cycle is rotation of a fixed multiset: for any
  window of m of the m+1 entries, the next term is `K − τ(outgoing) =
  outgoing`. A multiset from S(K) of size m+1 is a valid cycle **iff** it
  also satisfies $\Sigma_v n_v \tau(v) = K$ (the admissibility condition
  below) — *which* admissible multiset gets realised is selected by the
  seed/transient, not by the recurrence.

### Parity lemma

τ(x) is odd iff x is a perfect square, so from $x = K - \tau(x)$:
**every non-square value in a length-(m+1) cycle has the same parity as
K.** Zero violations across all length-(m+1) signatures (cell below).
This explains the even value-gaps inside cycles (…112/114/116/118…), the
overwhelmingly even K-catalogue, and most likely the Δ=4 spacing of
dominant K's in the m+2 family (same-parity K's with populated S(K) are
typically 4 apart).
"""
)

code(
    """
# Verify the K-invariant and the parity lemma on every length-(m+1) signature.
SIG_DIR = ANA / 'cycle_signatures'

def tau(n: int) -> int:
    c, i = 0, 1
    while i * i <= n:
        if n % i == 0:
            c += 1 if i * i == n else 2
        i += 1
    return c

mp1 = combined[combined.cycle_length == combined.m + 1]
checked = invariant_violations = parity_violations = 0
K_per_m = {}
for m in mp1.m:
    p = SIG_DIR / f'{m}.csv'
    if not p.exists():
        continue
    sig = pd.read_csv(p)
    Ks = {int(v) + tau(int(v)) for v in sig['value']}
    if len(Ks) != 1:
        invariant_violations += 1
        continue
    K = Ks.pop()
    K_per_m[int(m)] = K
    checked += 1
    for v in sig['value']:
        v = int(v)
        if math.isqrt(v) ** 2 != v and (v - K) % 2 != 0:
            parity_violations += 1

print(f'length-(m+1) cycles with signatures: {checked}')
print(f'cycles violating x + τ(x) = K:       {invariant_violations}   (0 = invariant exact)')
print(f'non-square parity violations:        {parity_violations}   (0 = parity lemma exact)')
ks = pd.Series(K_per_m)
print(f'distinct K values realised:          {ks.nunique()}')
print(f'K parity: {int((ks % 2 == 0).sum())} even, {int((ks % 2 == 1).sum())} odd')
"""
)

md(
    r"""
### K-reuse: a small catalogue of attractors

K is highly reused across m — only ~60 distinct K's across 801 seed=1
cycles (m ≤ 1788 snapshot). Top entries:

| K     | n m's | m range       |
|------:|------:|---------------|
| 6242  | 196   | [767, 1296]   |
| 9410  | 171   | [1114, 1788]  |
| 5162  | 72    | [579, 981]    |
| 7562  | 48    | [857, 1445]   |
| 6222  | 37    | [781, 1177]   |
| 2046  | 34    | [267, 463]    |
| 10202 | 26    | [1276, 1752]  |

The same level set S(K) supports length-(m+1) cycles for hundreds of
consecutive m's; only the multiplicities shift with m to keep
$(m+1)\overline{\tau} = K$. On a fixed-K plateau, `mean_τ` *decreases* as
m grows (e.g. K=9410: mean_τ 5.79 at m=1625 → 5.26 at m=1788).

### The 4m–9m band, reformulated

`cmin/m` and `cmax/m` both collapse onto `K/m` as m grows (band thickness
is O(1)/m), so the empirical "cycle values live in [4m, 9m]" statement is
really a bound on a single statistic:

> **K/m ∈ [4.22, 9.26]** over all observed length-(m+1) cycles. The max
> 9.26 is attained at m=285 (K=2638) and never exceeded through m=1788;
> the upper quantiles *shrink* with m. Fit: `K ≈ 455 + 6.40·m`.

`mean_τ = K/(m+1)` shows **no detectable growth with m** (all regression
slopes within 1–2 SE of zero; top-half slope mildly negative). If that
flatness extrapolates, the band is genuinely `mean_τ ∈ [≈4.2, ≈9.2]` for
all m — in tension with the `mean_τ ≈ 1.1·ln m` fit of §4, which agrees
numerically only because 1.1·ln(1788) ≈ 8.2 happens to sit at the ceiling
in this finite range. Discriminating bounded-vs-ln m needs m ≳ 10⁴ (§12).

### Admissibility vs realisation

A K supports a length-(m+1) cycle iff non-negative integers $(n_v)_{v \in S(K)}$
exist with $\Sigma n_v = m+1$ and $\Sigma n_v \tau(v) = K$. Equivalently:
$\tau_{\min}(S(K)) \le K/(m+1) \le \tau_{\max}(S(K))$ plus a gcd
divisibility condition on $K - (m+1)\tau_{\min}$. This is fully enumerable
from a τ-sieve (`analysis/length_mp1_K_catalogue.csv`,
`length_mp1_admissibility.csv`).

- **All realised K's are admissible** (801/801) — the static enumeration
  captures the dynamics' choices.
- But the admissible set is huge: typically **200–350 candidate K's per
  m**, of which the dynamics realises exactly one.
- The realised K concentrates in the **bottom third** of the sorted
  admissible set (median position 0.16) but is essentially never the
  smallest (5/801); no simple static selection rule tested (smallest,
  largest, max |S(K)|, …) explains the choice.
- The position **drifts upward with m** (r ≈ +0.55): the dynamics reaches
  deeper into the admissible set as m grows.

### Floor and ceiling: what is structural, what is dynamical

- **The 4m floor is dynamical.** Admissible K's exist down to
  `K/m ≈ 2` at every large m — the seed=1 transient simply never reaches
  them, and neither do random log-normal seeds centred on m·ln m (§11).
  The floor is *basin-robust* but not structural; falsifying it would
  take seeds targeted at the small-cmin regime (§12).
- **The 9m ceiling is also (at least partly) dynamical.** A descriptive
  rule over the sampled K-window — "K is reached iff |S(K)| ≥ 3 or
  (|S(K)|=2 and τ_min ∈ [4,8])", 98% recall — *describes* the reached set,
  but extrapolating the same rule over a τ-sieve to K ≤ 2·10⁶ predicts
  ceilings of 70–240·m where the dynamics tops out near 8–9·m. Whatever
  pins the ceiling involves the orbit's wandering height, not level-set
  combinatorics alone. The reach-rate *is* steeply monotone in |S(K)|
  (1.5% at |S|=2 → 50% at |S|=5), and the never-reached extremes
  (τ_max ≤ 4 prime/semiprime level sets below the floor; all-τ-rich sets
  above the ceiling) remain telling — they are necessary conditions, not
  the explanation.

### Neighbouring families: m+2 and 2m+3

There is **no scalar K-invariant for any period other than m+1**. For
P = m+2 the cycle relation gives a per-triple identity
$\tau(a_{n+2}) = a_n + \tau(a_n) - a_{n+1}$; summing it cyclically
recovers conservation and nothing more. Empirically the m+2 family
(212 cycles) is a *perturbation* of m+1: each cycle draws from 3–5
distinct level sets S(K), with **two dominant K's** (almost always spaced
Δ=4, the minimal same-parity gap) carrying m of the m+2 entries, plus 2
single-multiplicity "linker" entries. The 2m+3 family (48 cycles) is the
doubled-up version — two passes of the same dominant pair, 2–3 linkers —
and 90% of its dominant K's also appear as m+1 K-attractors. Both inherit
the 4m–9m band because their dominant K's sit in the same envelope.
Detail: `analysis/length_mp2_K_structure.csv`,
`length_2mp1_K_structure.csv`.

### A weaker exact invariant for the other families: class sums mod gcd(m, P)

The per-triple identity generalises: for any period P write d = P − m, so
$\tau(a_{n+d}) = a_n + \tau(a_n) - a_{n+1}$. Summing it over one orbit of
$n \mapsto n + d \pmod P$ telescopes the τ terms away, leaving
$g = \gcd(d, P) = \gcd(m, P)$ exact linear relations:

> **The cycle's value sums over positions in each residue class mod g are
> all equal** (each class carries $\frac{1}{g}\Sigma a_n$).

For g = 1 this is vacuous — and P = m+1 always has g = 1; there the
pointwise invariant is the d = 1 collapse of the same telescoping.
Non-trivial instances in the data (verified bit-exactly, cell below):

- **m+2 family, even m** (g = 2): the two alternating-position sums
  around the cycle are equal — m = 4, 16, 30, 80 all exact.
- **2m+3 family, 3 | m** (g = 3): the three class sums are equal —
  m = 552 (P = 1107, reached after an 18.2M-step transient; all three
  sums are 1 636 864).

This is more than conservation (the cycle's mass is *balanced* across
position classes) but far less than the m+1 invariant: it constrains only
g − 1 linear combinations instead of pinning every element to one level
set — consistent with m+2 cycles spreading over 3–5 level sets where
m+1 cycles live in exactly one.
"""
)

code(
    """
# Verify the class-sum invariant on m+2 (g=2) and 2m+3 (g=3) cycles.
# Ring-buffer simulation, no window history (repeat_after from the scan
# data tells us exactly how far to run). m=552 takes ~30 s.
import collections

def cycle_class_sums(m, P, repeat_after, tau_limit):
    T = [0] * (tau_limit + 1)
    for i in range(1, tau_limit + 1):
        for j in range(i, tau_limit + 1, i):
            T[j] += 1
    win, s = [1] * m, m                       # all-ones seed; tau(1) = 1
    tail = collections.deque(maxlen=2 * P)
    for step in range(repeat_after + 2 * P):
        nxt = s
        tail.append(nxt)
        s += T[nxt] - T[win[step % m]]
        win[step % m] = nxt
    tail = list(tail)
    assert all(tail[i] == tail[i + P] for i in range(len(tail) - P)), \\
        f'm={m}: tail not {P}-periodic'
    g = math.gcd(m, P)
    return [sum(tail[-P:][c::g]) for c in range(g)]

for m in (4, 16, 30, 80, 552):                # m+2 even-m cases, then 2m+3 with 3|m
    row = combined.loc[combined.m == m].iloc[0]
    P = int(row.cycle_length)
    fam = 'm+2 ' if P == m + 2 else '2m+3'
    sums = cycle_class_sums(m, P, int(row.repeat_after), int(row.max_value) + 1)
    print(f'm={m:>4}  P={P:>5} ({fam})  g={math.gcd(m, P)}  '
          f'class sums equal: {len(set(sums)) == 1}  {sums}')
"""
)

code(
    """
# K vs m and mean_τ vs m for the length-(m+1) family.
bt = pd.read_csv(ANA / 'length_mp1_bar_tau.csv')

fig, axes = plt.subplots(1, 2, figsize=(14, 5))
ax = axes[0]
top_K = bt.K.value_counts().head(7)
other = bt[~bt.K.isin(top_K.index)]
ax.scatter(other.m, other.K, s=8, alpha=0.4, c='lightgray', label='other K')
cmap = plt.get_cmap('tab10')
for i, (K, n) in enumerate(top_K.items()):
    sub = bt[bt.K == K]
    ax.scatter(sub.m, sub.K, s=10, alpha=0.8, color=cmap(i), label=f'K={K} (n={n})')
xs = np.linspace(50, bt.m.max(), 200)
for ratio, style in [(4.22, ':'), (9.26, '--')]:
    ax.plot(xs, ratio * xs, 'k' + style, lw=1, alpha=0.7, label=f'K = {ratio}·m')
ax.set_xlabel('m'); ax.set_ylabel('K')
ax.set_title('Realised K vs m — K-reuse plateaus inside the [4.22m, 9.26m] envelope')
ax.legend(fontsize=7, loc='upper left'); ax.grid(alpha=0.3)

ax = axes[1]
ax.scatter(bt.m, bt.bar_tau, s=8, alpha=0.5, c='#1f77b4', label='mean_τ = K/(m+1)')
xs = np.linspace(10, bt.m.max(), 200)
ax.plot(xs, np.log(xs), 'k--', lw=1, label='ln m')
ax.plot(xs, 1.1 * np.log(xs), 'k:', lw=1, label='1.1·ln m')
ax.set_xlabel('m'); ax.set_ylabel('mean_τ')
ax.set_title('mean_τ per length-(m+1) cycle — flat band, no detectable growth')
ax.legend(fontsize=8); ax.grid(alpha=0.3)
plt.tight_layout(); plt.show()

km = bt.K / bt.m
imax, imin = km.idxmax(), km.idxmin()
print(f"cycles: {len(bt)}, distinct K: {bt.K.nunique()}")
print(f"K/m envelope: min {km.min():.2f} (m={bt.loc[imin, 'm']}, K={bt.loc[imin, 'K']}), "
      f"max {km.max():.2f} (m={bt.loc[imax, 'm']}, K={bt.loc[imax, 'K']})")
print(f"band thickness cmax-cmin: median {int((bt.cmax - bt.cmin).median())}, max {int((bt.cmax - bt.cmin).max())}")
print(f"mean_τ: q05 {bt.bar_tau.quantile(0.05):.2f}, median {bt.bar_tau.median():.2f}, "
      f"q95 {bt.bar_tau.quantile(0.95):.2f}, max {bt.bar_tau.max():.2f}")
"""
)

# ---------------------------------------------------------------------------
# §6 8m envelope
# ---------------------------------------------------------------------------

md(
    r"""
## 6. The 8m envelope — cycle values cluster against y = 8m

### Observation

Beyond the exact 8m fixed points (§7), the *non*-fixed-point cycles also
hug the y = 8m line: ~28% of non-fixed cycles have `cycle_min` within ±5%
of 8m, the 90th percentile of `cycle_min/m` is ≈ 8.1, and the absolute max
is ≈ 9.2 — 8m acts as an empirical **upper envelope**, approached from
below.

### Geometry

In the `cycle_value / m` panel below:

- the 8m fixed-point primes (gold stars) sit *exactly* on y = 8;
- consecutive m's sharing one attractor produce **descending arcs** below
  the line — cycle values stay roughly constant while m grows, so the
  ratio drops; a new attractor takes over and the ratio resets back
  near 8.

### Why 8m — direct from §4

The conservation identity `mean_v = m·mean_τ` is the mechanism. A cycle
with mean value ≈ 8m must have temporal-average τ ≈ 8, and τ = 8 is
precisely the τ-class of `2³·prime` — dense at integer magnitudes near 8m
(odd primes near m make `8·prime` a τ=8 number in the cycle's
neighbourhood). Once a cycle drifts into the 8m band the τ-average
self-stabilises around 8; climbing above 8m enters regions with sparser
τ=8 representatives, so the trajectory falls back — hence the
upper-envelope geometry. The fixed-point condition `x = m·τ(x)` (§7) is
the equality limit of the same identity at τ = 8.

### Cycles that literally pass through 8m

Of the m's in the [7.95m, 8.10m) cohort with signatures on disk, ≈29%
have 8m as a literal cycle value (e.g. m=99: values {792, 808} = {8m,
8m+16}; m=125: {1000, 1008, 1022, 1030} ∋ 8m). The other ≈71% orbit near
8m without visiting it.

### Where the band breaks down

In m ∈ [800, 1000) and [1400, 1745] essentially no cycles straddle 8m —
the dominant attractors there (§9 clusters at cycle_max ∈ {6218, 6238,
9406, 10202}) sit *below* 8m, so all m's in their basin do too. The 8m
envelope is the upper limit, not the typical value.

### Basin cross-check

The fourth panel repeats the histogram on the random-seed basin scan
(§11): the same envelope appears (≈26% of finished trials within ±5% of
8m, p90 ≈ 8.0), so the 8m envelope is a property of the dynamics, not a
seed=1 artefact.
"""
)

code(
    """
nf = combined[combined.cycle_length > 1].copy()
fp = combined[combined.cycle_length == 1].copy()

fig, axes = plt.subplots(1, 4, figsize=(20, 5))

# Panel A: cycle values vs m with y = 8m
ax = axes[0]
ax.scatter(nf.m, nf.cycle_min, s=4, alpha=0.4, c='#1f77b4', label='cycle_min')
ax.scatter(nf.m, nf.cycle_max, s=4, alpha=0.4, c='#d62728', label='cycle_max')
xs = np.array([1, combined.m.max()])
ax.plot(xs, 8 * xs, 'k-', lw=1.2, label='y = 8m')
ax.scatter(fp[fp.m > 1].m, fp[fp.m > 1].cycle_min, s=80, marker='*',
           c='gold', edgecolor='black', lw=0.5, label='8m fixed points', zorder=5)
ax.set_xlabel('m'); ax.set_ylabel('cycle value')
ax.set_title('Cycle values vs m (line y = 8m)')
ax.legend(fontsize=8, loc='upper left'); ax.grid(alpha=0.3)

# Panel B: cycle_value / m, slope-8 normalised
ax = axes[1]
ax.scatter(nf.m, nf.cycle_min / nf.m, s=4, alpha=0.4, c='#1f77b4', label='cycle_min / m')
ax.scatter(nf.m, nf.cycle_max / nf.m, s=4, alpha=0.4, c='#d62728', label='cycle_max / m')
ax.axhline(8.0, color='k', lw=1.2, label='y = 8')
ax.scatter(fp[fp.m > 1].m, fp[fp.m > 1].cycle_min / fp[fp.m > 1].m, s=80,
           marker='*', c='gold', edgecolor='black', lw=0.5,
           label='8m fixed points', zorder=5)
ax.set_xlabel('m'); ax.set_ylabel('cycle value / m')
ax.set_title('cycle value / m — upper envelope at 8')
ax.set_ylim(0, 10)
ax.legend(fontsize=8, loc='lower left'); ax.grid(alpha=0.3)

# Panel C: histogram of cycle_min/m peaking at 8 (seed=1)
ax = axes[2]
ratio = (nf.cycle_min / nf.m).values
bins = np.arange(0, 10.05, 0.05)
ax.hist(ratio, bins=bins, color='#1f77b4', edgecolor='none', alpha=0.75)
ax.axvline(8.0, color='k', lw=1.2, label='y = 8m')
ax.set_xlabel('cycle_min / m'); ax.set_ylabel('count')
ax.set_title('Seed = 1: cycle_min / m (non-fixed cycles)')
ax.legend(fontsize=8); ax.grid(alpha=0.3)

# Panel D: same histogram on the T=200-trial random-seed basin scan (§11).
# The basin file may be absent on a fresh checkout; fall back to a placeholder.
ax = axes[3]
basin_path = ANA / 'random_seed_basin.csv'
if basin_path.exists():
    basin = pd.read_csv(basin_path)
    bf = basin[basin.timed_out == 0].copy()
    bratio = (bf.cycle_min / bf.m).values
    ax.hist(bratio, bins=bins, color='#9467bd', edgecolor='none', alpha=0.75)
    ax.axvline(8.0, color='k', lw=1.2, label='y = 8m')
    ax.set_xlabel('cycle_min / m'); ax.set_ylabel('count')
    ax.set_title(f"Random-seed basin: cycle_min / m\\n"
                 f"({len(bf)} trials over {bf.m.nunique()} m's — see §11)")
    ax.legend(fontsize=8); ax.grid(alpha=0.3)
else:
    ax.text(0.5, 0.5, "random_seed_basin.csv not present\\n(see §11 to generate)",
            transform=ax.transAxes, ha='center', va='center', fontsize=10)
    ax.set_title('Random-seed basin: cycle_min / m')
    ax.set_axis_off()

plt.tight_layout(); plt.show()

# Quantitative summary printed alongside the chart.
print(f'non-fixed-point cycles: {len(nf)}')
peak = nf[(nf.cycle_min >= 7.95 * nf.m) & (nf.cycle_min < 8.10 * nf.m)]
print(f'cycle_min in [7.95m, 8.10m): {len(peak)}  ({100 * len(peak) / len(nf):.1f}%)')
band5 = nf[(nf.cycle_min >= 7.6 * nf.m) & (nf.cycle_min <= 8.4 * nf.m)]
print(f'cycle_min within ±5% of 8m: {len(band5)}  ({100 * len(band5) / len(nf):.1f}%)')
print(f'cycle_min/m  p90 ≈ {(nf.cycle_min / nf.m).quantile(0.90):.3f},  max ≈ {(nf.cycle_min / nf.m).max():.3f}')
print(f'cycle_max/m  p90 ≈ {(nf.cycle_max / nf.m).quantile(0.90):.3f},  max ≈ {(nf.cycle_max / nf.m).max():.3f}')

# Of m's in the peak band, how many have 8m as a literal cycle value?
SIG_DIR = ANA / 'cycle_signatures'
def has_8m_value(m):
    p = SIG_DIR / f'{m}.csv'
    if not p.exists():
        return None
    s = pd.read_csv(p)
    return int(8 * m in s['value'].values)

peak_with_sig = peak[peak.m.apply(lambda m: (SIG_DIR / f'{m}.csv').exists())]
exact_hits = int(peak_with_sig.m.apply(has_8m_value).sum())
denom = max(len(peak_with_sig), 1)
print(f'In peak band with signatures on disk ({len(peak_with_sig)} m): '
      f'{exact_hits} cycles literally contain x = 8m '
      f'({100 * exact_hits / denom:.0f}%)')

# Cross-check on the random-seed basin (§11). Same envelope, larger sample.
if basin_path.exists():
    bratio_pd = bf.cycle_min / bf.m
    bband5 = ((bf.cycle_min >= 7.6 * bf.m) & (bf.cycle_min <= 8.4 * bf.m)).sum()
    bexact = (bf.cycle_min == 8 * bf.m).sum()
    print(f'\\nRandom-seed basin (§11): {len(bf)} finished trials over {bf.m.nunique()} m\\'s')
    print(f'  cycle_min within ±5% of 8m: {bband5}  ({100 * bband5 / len(bf):.1f}%)')
    print(f'  cycle_min/m  p90 ≈ {bratio_pd.quantile(0.90):.3f},  max ≈ {bratio_pd.max():.3f}')
    print(f'  cycle_min == 8m exactly: {bexact} trials')
"""
)

# ---------------------------------------------------------------------------
# §7 Fixed points
# ---------------------------------------------------------------------------

md(
    r"""
## 7. Fixed points — the full catalogue

A fixed point (cycle of length 1) is a value the window can hold forever:
all m entries equal x, and the next term is $m \cdot \tau(x) = x$. So fixed
points are exactly the integer solutions of

$$x = m \cdot \tau(x), \qquad\text{equivalently } \tau(qm) = q
\text{ with } q = x/m.$$

### Per-quotient families

Multiplicativity of τ turns each quotient q into a condition on the
prime-factor shape of m. The families are broader than a prime-only
analysis suggests — testing only m ∈ {prime, p², pq} misses most of them:

| q | condition on m | examples |
|---|---|---|
| 1 | m = 1 | x = 1 |
| 3 | 3m = p² ⇒ m = 3 only | x = 9 (not reached by seed=1) |
| 8 | m an odd prime | x = 8m: m = 127, 167, 211, 613, 733, 1103, 1117, 1291 all observed |
| 12 | m a prime > 3, **and also m ∈ {6, 8, 9}** | x = 72, 96, 108 at the composite m's |
| 16 | **m = 8p (p odd prime) or m = 2¹¹** | x = 384 (m=24), x = 640 (m=40), x = 32768 (m=2048) |
| 24 | m = p² (p odd ≠ 3), **and also m ∈ {3p, 4p, 36, 256}** | x = 600 (m=25), x = 360 (m=15), x = 480 (m=20), … |

### Fixed points are near-universal

Sieving $x = m\,\tau(x)$ exhaustively for $x \le M^*(1549) = 277{,}200$
(complete for m ≤ 1549; catalogue `analysis/fixed_points_full.csv` extends
to m ≤ 2100):

- **~91% of m ≤ 1549 have at least one fixed point** (789 m's have exactly
  one, 557 have two, 65 have three).
- **Every 8m-prime has a second, unvisited fixed point at 12m**
  (τ(2²·3·p) = 12): m=127 has {1016, 1524}, m=1291 has {10328, 15492}, ….
  So "every prime m > 3 has a length-1 cycle" is structurally trivial —
  every such prime has *two*. The open question was never existence, only
  reachability.
- **Seed=1, when it lands on a fixed point at all (9 of ~1411 m's that
  have one), always lands on the smallest.**
- The ~138 m's with *no* fixed point skew τ-rich (multiples of 9, 16, 64:
  18, 27, 30, 45, 63, 64, 72, …) — a divisibility obstruction that looks
  characterisable (§12).
- Phase-D prediction: **m = 2048 has fixed points {32768, 53248, 57344}**
  (q = 16, 26, 28) — a concrete target when the scan extends past 2000.

### Reachability

Existence ≠ observation: the dynamics almost never *selects* a fixed
point (9 of ~1411). The random-seed basin scan (§11) found the first
direct evidence that unvisited fixed points are reachable at all: at
m=103 and m=179, 1/200 random seeds land on x = 8m even though seed=1
resolves to a multi-element cycle. The interesting question is why the
selection probability is so small — and whether the basin of a fixed
point is ever more than the point itself plus a thin shell (§12).
"""
)

code(
    """
# Full fixed-point catalogue: x = m·τ(x) sieved over x ≤ 277,200 (complete for m ≤ 1549).
fpf = pd.read_csv(ANA / 'fixed_points_full.csv')
M_COMPLETE = 1549
fpc = fpf[fpf.m <= M_COMPLETE]
counts = fpc.groupby('m').size().reindex(range(1, M_COMPLETE + 1), fill_value=0)
print(f'm ≤ {M_COMPLETE} with ≥1 fixed point: {(counts > 0).sum()} / {M_COMPLETE} '
      f'({100 * (counts > 0).mean():.1f}%)')
print('fixed points per m:', dict(counts.value_counts().sort_index()))

# Seed=1 landings: always the smallest available fixed point?
seed1_fp = combined[combined.cycle_length == 1]
rows = []
for _, r in seed1_fp.iterrows():
    avail = fpc[fpc.m == r.m].x.sort_values().tolist()
    rows.append((int(r.m), int(r.cycle_min), avail, int(r.cycle_min) == (avail[0] if avail else -1)))
landed = pd.DataFrame(rows, columns=['m', 'landed_x', 'available_x', 'is_smallest'])
print('\\nseed=1 fixed-point landings (is_smallest should be True throughout):')
print(landed.to_string(index=False))

fig, axes = plt.subplots(1, 2, figsize=(14, 5), gridspec_kw={'width_ratios': [3, 1]})
ax = axes[0]
cmap = plt.get_cmap('tab10')
for i, q in enumerate(sorted(fpc.q.unique())):
    sub = fpc[fpc.q == q]
    ax.scatter(sub.m, sub.x / sub.m, s=10, alpha=0.6, color=cmap(i % 10), label=f'q = {q} (n={len(sub)})')
ax.scatter(seed1_fp[seed1_fp.m > 1].m, seed1_fp[seed1_fp.m > 1].cycle_min / seed1_fp[seed1_fp.m > 1].m,
           s=120, marker='*', c='gold', edgecolor='black', lw=0.6, zorder=5, label='visited by seed=1')
ax.set_xlabel('m'); ax.set_ylabel('x / m  (= τ(x) = q)')
ax.set_title(f'All fixed points x = m·τ(x), m ≤ {M_COMPLETE} — seed=1 visits only the gold stars')
ax.legend(fontsize=7, ncol=2); ax.grid(alpha=0.3)

ax = axes[1]
vc = counts.value_counts().sort_index()
ax.bar(vc.index.astype(str), vc.values, color='#1f77b4', edgecolor='black', lw=0.5)
for i, v in enumerate(vc.values):
    ax.text(i, v + 8, str(v), ha='center', fontsize=9)
ax.set_xlabel('fixed points per m'); ax.set_ylabel("number of m's")
ax.set_title('Fixed-point multiplicity')
ax.grid(alpha=0.3, axis='y')
plt.tight_layout(); plt.show()
"""
)

# ---------------------------------------------------------------------------
# §8 Sustained ceiling
# ---------------------------------------------------------------------------

md(
    r"""
## 8. The sustained ceiling M*(m) and the four-band picture

### Definition and computation

$M^*(m) = \max\{M : M \le m\,\tau(M)\}$ (§1). Equivalently
$M^*(m) = \max\{M : \lceil M/\tau(M)\rceil \le m\}$, so one τ-sieve over
$[1, 4m_{\max}^2]$ plus a prefix-max gives the whole locus
(`analysis/build_sustained_ceiling.py` → `analysis/sustained_ceiling.csv`).

The fixed-point condition `x = m·τ(x)` (§7) is the **equality boundary**
of this locus: fixed points are the integer points *on* the curve
$M = m\,\tau(M)$, while $M^*(m)$ is the largest M weakly below it — and
the two typically differ (M*(127) = 7,560 vs the visited fixed point
1,016; ratio 7.4×, growing to 19× at m=1291).

### Headline numbers

- `M*(1549) = 277,200` (= 2⁴·3²·5²·7·11, τ = 180) vs the worst-case bound
  `4·1549² = 9,597,604` — a 35× gap; the median `4m²/M*(m)` over
  m ∈ [200, 1549] is **26×**.
- `M*(569) = 65,520`; m=569's observed cycle band sits near 4,744 — two
  orders of magnitude below the sustained ceiling.
- The M's attaining M*(m) are highly composite numbers; `M_at(m)` is
  essentially a bottleneck index over HCNs (OEIS candidate, §12).

### Asymptotics

Log-log slope of M*(m): 1.43 over m ∈ [2, 1549], decaying to 1.30 over
the top half. Wigert's theorem
($\max_{n \le N} \tau(n) \sim \exp((\ln 2 + o(1))\ln N / \ln\ln N)$)
predicts $M^*(m) \sim m^{1 + \Theta(1/\ln\ln m)}$ — between linear and
quadratic with the exponent slowly decaying toward 1, consistent with the
observed decay. The 4m² bound corresponds to slope 2.

### The four-band picture

| anchor | scale at m ≈ 1549 | / (m·ln m) |
|---|---|---:|
| cycle_max (§3) | ≈ 1.13·m·ln m | 1.13 |
| max_value (§3) | ≈ 2.13·m·ln m | 2.13 |
| M*(m) | 277,200 | ≈ 24 |
| 4m² | 9,597,604 | ≈ 845 |

The seed=1 trajectory leaves the entire stratum `[max_value, M*(m)]`
unvisited — over an order of magnitude of sustainable state space sits
above the transient peak. That slack is the wedge for the basin probes
(§11, §12): a window seeded at M*(m) starts far above anything the
all-ones seed ever reaches.
"""
)

code(
    """
sc = pd.read_csv(ANA / 'sustained_ceiling.csv')
merged = combined.merge(sc[['m', 'M_star']], on='m', how='left')

fig, ax = plt.subplots(figsize=(10, 6))
ax.scatter(merged.m, merged.cycle_max, s=4, alpha=0.5, c='#1f77b4', label='cycle_max')
ax.scatter(merged.m, merged.max_value, s=4, alpha=0.5, c='#d62728', label='max_value (transient peak)')
ax.scatter(merged.m, merged.M_star, s=4, alpha=0.5, c='#2ca02c', label='M*(m) sustained ceiling')

xs = np.linspace(2, merged.m.max(), 400)
ax.plot(xs, xs, 'k--', alpha=0.4, label='m')
ax.plot(xs, xs * np.log(xs), 'k-', alpha=0.4, label='m·ln m')
ax.plot(xs, 4 * xs ** 2, 'k:', alpha=0.6, label='4m²  (worst-case ceiling)')

ax.set_xscale('log'); ax.set_yscale('log')
ax.set_xlabel('m (log)'); ax.set_ylabel('value (log)')
ax.set_title('Four-band picture: cycle ≪ transient ≪ M*(m) ≪ 4m²')
ax.legend(fontsize=8, loc='upper left'); ax.grid(alpha=0.3, which='both')
plt.tight_layout(); plt.show()

mask = merged.m >= 200
mv_ratio = (merged.loc[mask, 'max_value'] / merged.loc[mask, 'M_star']).describe(percentiles=[0.05, 0.5, 0.95])
print('max_value / M*(m), m ≥ 200:'); print(mv_ratio)
m4_ratio = ((4 * merged.loc[mask, 'm'] ** 2) / merged.loc[mask, 'M_star']).median()
print(f'4m² / M*(m) median (m ≥ 200): {m4_ratio:.1f}×')
"""
)

# ---------------------------------------------------------------------------
# §9 Attractor catalogue
# ---------------------------------------------------------------------------

md(
    """
## 9. The attractor catalogue

### Multiset is the wrong unit

Every resolved m has a **unique** value→count multiset — m's that visit
the same set of cycle values generally have different cycle lengths, so
the per-value frequencies rebalance (e.g. m=24 vs m=25: same value set
{180, …, 206} but cycle lengths 101 vs 445). The right clustering unit is
the **value set**: the distinct cycle values, ignoring multiplicities.

### Clustering by value set

~300 distinct value sets cover all resolved m's: ~75 with ≥2 members, the
rest singletons (predominantly large-m, jittery trajectories). Top
clusters by size (catalogue `analysis/attractors.csv` /
`value_set_clusters.csv`, built by `analysis/build_attractors.py`):

| id  | size | distinct | cycle_min | cycle_max | m range       |
|-----|------|----------|-----------|-----------|---------------|
| 208 | 196  | 4        | 6210      | 6238      | 767..1296     |
| 241 | 130  | 4        | 9394      | 9406      | 1114..1496    |
| 103 |  74  | 4        | 2624      | 2638      | 330..582      |
| 142 |  71  | 5        | 5130      | 5158      | 579..981      |
|  72 |  50  | 6        | 1380      | 1402      | 174..287      |

The largest cluster covers ~13.5% of all resolved m's. These clusters are
exactly the K-attractor plateaus of §5 seen from the value side (cluster
208 is K=6242, cluster 241 is K=9410, …). Cluster 241 covers most of
m ≥ 1114, suggesting attractor consolidation at large m.
"""
)

code(
    """
clusters = pd.read_csv(ANA / 'value_set_clusters.csv')
m_to_cluster = {}
for _, row in clusters.iterrows():
    members = str(row['member_m_list']).split('|') if '|' in str(row['member_m_list']) else str(row['member_m_list']).split(' ')
    for tok in members:
        try:
            m_to_cluster[int(tok)] = (int(row['attractor_id']), int(row['size']))
        except ValueError:
            continue

combined['cluster_id'] = combined['m'].map(lambda m: m_to_cluster.get(m, (-1, 0))[0])
combined['cluster_size'] = combined['m'].map(lambda m: m_to_cluster.get(m, (-1, 0))[1])
print(f'm with cluster assignment: {(combined.cluster_id >= 0).sum()} / {len(combined)}')
print('top 5 clusters by size:')
print(clusters.nlargest(5, 'size')[['attractor_id', 'size', 'cycle_min', 'cycle_max']])

fig, ax = plt.subplots(figsize=(10, 5.5))
big = combined[combined.cluster_size >= 10]
small = combined[(combined.cluster_size > 0) & (combined.cluster_size < 10)]
miss = combined[combined.cluster_id < 0]
sc = ax.scatter(big.m, big.cycle_min, s=8, c=big.cluster_id, cmap='tab20', alpha=0.7, label='cluster size ≥ 10')
ax.scatter(small.m, small.cycle_min, s=6, c='lightgray', alpha=0.5, label='cluster size < 10')
if len(miss):
    ax.scatter(miss.m, miss.cycle_min, s=6, c='black', marker='x', alpha=0.6, label='no cluster')
ax.set_xlabel('m'); ax.set_ylabel('cycle_min'); ax.set_yscale('log')
ax.set_title('cycle_min by m, coloured by attractor cluster id')
ax.legend(loc='upper left', fontsize=8); ax.grid(alpha=0.3, which='both')
plt.tight_layout(); plt.show()
"""
)

md(
    r"""
### 9b. Attractor 48 and the `(2m − 199)(m + 1)` harmonic family

One attractor breaks the k=1 resonance pattern in a structurally
interesting way. In the §2.3 plot a clear curve sits above the m+1 band
over m ∈ [102, 133]; its exact form is

> **`cycle_length = (2m − 199)(m + 1)`** — bit-exact for all 20 member
> m's, residual 0.

Equivalently `cycle_length = k(m+1)` with `k = 2m − 199` (always odd).
Every other multi-member attractor with `(m+1) | cycle_length` has
constant k = 1 (occasionally 2); attractor 48 (value set {810, 812, 818,
820, 822, 824, 828, 834, 838}, 9 values) is the only one surveyed whose
harmonic index *grows with m*: the orbit traverses its value multiset
(2m − 199) times before closing.

### Mechanism — closed-form count polynomials

With k = 2m − 199, the per-value visit counts are exact polynomials in k:

| value v | τ(v) | count(v) |
|--------:|-----:|----------|
| 810, 812, 818, 820, 828 | 20, 12, 4, 12, 18 | k − 1 (each) |
| 822 | 8 | 204 − 2k |
| 824 | 8 | (205 − 3k)/2 |
| 834 | 8 | (−k² + 204k − 607)/2 |
| 838 | 4 | (k − 1)(k − 2) |

Counts sum to k(m+1) and satisfy conservation `Σ v·c(v) = m·Σ τ·c(v)`
bit-exactly for every k. **The binding constraint is count(824) ≥ 0 ⇒
k ≤ 67 ⇒ m ≤ 133**: above m=133 the attractor *ceases to exist* as an
integer solution — a clean example of a cycle-existence Diophantine
constraint cutting off an attractor at an exact m. The constant 199 is
set by the multiset's expansion geometry: 199 = 2·m_min − 1 where
m_min = 100 is where the formula's trivial k=1 root lies.

As m grows along the family, conservation (`mean_τ = 824/m`, sliding from
8.08 to 6.20) forces the orbit to lean ever harder on the τ=4 value 838 —
hence the quadratic count (k−1)(k−2).
"""
)

code(
    r"""
# §9b: identify the {810..838} attractor population, fit the (2m-199)(m+1)
# curve bit-exactly, and overplot it on the cycle_length scatter.
target = combined[(combined.cycle_min == 810) & (combined.cycle_max == 838) &
                  (combined.distinct_tail_values == 9)].copy()
target['k'] = 2 * target.m - 199
target['predicted'] = target.k * (target.m + 1)
target['residual'] = target.cycle_length.astype(int) - target.predicted
print(f"attractor 48 ({{810..838}}, 9 distinct values): {len(target)} m's, m∈[{target.m.min()},{target.m.max()}]")
print(f"max |cycle_length - (2m-199)(m+1)|: {target.residual.abs().max()}  (0 = bit-exact)")
print(f"k = 2m - 199 ranges over odd integers {target.k.min()}..{target.k.max()}")

fig, ax = plt.subplots(figsize=(10, 5.5))
for pop, sub in combined.groupby('population'):
    ax.scatter(sub.m, sub.cycle_length, s=6, alpha=0.35, c=colors[pop], label=pop)

# Highlight attractor 48 members and overlay the closed-form curve.
ax.scatter(target.m, target.cycle_length, s=40, facecolors='none',
           edgecolors='#9467bd', linewidths=1.5, label='attractor 48 (n=20)')
ms_curve = np.arange(101, 134)
ax.plot(ms_curve, (2*ms_curve - 199) * (ms_curve + 1), '-', color='#9467bd', lw=1.2,
        label='(2m − 199)(m + 1)')

xs = np.linspace(1, combined.m.max(), 300)
ax.plot(xs, xs + 1, 'k-', linewidth=0.8, alpha=0.5, label='cycle_length = m+1')
ax.set_yscale('log'); ax.set_xscale('log')
ax.set_xlim(50, 250); ax.set_ylim(50, 2e4)
ax.set_xlabel('m (log)'); ax.set_ylabel('cycle_length (log)')
ax.set_title('§9b: attractor 48 — cycle_length = (2m − 199)(m + 1) for k=5..67')
ax.legend(fontsize=8, loc='upper left'); ax.grid(alpha=0.3, which='both')
plt.tight_layout(); plt.show()

# Verify the per-value count formulae bit-exactly across the 20 m's.
SIG_DIR = ANA / 'cycle_signatures'
def cnt_pred(v, k):
    if v in (810, 812, 818, 820, 828):
        return k - 1
    if v == 822:
        return 204 - 2*k
    if v == 824:
        return (205 - 3*k) // 2
    if v == 834:
        return (-k*k + 204*k - 607) // 2
    if v == 838:
        return (k - 1) * (k - 2)
    raise ValueError(v)

mismatches = 0
for _, row in target.iterrows():
    sig = pd.read_csv(SIG_DIR / f'{int(row.m)}.csv').set_index('value')
    k = int(row.k)
    for v in (810, 812, 818, 820, 822, 824, 828, 834, 838):
        actual = int(sig.loc[v, 'count'])
        pred = cnt_pred(v, k)
        if actual != pred:
            mismatches += 1
            print(f"  mismatch m={int(row.m)} v={v}: actual={actual} pred={pred}")
print(f"per-value count formulae verified across all 20 m's: {mismatches} mismatches "
      f"(0 = all 9 closed-form formulae are bit-exact)")
"""
)

md(
    r"""
### §9b validation in the random-seed basin

Cross-checking against `analysis/random_seed_basin.csv` (§11) probes two
questions: does the curve hold for m's seed=1 *missed*, and does the same
value set support *other* harmonic branches?

**Findings** (all bit-exact):

- **Primary branch — `(2m − 199)(m + 1)`, k odd**: random seeds reach the
  primary branch for *every* m ∈ [102, 133] — all 32 m's, including the
  12 that seed=1 missed. The structural [102, 133] window predicted by
  the count-formula non-negativity constraints is therefore the *true*
  extent of this attractor's primary resonance.
- **Secondary branch — `(2m − 182)(m + 1)`, k even**: random seeds expose
  a second harmonic family on the same value set (five trials at m=101,
  113, 115, 116, 117): same 9-value multiset, same conservation law,
  different count multiset, 1.5–2× longer cycle. The 17-step shift
  between the branches' k-values (199 − 182) is unexplained.
- **Tertiary singleton at m=100** (cycle_length = 606 = 6·101). One trial
  only — possibly a third branch, possibly a sampling fluke.
"""
)

code(
    r"""
# §9b validation: load random-seed basin, find attractor 48 hits, plot
# cycle_length vs m with both (2m-199)(m+1) and (2m-182)(m+1) curves overlaid.
basin_path = ANA / 'random_seed_basin.csv'
if not basin_path.exists():
    print(f'{basin_path} not present — skip random-seed cross-check.')
else:
    basin = pd.read_csv(basin_path)
    done = basin[basin.timed_out == 0].copy()
    a48 = done[(done.cycle_min == 810) & (done.cycle_max == 838) &
               (done.distinct_tail_values == 9)].copy()
    a48['cl'] = a48.cycle_length.astype(int)
    # Branch label: X such that cycle_length = (2m - X)(m+1).
    a48 = a48[a48.cl % (a48.m + 1) == 0].copy()
    a48['k_actual'] = a48.cl // (a48.m + 1)
    a48['X'] = (2 * a48.m - a48.k_actual).astype(int)

    print(f'random-seed trials in attractor 48: {len(a48)} / {len(done)} finished trials')
    print()
    print('Branch X populations:')
    for X, sub in a48.groupby('X'):
        parity = 'odd' if X % 2 == 1 else 'even'
        print(f"  (2m - {X})(m+1)  [{parity}]: {len(sub)} trials, "
              f"m ∈ [{sub.m.min()}, {sub.m.max()}], "
              f"distinct m's: {sub.m.nunique()}, k range {sub.k_actual.min()}..{sub.k_actual.max()}")

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5),
                             gridspec_kw={'width_ratios': [3, 1]})

    ax = axes[0]
    # Random-seed trials, coloured by branch.
    for X, color, lbl in [(199, '#9467bd', 'primary (2m−199)(m+1), k odd'),
                          (182, '#e377c2', 'secondary (2m−182)(m+1), k even'),
                          (194, '#7f7f7f', 'singleton X=194 at m=100')]:
        sub = a48[a48.X == X]
        if len(sub):
            ax.scatter(sub.m, sub.cl, s=22, alpha=0.55, c=color, label=lbl,
                       edgecolors='none')
    other = a48[~a48.X.isin([199, 182, 194])]
    if len(other):
        ax.scatter(other.m, other.cl, s=18, alpha=0.5, c='#bcbd22',
                   label=f'other branches (n={len(other)})', marker='x')

    # Closed-form curves.
    mm_p = np.arange(101, 134)
    ax.plot(mm_p, (2*mm_p - 199) * (mm_p + 1), '-', color='#9467bd', lw=1.3, alpha=0.7)
    mm_s = np.arange(101, 134)
    ax.plot(mm_s, (2*mm_s - 182) * (mm_s + 1), '--', color='#e377c2', lw=1.3, alpha=0.7)

    # seed=1 attractor 48 members (from §9b).
    seed1 = combined[(combined.cycle_min == 810) & (combined.cycle_max == 838) &
                     (combined.distinct_tail_values == 9)]
    ax.scatter(seed1.m, seed1.cycle_length, marker='x', c='cyan', s=80, lw=2.0,
               label=f'seed=1 (n={len(seed1)}, primary only)')

    ax.set_yscale('log')
    ax.set_xlabel('m'); ax.set_ylabel('cycle_length (log)')
    ax.set_title('§9b cross-check: attractor 48 cycle lengths from random seeds')
    ax.legend(fontsize=8, loc='upper left'); ax.grid(alpha=0.3, which='both')

    # Sister panel: primary-branch m-coverage in attractor 48 over the
    # mathematically-allowed window [102, 133].
    ax2 = axes[1]
    seed1_ms = set(seed1.m.astype(int).tolist())
    primary_ms = set(a48[a48.X == 199].m.astype(int).tolist())
    cats = ['seed=1 ∩\nrandom', 'random\nonly', 'seed=1\nonly', 'never\nin [102,133]']
    n_both = len(seed1_ms & primary_ms)
    n_rng_only = len(primary_ms - seed1_ms)
    n_seed1_only = len(seed1_ms - primary_ms)
    n_never = len(set(range(102, 134)) - primary_ms - seed1_ms)
    counts = [n_both, n_rng_only, n_seed1_only, n_never]
    colors_bar = ['#9467bd', '#e377c2', 'cyan', 'lightgray']
    ax2.bar(cats, counts, color=colors_bar, edgecolor='black', lw=0.8)
    for i, c in enumerate(counts):
        ax2.text(i, c + 0.3, str(c), ha='center', fontsize=10, fontweight='bold')
    ax2.set_ylabel("m's reaching primary branch")
    ax2.set_title('primary-branch coverage (m∈[102,133])')
    ax2.grid(alpha=0.3, axis='y')

    plt.tight_layout(); plt.show()

    # Summary numerics.
    print()
    primary_ms = set(a48[a48.X == 199].m.astype(int).tolist())
    print(f"seed=1 primary-branch m's (n={len(seed1_ms)}): {sorted(seed1_ms)}")
    print(f"random-seed primary-branch m's added beyond seed=1 "
          f"(n={len(primary_ms - seed1_ms)}): {sorted(primary_ms - seed1_ms)}")
    print(f"random-seed secondary-branch m's (X=182, even k): "
          f"{sorted(a48[a48.X == 182].m.unique().tolist())}")
    print(f"random-seed singleton at X=194: "
          f"{sorted(a48[a48.X == 194].m.unique().tolist())}")
"""
)

# ---------------------------------------------------------------------------
# §10 Outliers
# ---------------------------------------------------------------------------

md(
    """
## 10. Wide-band outliers and runaway cycles

Two flags pick out the same population: cycle range
`cycle_max − cycle_min > 100` or `distinct_tail_values > 50` (the
**wide-band outliers**, 74 m's), and `cycle_length > 10·m` (the
**runaway cycles**, 96 m's, λ up to 1.1·10¹⁰ at m=1244). They cluster at
m ∈ {532, 534, 601, 607, 630, 738–751, 1242–1254, …}.

These are τ-spectrum events, not algorithm pathologies: the cycle spans
enough of the integer line that τ's roughness dominates — the
value–τ anticorrelation washes out (ρ ≈ 0, §4 table), and the cycle has
to sample thousands of distinct values before the multiset balances the
conservation law. They are also the m's that reopen the `cycle_max/(m·ln
m)` band in §3 and dominate scan wall-clock. Per-m tables:
`analysis/cycle_value_tau_structure.csv`.
"""
)

code(
    """
fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
rng = (combined.cycle_max - combined.cycle_min).values
axes[0].scatter(combined.m, rng, s=4, alpha=0.5, c='#1f77b4')
axes[0].set_xlabel('m'); axes[0].set_ylabel('cycle_max − cycle_min')
axes[0].set_title('Cycle range by m')
axes[0].set_yscale('symlog')
axes[0].grid(alpha=0.3)

axes[1].scatter(combined.m, combined.distinct_tail_values, s=4, alpha=0.5, c='#d62728')
axes[1].set_xlabel('m'); axes[1].set_ylabel('distinct_tail_values')
axes[1].set_title('Distinct tail values by m')
axes[1].set_yscale('symlog')
axes[1].grid(alpha=0.3)
plt.tight_layout(); plt.show()

wide = combined[(rng > 100) | (combined.distinct_tail_values > 50)]
print(f'wide-band outliers (range>100 OR distinct>50): {len(wide)} m values')
print('first 30:', wide.m.head(30).tolist())
runaway = combined[combined.cycle_length > 10 * combined.m]
print(f'runaway cycles (λ > 10·m): {len(runaway)} m values; '
      f'longest λ = {int(runaway.cycle_length.max()):,} at m={int(runaway.loc[runaway.cycle_length.idxmax(), "m"])}')
"""
)

# ---------------------------------------------------------------------------
# §11 Basin scans
# ---------------------------------------------------------------------------

md(
    r"""
## 11. Random-seed basin scans

Everything above is built from one deterministic trajectory per m
(seed = all-ones window). The basin scan
(`analysis/build_random_seed_basin.py` → `analysis/random_seed_basin.csv`)
maps the wider attractor landscape: T = 200 trials per m across 106 m's,
each trial's window seeded by m independent draws from
`round(LogNormal(ln(m·ln m), 0.71))` — centred on the cycle band, with a
central-95% factor-16 spread. (T is the trial count per m — unrelated to
the cycle invariant K of §5.)

### Headline findings

- **The seed=1 catalogue materially undercounts attractors**: 141 value
  sets (47% on top of the ~300-entry seed=1 catalogue) are visible only
  to non-trivial seeds.
- **Basin multiplicity is the norm**: at any given m the basin reaches a
  median of 4 distinct length-(m+1) K-attractors (max 8) and up to 22
  distinct value sets (m=289).
- **The K-attractor catalogue more than doubles**: 60 → 135 distinct K's
  over the length-(m+1) trials, with basin-only K's living on tighter
  m-windows than the seed=1 favourites.
- **The m+1 dominance is partly a seed=1 artefact**: the m+1 share of
  basin trials swings 15–83% by m bucket (vs 52% for seed=1); random
  seeds reveal a much richer cycle-length distribution, with m+2 cycles
  common at small m.
- **The 4m floor and 9m ceiling are basin-robust** under log-normal
  seeds: basin q05/q95 of K/m stay within ≈[4.6, 8.7] at large m; the
  admissible minimum K/m ≈ 2 is never reached. The floor and ceiling are
  properties of the dynamics over a wide seed class — but not of the
  admissibility structure (§5).
- **Fixed-point reachability** (§7): the known 8m fixed-point primes are
  hit frequently by random seeds (15–151 of 200 trials); for primes whose
  seed=1 misses the fixed point, m=103 and m=179 each landed 1/200 trials
  on x = 8m — first direct evidence that the unvisited fixed points are
  reachable, with basin measure ~5·10⁻³ at this σ. Other sampled primes
  recorded zero hits at T = 200.

### Caveats

Residual timeouts (12.9%) cluster on large-m runaway-cycle trials; the
pre-2026-05-06 u16 value clamp affected some early `max_value` records
(fixed — window is u32 now; affected rows flagged for re-run). σ = 0.71
is a single point in seed-distribution space: the floor/ceiling
robustness claim is conditional on the log-normal scale, and a low-seed
scan (e.g. LogNormal(ln 2m, 0.5)) is the open discriminator for the
floor (§12).
"""
)

code(
    """
basin_path = ANA / 'random_seed_basin.csv'
if not basin_path.exists():
    print(f'{basin_path} not present — '
          'run `python analysis/build_random_seed_basin.py` to generate it.')
else:
    basin = pd.read_csv(basin_path)
    finished = basin[basin.timed_out == 0].copy()
    print(f'basin trials: total={len(basin)}, finished={len(finished)}, '
          f'timeouts={int((basin.timed_out == 1).sum())}')

    fig, axes = plt.subplots(
        3, 1, figsize=(18, 18), dpi=130,
        gridspec_kw={'height_ratios': [4, 4, 1]},
        constrained_layout=True,
    )

    def _plot_heatmap(ax, df, m_lo, m_hi, title):
        # Linear m bins, one bin per m (or close to it) for max resolution.
        n_m = max(1, m_hi - m_lo + 1)
        m_edges = np.linspace(m_lo - 0.5, m_hi + 0.5, min(n_m, 800) + 1)
        cmin_lo = float(df.cycle_min.min())
        cmin_hi = float(df.cycle_min.max())
        c_edges = np.linspace(cmin_lo, cmin_hi, 401)
        H, _, _ = np.histogram2d(df.m, df.cycle_min,
                                 bins=[m_edges, c_edges])
        im = ax.pcolormesh(m_edges, c_edges, H.T,
                           norm=LogNorm(vmin=max(1, H[H > 0].min() if H.any() else 1),
                                        vmax=max(1, H.max())),
                           cmap='magma', shading='auto')
        fig.colorbar(im, ax=ax, label='trial count (log)',
                     shrink=0.9, pad=0.01)
        ax.set_xlim(m_lo - 0.5, m_hi + 0.5)
        ax.set_ylim(cmin_lo, cmin_hi)
        ax.set_ylabel('cycle_min', fontsize=13)
        ax.set_title(title, fontsize=15)
        ax.grid(alpha=0.3); ax.tick_params(labelsize=11)

    if len(finished) > 0:
        m_min = max(1, int(finished.m.min()))
        m_max = int(finished.m.max())
        _plot_heatmap(axes[0], finished, m_min, m_max,
                      'Random-seed basin: where do orbits land? (full range)')

        zoom = finished[(finished.m >= 1) & (finished.m <= 200)]
        if len(zoom) > 0:
            _plot_heatmap(axes[1], zoom, max(1, int(zoom.m.min())),
                          min(200, int(zoom.m.max())),
                          'Random-seed basin: zoom m ∈ [1, 200]')
        else:
            axes[1].text(0.5, 0.5, 'no finished trials in m ∈ [1, 200]',
                         ha='center', va='center', transform=axes[1].transAxes)
            axes[1].set_axis_off()

    ax = axes[2]
    distinct_per_m = (finished
                      .groupby('m')['value_set_hash']
                      .nunique()
                      .reset_index(name='n_attractors'))
    ax.bar(distinct_per_m.m, distinct_per_m.n_attractors,
           width=5, color='#1f77b4', edgecolor='none', align='center')
    # seed=1 sees exactly one attractor per m by construction; show that as a
    # dashed reference at y=1.
    ax.axhline(1.0, ls='--', color='gray', alpha=0.5,
               label='seed=1 (single attractor)')
    ax.set_xlabel('m', fontsize=13)
    ax.set_ylabel('distinct\\nattractors', fontsize=12)
    ax.legend(fontsize=10, loc='upper left'); ax.grid(alpha=0.3, axis='y')
    ax.tick_params(labelsize=11)

    plt.show()

    # Cross-check vs §7: any m where the heatmap puts mass on
    # cycle_min == 8m while seed=1 resolved to a multi-element cycle is direct
    # evidence that the unvisited fixed point is reachable.
    fixed_path = ANA / 'fixed_points.csv'
    primes_8m_hits = []
    if fixed_path.exists():
        fp = pd.read_csv(fixed_path)
        # Look at every m we scanned, not just known fixed-point primes.
        for m, grp in finished.groupby('m'):
            seed1_row = combined[combined.m == m]
            if seed1_row.empty:
                continue
            seed1_cmax = int(seed1_row.iloc[0]['cycle_max'])
            seed1_cmin = int(seed1_row.iloc[0]['cycle_min'])
            seed1_distinct = int(seed1_row.iloc[0]['distinct_tail_values'])
            hits_8m = ((grp.cycle_min == 8 * m) & (grp.cycle_max == 8 * m)).sum()
            if hits_8m > 0 and seed1_distinct > 1:
                primes_8m_hits.append({
                    'm': m,
                    'random_seed_8m_hits': int(hits_8m),
                    'random_seed_total': len(grp),
                    'seed1_cycle_min': seed1_cmin,
                    'seed1_cycle_max': seed1_cmax,
                    'seed1_distinct': seed1_distinct,
                })
    if primes_8m_hits:
        print('\\nm where random seeds hit the length-1 cycle at x = 8m '
              'but seed=1 did not (§7 reachability evidence):')
        print(pd.DataFrame(primes_8m_hits).to_string(index=False))
    else:
        print('\\nno new x=8m hits beyond seed=1 in this sample.')
"""
)

# ---------------------------------------------------------------------------
# §12 Further work
# ---------------------------------------------------------------------------

md(
    r"""
## 12. Further work

### Mathematics

- **The τ-deficit / quasi-equilibrium question.** If visited values were
  τ-typical of their height, the wandering height would equilibrate at
  `v* = m·(ln v* + 2γ − 1)` (Lambert-W; v*/m ≈ 9.7 at m=1500). The
  observed band locks in *below* that (median mean_τ ≈ 6.8, declining),
  and `K ≈ 455 + 6.40·m` suggests mean_τ → ~6.4 constant against ln m
  growth. These are different predictions and don't need m=10⁴ scans to
  discriminate: instrument the transient (the `steps_to_lock_in` hooks)
  to sample `(v, τ(v))` during wandering and compare visited-τ to
  `ln v + 2γ − 1` at the same height; companion τ-sieve statistic of
  mean τ over S(K) members near height v.
- **Why is K/m ≤ 9.26?** The ceiling is dynamical (§5): whatever pins it
  must involve the orbit's wandering height, not level-set combinatorics
  alone. A model of the transient + the admissibility set should
  determine the realised K.
- **Lock-in as nucleation.** Hypothesis: the window gradually entrains
  into one S(K) (purity ramps from mixed to 100%), and the wandering time
  μ ~ 1/P(nucleation per step). Measure window "purity" backwards from
  lock-in for a few dozen m's; a mean-field nucleation model could
  *predict* the μ ~ m^5.3 exponent and identify runaway m's in advance —
  i.e. how to size the next scan phase without running it.
- **The ~138 fixed-point-free m's** skew τ-rich (multiples of 9, 16,
  64…). `m | x ∧ τ(x) = x/m` failing for all x ≤ M*(m) is a divisibility
  obstruction that looks characterisable — a clean standalone lemma.
- **Parity → Δ=4.** Prove that the minimal spacing between same-parity
  K's with populated S(K) is typically 4, formalising the dominant-K
  spacing in the m+2 family.
- **Class-sum invariant follow-through** (§5): for g = gcd(m, P) > 1 the
  position-class value sums are equal. Does this constrain the m+2
  family's two "linker" entries — e.g. must they land in opposite
  position-classes, and does the balance condition explain the Δ=4
  dominant-K split? Only 5 cycles verified so far; sweep all even-m m+2
  and 3|m 2m+3 signatures.
- **Is the K catalogue saturating?** 60 distinct seed=1 K's at m ≤ 1788
  (135 in the basin). Does the count grow with m or is it bounded? An
  m = 10⁴ scan would discriminate — and also separate `mean_τ` bounded
  vs ~1.1·ln m (§5 vs §4).

### Analysis on existing data

- **Per-outlier table** for the 74 wide-band m's with prime-factor
  structure of the integers in the cycle band (currently only bucketed).
- **Linear-segment detector** over `cycle_min(m)`: flag runs with
  R² ≥ 0.99 and slope in a small rational set; output
  `(m_start, m_end, slope, value_set_id)`.
- **Resonance period audit**: bucket m by `cycle_length mod m`, list
  small non-integer `cycle_length/m` ratios, and cross-check runaway
  cycles against the wide-band outliers and fixed-point families.
- **`steps_to_lock_in` analysis** (column now in `results_new.csv`):
  verify `steps_to_lock_in ≤ repeat_after − m` per row; plot
  `repeat_after − steps_to_lock_in` vs `steps_to_lock_in` to test whether
  the transient and closed-loop phases scale differently with m.
- **8m prime hitting-time scaling**: regress `log(repeat_after)` vs m for
  the 8m fixed-point primes (exponential vs polynomial) to size budgets
  for unresolved large primes before extending the scan.
- **Hypothesis — slack as a difficulty proxy**: does
  `M*(m) − x_{seed=1}` correlate with `repeat_after` for the 8m primes?

### New scans / Rust

- **Basin probes re-aimed at the full fixed-point catalogue.** With
  `fixed_points_full.csv` in hand, probe flat-window seeds at *all* fixed
  points of a sample of m's (composites included, and the 12m second
  points of the 8m primes). Is a fixed point's basin ever more than the
  point plus a thin shell? Do the 65 m's with three fixed points behave
  differently? Why does seed=1 reach a fixed point for only 9 of ~1411
  m's that have one — and always the smallest?
- **Low-seed basin scan** (e.g. `LogNormal(ln 2m, 0.5)`): can *any* seed
  reach the admissible small-K cycles (K/m ≈ 2)? This is the open
  falsifier for the 4m floor.
- **σ-sweep** at the m's with 1/200 fixed-point hits (m=103, 179): if the
  8m basin is thin, hits should grow systematically with σ.
- **Long tail past m=1788** (and the m=2048 three-fixed-point target),
  with checkpointing and a sidecar config for reproducibility; size
  `--max-steps` via the hitting-time regression first. Brent needs ~2×
  `repeat_after` steps to fire.
- **E.2/E.3 ceilings**: define `M_typ(m)` as the solution of `M = m·ln M`
  and quantify the slack band `[M_typ, M*]`; per-m `max_value/M*(m)`
  ("closest approach" — is it correlated with the wide-band outliers?).

### OEIS / publication

- The map `x → x + τ(x)` is **A062249**; `|S(K)|` is **A036431**; values
  with no preimage are **A036434**. The K-attractor catalogue is a
  statement about the level sets of A062249 — connect to the existing
  literature on the n + d(n) map.
- Submit the realised-K list (6242, 9410, 5162, …) and `M_at(m)` (the HCN
  attaining M*(m) — a bottleneck index over highly composite numbers).
- b-files for the 7 per-m sequences are in `analysis/oeis_bfiles/`;
  initial lookups for `repeat_after(m)` and `max_value(m)` found no OEIS
  matches (as of 2026-05), suggesting the sequence family is novel.
  Remaining lookups unrecorded.

### Decision records

- **Hashing strategy**: a divisor-count-only rolling hash (and
  moving-average gating of snapshot storage) was evaluated and rejected —
  the u64 Rabin-Karp hash on the full window is already O(1) per step
  with ~2⁻⁶⁴ collision odds, and state comparison is not the bottleneck;
  the full-value hash also preserves attractor signatures.
- **Engineering perf plan** (MLP batching of the inner loop, bounds-check
  elimination) lives separately in `PERFORMANCE_PLAN.md`.
"""
)

nb['cells'] = cells
nb['metadata'] = {
    'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
    'language_info': {'name': 'python', 'version': '3.10'},
}
out = (Path(__file__).resolve().parent / 'explore.ipynb')
nbf.write(nb, out)
print(f'wrote {out}  ({len(cells)} cells)')

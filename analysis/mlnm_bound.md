# m·ln(m) bound quantification (ROADMAP §6)

Source: `results_new.csv`, n=1348, m∈[2..1349].
Anchors: m·ln(m); m·H(m) where H is the exact partial harmonic sum.

## Findings

1. **Both anchors are tight, m·H(m) marginally tighter** — the band
   `[p5, p95]` of `cycle_max / anchor` is narrower under m·H(m) than
   under m·ln(m), as expected (H(m) = ln(m) + γ + O(1/m)).

2. **The bulk band tightens substantially with growing m, but is
   not strictly monotonic — outlier m's reopen it.** The `p95 − p5`
   spread of `cycle_max / (m·ln(m))` falls from ~2.3 (m<50) to
   ~0.4 (m≥1000), a ~6× contraction. The empirical sup itself
   does *not* tighten as cleanly: large-spread outliers in the
   600–800 and 1200–1350 bins (cf. m=601, 738–751, 1082 in
   `human_notes.md`) keep the per-bin max in the 2.0–2.2× range.

3. **Trivial lower bound `cycle_min ≥ m` is far from sharp.** In the
   tail (m ≥ 200) the smallest observed `cycle_min / (m·ln(m))` is
   ≈ 0.5911, i.e. `cycle_min ≳ 0.591·m·ln(m)`.
   This is well above the trivial `cycle_min ≥ m`, which would
   correspond to a ratio of `1/ln(m)` (≈ 0.14 at m=1349).

4. **Median is anchor-flat at ~1.13 (m·ln(m)) / ~1.05 (m·H(m))**
   for cycle_min and cycle_max, and ~2.13 / ~1.96 for max_value.
   That is, transient peaks sit at roughly 2× the cycle band —
   consistent with the algorithm overshooting before settling.

## Conjectured empirical bounds (m ≥ 200, n = 1150)

Anchored to m·ln(m):

- `cycle_min ≥ 0.5911 · m·ln(m)`  (empirical inf)
- `cycle_max ≤ 2.1986 · m·ln(m)`  (empirical sup, outlier-driven; see B.4)
- `max_value ≤ 2.6935 · m·ln(m)`  (transient peak)

Tail medians (m ≥ 200):

- `cycle_min`: median = 1.1171, [p5, p95] = [0.7707, 1.3205]
- `cycle_max`: median = 1.1261, [p5, p95] = [0.7912, 1.3702]
- `max_value`: median = 2.1119, [p5, p95] = [1.9333, 2.3686]

## Method

- Quantiles: linear interpolation (numpy default).
- m-bins: [2, 50, 100, 200, 400, 600, 800, 1000, 1200, 1350].
- m=1 dropped (m·ln(m) = 0).
- Tail-only conjecture cutoff at m=200 follows `human_notes.md`
  observation that integer effects dominate small-m cycles.

Re-run: `python analysis/quantify_mlnm_bound.py`.

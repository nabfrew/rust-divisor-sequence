# Research log

Per `ROADMAP.md` §B.8. Sections accrete as roadmap items are completed.
Detailed per-task data lives next to its script under `analysis/`; this
file is the index + conjecture record.

## §6 — m·ln(m) bound (quantified 2026-04-28)

Source: `results_new.csv`, n=1348 resolved m's, m∈[2..1349].
Script: `analysis/quantify_mlnm_bound.py`.
Detailed tables: `analysis/mlnm_bound.csv`, `analysis/mlnm_bound.md`.

**Anchors compared.** m·ln(m) and m·H(m), where H(m) = Σ_{k=1..m} 1/k
(exact partial harmonic sum). m·H(m) is marginally tighter than m·ln(m)
across all three metrics (cycle_min, cycle_max, max_value), as expected
from H(m) = ln(m) + γ + O(1/m).

**Tightening.** The bulk band `[p5, p95]` of `cycle_max / (m·ln(m))`
contracts ~6× from m<50 (spread 2.30) to m≥1000 (spread ~0.4). Not
strictly monotonic — the per-bin **maximum** stays in the 2.0–2.2× range
because outlier m's (601, 738–751, 1082, …; see `human_notes.md`) reopen
the band locally. The bulk contraction is robust; the tail bound is
outlier-dominated.

**Conjectured empirical bounds (m ≥ 200, n = 1150).** Anchored to
m·ln(m):

- `cycle_min ≥ 0.591 · m·ln(m)`     (empirical inf)
- `cycle_max ≤ 2.20  · m·ln(m)`     (empirical sup, outlier-driven)
- `max_value ≤ 2.69  · m·ln(m)`     (transient peak)

Tail medians (m ≥ 200) sit at ~1.13·m·ln(m) for the cycle band and
~2.13·m·ln(m) for `max_value` — i.e. transient peaks live ~2× above
the cycle band, consistent with overshoot before settling.

**Improving on the trivial lower bound.** `cycle_min ≥ m` corresponds
to a ratio of `1/ln(m)` ≈ 0.14 at m=1349. The empirical inf 0.591 is
~4× higher, so the data supports a much sharper lower bound than the
trivial all-primes argument gives.

**Open.** The human-notes <0.01% mean-of-cycle invariant is *not*
quantified here — `results_new.csv` carries only cycle_min/max and
most_common_tail_value, not the cycle mean. To verify rigorously,
compute Σ value·count / Σ count over each `analysis/cycle_signatures/<m>.csv`
(1030 m's available) and tabulate `mean / (m·ln(m))`. Deferred.

## §C.1 — Fixed-point families (enumerated 2026-04-28)

Source: `results_new.csv` + `results_new_4.csv`.
Script: `analysis/build_fixed_points.py`.
Detailed table: `analysis/fixed_points.csv`, `analysis/fixed_points.md`.

A fixed point of the divisor-window recurrence satisfies `d(x) = x/m`,
equivalently `τ(q·m) = q` where `q = x/m`. Multiplicativity of τ
constrains q and the prime-factor shape of m.

**Observed.** 7 cycle_length==1 rows: trivial m=1 (q=1), and 6 odd
primes resolving to `x = 8m`:

- m=127, x=1016, repeat_after=18,958
- m=167, x=1336, repeat_after=34,532
- m=211, x=1688, repeat_after=979,783
- m=613, x=4904, repeat_after=14,143,541
- m=733, x=5864, repeat_after=52,900,083
- m=1291, x=10328, repeat_after=4,180,785,143

**Per-quotient algebraic conditions.**

- **q=3.** `3m = p²` ⇒ p=3, m=3 is the **unique** candidate.
  Not observed (m=3 has cycle_length=4, seed-1 misses x=9).
- **q=8.** `m` an odd prime. Observed for 6 m's above; trivially
  valid for any odd prime m, so the universal-prime conjecture
  reduces to a basin-of-attraction question.
- **q=12.** `m` a prime > 3. Mathematically valid for any such m.
  **Empirically empty** in current data — every prime > 3 lands in
  a multi-element attractor before reaching `x = 12m`.
- **q=16.** Structurally **impossible** for any small m-shape
  (prime, p², semiprime). Contra `human_notes.md` which lists 16m
  as a candidate — there is no `m` with `τ(16m) = 16` and m of low
  prime complexity.
- **q=24.** `m = p²` for odd prime `p ≠ 3`. Smallest candidate
  m=25 → x=600 is in the data but resolves to a 445-cycle, not the
  fixed point.

**Findings.**

1. All non-trivial observed fixed points are `8m` with m odd prime.
   Confirms the human-notes hypothesis. **No composite-m fixed point
   appears in m ≤ 1349.**
2. Mathematical validity ≠ observation: 12m and 24m families exist
   structurally but the seed=1 trajectory never reaches them.
3. The 16m candidate raised in `human_notes.md` is structurally
   ruled out — no need to keep looking.

**Open question.** Per `human_notes.md`: every prime m may have a
length-1 cycle, with some just stuck in a non-trivial loop first.
Partial test (no new Rust): for each prime m whose trial resolved to
a multi-element cycle, check whether `8m` lies in one of the
`analysis/value_set_clusters.csv` clusters. If not, 8m is a separate
basin the seed=1 trajectory missed.

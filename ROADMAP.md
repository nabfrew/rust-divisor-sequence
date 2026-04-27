# Divisor-sequence roadmap

## Status snapshot (2026-04-27)

Phase A (perf rewrite) and the engineering side of Phase B are complete. The
remaining work is mostly **analysis on data we already have** plus a handful
of small Rust additions to extract structural data the current CSV doesn't
expose.

### Shipped

- `r() / r_with_progress() / r_resumable()` layered API on `State` with
  Brent + snapshot stack, Rabin-Karp window hash, `find_cycle_start` walking
  newest→oldest. (`src/lib.rs`)
- Streaming `run_stream` runner: rayon `into_par_iter` + mpsc + in-order
  flush, so a single slow m doesn't stall peers. (`src/main.rs`)
- Checkpoint format with documented invariants; resume on restart, deleted
  on success, preserved on timeout.
- `scan` / `revisit` / `dump-signature` CLI subcommands.
- 8-column CSV format (`m, repeat_after, max_value,
  most_common_tail_value, cycle_length, cycle_max, cycle_min,
  distinct_tail_values`).
- `results_new.csv`: m=1..=1299, no `None` rows.
- `results_new_4.csv`: m=1300..=1349, 22 `None` rows still pending.
- `analysis/build_attractors.py` → `analysis/attractors.csv`
  (288 multiset clusters), `analysis/value_set_clusters.csv`,
  `analysis/cycle_signatures/<m>.csv` (1030 signature dumps).
- `analysis/build_bfiles.py` → `analysis/oeis_bfiles/` (7 b-files).
- Reference tests for m∈{1,2,3,5,8} and criterion benches at m∈{16, 64, 256,
  512, 700}.

### Not shipped / open

- Phase B §1 long tail past m=1349; 22 timeouts in 1300–1349 unresolved.
- Phase B §3 `analysis/explore.ipynb` — no notebook exists.
- Phase B §4 outlier characterisation.
- Phase B §5 linear-segment detector.
- Phase B §6 m·ln(m) bound quantification.
- Phase B §7 OEIS submission log (b-files exist, but no hits/misses recorded).
- Phase B §8 `NOTES.md` — research log file does not exist.
- Threads from `human_notes.md` / `summary.md` not in ROADMAP:
  fixed-point family enumeration, 8m hitting-time scaling, period
  resonance regimes, state-space lock-in metric.

## Phase B remainder — analysis on existing data

These need no new Rust. They consume `results_new*.csv`,
`analysis/attractors.csv`, `analysis/value_set_clusters.csv`, and the
per-m signature files.

### B.3 `analysis/explore.ipynb`

Plots, all on the merged `results_new.csv` + `results_new_4.csv`:

- `repeat_after(m)` log-log with a fit; flag the `cycle_length = m+1`
  vs. multi-m-cluster vs. fixed-point (`cycle_length = 1`) populations
  separately — they almost certainly have different scaling laws.
- `max_value(m)` and `max_value / m`.
- `cycle_length(m)` with the `m+1` resonance band called out (currently
  ~554 of 1158 rows in `results_new.csv`).
- `cycle_min(m)`, `cycle_max(m)` overlaid with `m·ln(m)`, the
  Hardy-Ramanujan anchor `m·H(m)`, and the trivial lower bound `m`.
- `(cycle_max − cycle_min)(m)` and `distinct_tail_values(m)` — both
  flag the same handful of outliers (532, 534, 601, 630, ~738–751,
  1082, …).
- Scatter of m coloured by `value_set_id` (large clusters jump out as
  horizontal bands; isolated outlier m's appear as singletons).
- Run-mean of cycle values vs. `m·ln(m)` (the human-notes invariant
  claim: error <0.01%). Quantify whether that error is genuinely that
  tight or just looks tight on a log scale.

Verification: `jupyter nbconvert --execute analysis/explore.ipynb`
runs clean and re-emits every figure.

### B.4 Outlier characterisation

For m where `cycle_max − cycle_min ≫ 100` or `distinct_tail_values ≫ 50`
(under 20 m's in current data), check the prime-factor structure of the
integers entering/leaving the window. Hypothesis from `human_notes.md`:
confluence of highly-composite numbers in the window broadens the
attractor. Confirm or refute by correlating outlier m's with τ-spikes
among nearby integers (look at τ over the window's value range).

Output: a table per outlier m in the notebook + a one-paragraph entry
in `NOTES.md`.

### B.5 Linear-segment detector

Slide an OLS over `cycle_min(m)` and flag runs of length ≥ K with R²
≥ 0.99 and slope in a small rational set. Per `human_notes.md` these
typically lead into a stable attractor and have wider `cycle_max −
cycle_min` spread than the attractor itself. Output `(m_start, m_end,
slope, target_value_set_id)` to `NOTES.md`. Implement in the notebook,
not Rust.

### B.6 m·ln(m) bound — quantitative

- Median, p5/p95 of `cycle_min`, `cycle_max`, `max_value` relative to
  `m·ln(m)` and `m·H(m)`.
- Mean-of-cycle / `m·ln(m)` distribution (the human-notes invariant).
- Trivial lower bound `cycle_min ≥ m` is loose in the data — try to
  fit a tighter lower bound (perhaps `m·ln(ln m)` plus a constant).
- If the band tightens with growing m, record the conjecture in
  `NOTES.md` along with the empirical constants.

### B.7 OEIS lookups

For each generated b-file, paste first 20 terms into oeis.org by hand
and record hits / misses in `NOTES.md`. Also search the recurring
attractor extremes as a stand-alone integer sequence (2638, 4442, 4612,
4744, 5158, 6238, 9406, …) — these are the `cycle_max` constants of
the largest multiset clusters. Skip `cycle_length(m)` for the
`cycle_length = m+1` majority.

### B.8 `NOTES.md`

Lead with the attractor catalog (size of largest clusters, the
`(cycle_min, cycle_max, distinct_tail_values)` proxy vs. the actual
multiset hash). Sections: problem statement, finite-state-space
periodicity argument, attractor catalog summary, m·ln(m) bound
conjecture with plots, outlier list (B.4), linear-segment list (B.5),
fixed-point families (C.1, see below), 8m hitting-time scaling (C.2),
OEIS hits / misses, open questions.

## Phase C — math threads from `human_notes.md` / `summary.md`

These are new and need small targeted code.

### C.1 Fixed-point family enumeration

Cycles of length 1 (`cycle_length == 1`) satisfy d(x) = x/m, so the
fixed point is `most_common_tail_value` and the constraint is
`τ(x) · m == x`. From `results_new.csv` the known fixed points
(127, 167, 211, 613, 733, 1291) are all `x = 8m` with m prime.

Pure-data task: filter all `cycle_length == 1` rows, group by `x/m`
(the divisor count), and inspect the m-set per quotient. The 8m family
should dominate; any composite m fixed point is interesting (the human
notes raise 3m, 12m, 16m as candidates — verify whether any actually
occur in the data and what factorisation makes that work).

Output: `analysis/fixed_points.csv` (`m, prime, x, x_over_m,
m_prime_factorization`) + a `NOTES.md` section with the necessary
condition for each quotient.

### C.2 8m prime hitting-time scaling

For prime m where the trial resolves to x = 8m, plot m vs.
`log(repeat_after)`. Per `human_notes.md` the suspicion is exponential
scaling — confirm or refute with a regression. If the fit is clean,
extrapolate the expected runtime for the unresolved primes in
1300–1349 to size `--max-steps` and `--checkpoint-interval` for the
next long run.

Output: figure in `explore.ipynb` + a row per prime in `NOTES.md` with
predicted-vs-observed `repeat_after`.

### C.3 `steps_to_lock_in` metric (Rust)

Track when the dynamical system enters its "closed sub-region of state
space" — i.e. when no new value enters the window for a sustained
window. Two candidate definitions:

- **Strict (per human_notes):** the *set* of distinct divisor counts
  in the window stops changing for ≥ 2m consecutive steps. Cheap to
  maintain (a small histogram of u8 counts).
- **Looser:** the *set* of distinct values in the window stops
  changing. More expensive (window of u16, up to ~10⁴ distinct
  values), and probably less mathematically clean.

Prefer the strict variant. Add `steps_to_lock_in: Option<usize>` to
`RResult` and a 9th CSV column. The metric is the smallest step k at
which `div_counts[k..k+2m]` introduces no new τ value.

Then analysis-side: plot `repeat_after − steps_to_lock_in` vs.
`steps_to_lock_in`. Hypothesis: the transient phase
(`steps_to_lock_in`) and the closed-loop traversal
(`repeat_after − steps_to_lock_in`) scale differently with m.

This *adds* a column rather than replacing one — old CSVs stay
parseable; bump the CSV header reader in `read_csv` to default the
new column to `None` for legacy rows.

### C.4 Resonance period audit

Cluster m by `cycle_length − m` (likely concentrated at 0, 1, 2). Plot
the fraction of m in each resonance band as m grows. Pure data task,
goes in `explore.ipynb` and `NOTES.md`.

### C.5 Skipped: divisor-count rolling-hash rewrite

`human_notes.md` proposes hashing the window of divisor counts (u8)
instead of values (u16), framed as a perf win. **Don't.** The current
`State.hash` is already a rolling u64 Rabin-Karp with O(1) update;
hash collisions are ~2⁻⁶⁴ per compare. Switching the hashed type
from u16 to u8 doesn't change the asymptotic cost or the memory
footprint that matters (snapshots are ≈33 × m bytes, microseconds at
m=1500). Detection is not the current bottleneck — `repeat_after`
itself is. Leave this thread alone unless a future profile says
otherwise; record this decision in `NOTES.md` so it doesn't keep
resurfacing.

Also skipped: state-space compression (the moving-average gating idea
in `summary.md`). It would save memory we don't actually need to
save.

## Phase D — extended data run

Push past m=1349 and resolve the 22 Nones in `results_new_4.csv`.

- Run prime hitting-time scaling (C.2) **first**: it tells you whether
  `--max-steps 10¹¹` is realistic for the long tail or whether some m
  need 10¹² and a multi-day run.
- Use `--checkpoint-dir` and a sidecar `.toml` with
  `--max-steps`, `--checkpoint-interval`, range, fac-table size, and
  start time for reproducibility.
- Extend `results_new_4.csv` to 1500 first, then evaluate. Beyond
  ~1500 the fac_table size (1<<18 = 262144) starts approaching
  observed `max_value` (~20k for m≈1300), so monitor the panic from
  `step()` and bump as needed.
- The tricky-m spot-diff target stays m=560..=572 per CLAUDE.md.

## Critical-path files

- `src/lib.rs` — only if implementing C.3 (`steps_to_lock_in`).
  Touch points: extend `State` with a `tau_present: [bool; 256]`-ish
  histogram (or `HashSet<u8>` keyed by τ values seen in current
  window), update on each `step` as values enter/leave. Track
  "consecutive steps with stable set" counter. Surface result in
  `RResult` and `summarize_cycle`.
- `src/main.rs` — extend CSV header + `write_result_row` +
  `read_csv` (legacy `None` default) for C.3.
- `analysis/explore.ipynb` — new, drives B.3, B.4, B.6, C.2, C.4.
- `analysis/fixed_points.csv` — new, output of C.1 (script or
  notebook cell).
- `NOTES.md` — new, the research log itself.

## Verification

- `cargo test --release` and `cargo bench --bench r` clean per
  CLAUDE.md.
- m=560..=572 spot diff against `results_new.csv` after any lib.rs
  change (covers the historically tricky m=569).
- `jupyter nbconvert --execute analysis/explore.ipynb` runs clean.
- `dump-signature --m N` remains deterministic across the C.3 change
  (the new column doesn't enter the signature multiset).
- For C.3: spot-check `steps_to_lock_in ≤ repeat_after − m` on every
  resolved row (the lock-in must precede the cycle's first close).

## Out of scope (unchanged)

- Generalising to other arithmetic functions (σ, φ, ω, Ω, λ).
- GPU / SIMD.
- Non-uniform seeds, basin-of-attraction maps. (`human_notes.md`
  raises sampling random initialisations to test the conjecture
  "every prime m has a length-1 cycle, some just get stuck in a
  different loop first." Interesting; out of scope here.)
- Materialising full ordered cycle periods to disk.
- Publishing the crate, WASM demo, CI.

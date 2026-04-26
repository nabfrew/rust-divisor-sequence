# Next-level plan: divisor-sequence exploration

## Context

The project computes R(n, m) = sum of d(·) (divisor-count) over the last m terms, seeded with m ones, and looks for when the sequence becomes periodic. Results are tabulated in `results.csv` / `compiled_results.csv` for m up to ~700.

Two concrete limits motivate this plan:

1. **Performance wall.** With `max_length = 1e9`, m=569 already returns `None, None` (results.csv:572) — detection itself is the bottleneck, not the underlying mathematics. `repeats_m` calls `gs_find` over the entire stored sequence every 10^6 steps and stores every value in a `Vec<u16>` (potentially ~10^8 entries ≈ 200 MB/trial), which caps both the m-range and max_length.
2. **Math latent in the data.** Each column of the CSV is a candidate integer sequence (max_value(m), repeat_after(m), cycle_length(m), most-common-in-tail(m)). None of these appear to have been characterized or checked against OEIS. Conjectures about growth rates aren't written down anywhere.

Scope: one focused rewrite (math + performance, d(n) only). Goal: clear the m=569 wall, gather richer per-m statistics, and produce a minimal research artifact (notebook + b-files) that makes the data usable outside Rust.

## Key mathematical observation driving the perf rewrite

The state of the dynamical system at step t is exactly the sliding window of the last m values (everything else — the running sum, the ring buffer — is derivable from it). The map state → next-state is deterministic. So:

- The trajectory enters a cycle the first time a window-state repeats.
- Cycle detection reduces to detecting a repeated m-tuple, which is **Brent's algorithm** over the state — no substring search, no stored sequence.
- `repeat_after` = first-occurrence step of the cycle state; `cycle_length` = current step − repeat_after. Currently the code conflates these (CSV has `repeat_after` but no `cycle_length` as a distinct column, and the compiled CSV's `most common value in tail` isn't reproducible from `results.csv` alone).

This single observation replaces both `gs_find` (O(seq_len) each check) and `binary_repeat_search` (O(log seq_len) sequence scans) with O(1)-memory cycle detection.

## Files to modify / add

- `src/main.rs` — shrink to CLI entry point only.
- `src/lib.rs` (new) — `r()`, `RResult`, sieve, Brent detector; all unit-testable.
- `Cargo.toml` — drop `galil-seiferas` and `prime-factor`; add `clap`, `criterion` (dev), keep `rayon`.
- `tests/reference.rs` (new) — small-m correctness tests vs. a naive stored-sequence reference.
- `benches/r.rs` (new) — criterion benches for small/medium m.
- `analysis/explore.ipynb` (new) — load CSV, plot repeat_after(m), max_value(m), cycle_length(m), log-log fits.
- `analysis/oeis_bfiles/` (new) — generated b-files per derived sequence, ready for OEIS submission.
- `NOTES.md` (new) — running research log: conjectures, plots, OEIS IDs if found.


# Phase B — Math output

Phase A landed: `results_new.csv` covers m=1..=1158 with no `None` rows in the
8-column format (`m, repeat_after, max_value, most_common_tail_value,
cycle_length, cycle_max, cycle_min, distinct_tail_values`). The original m=569
wall is gone and the four extra cycle-summary columns surface structure the
original Phase B plotting list ignored. Plan refocuses on that structure.

## 1. Extended data run

Push m past 1158. Calibrate `--max-steps` for the outlier class — observed
`repeat_after` already reaches ~2×10¹⁰ in current data, so allocate ~10¹¹
and lean on `--checkpoint-dir` for the long tail. Run parameters recorded in
a sidecar `.toml` next to the CSV.

## 2. Attractor catalog (headline)

Many m share a cycle whose value-multiset is essentially identical:
e.g. `cycle_min/cycle_max = 4402/4442` covers nine m's just in 559–593,
`2624/2638` covers a much larger cluster, `4602/4612`, `4736/4744`,
`5130/5158`, `6210/6238`, `9394/9406` are recurring signatures. Cluster m by
`(cycle_min, cycle_max, distinct_tail_values)` and confirm "shared signature"
means "same value-multiset" by inspecting one representative m per cluster.

**Persistence shape:** cycles can hit 10⁷+ ordered terms — do **not**
materialise the period. Persist only the value→count multiset, which is
bounded by `distinct_tail_values` (worst observed ≈ 7.4k for the m=741
cluster, ~80 KB max per dump; typical attractor is 3–5 values, ~100 B).
`summarize_cycle` already builds this HashMap and discards it; expose it.

Concrete deliverables:

- New `dump-signature --m N --output PATH` CLI subcommand: re-runs `r()`
  for one m and writes `value,count` per line. Multiset only; never the
  ordered period.
- `analysis/attractors.csv`: one row per cluster — `signature_id,
  distinct_count, cycle_min, cycle_max, signature_hash, representative_m,
  member_m_list`.
- `analysis/cycle_signatures/<m>.csv`: one file per cluster representative
  (and per outlier from §4). Don't dump for every m — redundant for the
  cluster majority.

## 3. `analysis/explore.ipynb`

Load `results_new.csv`, plot:

- `repeat_after(m)`, log-log with a fit.
- `max_value(m)`, plus `max_value / m`.
- `cycle_length(m)`, with the `cycle_length = m+1` cluster (~554 of 1158
  rows in current data) called out vs. the multi-m cycles.
- `cycle_min(m)`, `cycle_max(m)` overlaid with `m·ln(m)` and the trivial
  lower bound `m`. Empirical band width as a function of m.
- `(cycle_max - cycle_min)(m)` and `distinct_tail_values(m)` — both flag
  the ~10 outlier m's (532, 534, 601, 630, 738–751-region, 1082).
- Scatter of m coloured by attractor cluster id from §2.

## 4. Outlier characterisation

For m where `cycle_max - cycle_min ≫ 100` or `distinct_tail_values ≫ 50`
(~10 m's in current data), examine the prime-factor structure of the
integers entering/leaving the window of length m around those values.
Hypothesis from `human_notes.md`: confluence of highly-composite numbers
sliding through the window broadens the attractor. Confirm or refute by
correlating outlier m's with τ-spikes among nearby integers.

## 5. Linear-segment detector

Slide an OLS over `cycle_min(m)` and flag runs of length ≥ K with R² ≥ 0.99
and slope in a small rational set. Per `human_notes.md` these typically
lead into a stable attractor and have wider `cycle_max - cycle_min` spread
than the attractor itself. Output `(m_start, m_end, slope, target_cluster)`
to `NOTES.md`.

## 6. m·ln(m) bound

Quantify the empirical band: median, p5/p95 of `cycle_min`, `cycle_max`,
`max_value` relative to `m·ln(m)` and `m·H(m)` (Hardy-Ramanujan). Try to
beat the trivial all-primes lower bound `≥ m`. If the band tightens with
growing m, record the conjectured bound in `NOTES.md`.

## 7. OEIS artifacts

b-files in `analysis/oeis_bfiles/` for: `repeat_after(m)`, `max_value(m)`,
`cycle_max(m)`, `cycle_min(m)`, `distinct_tail_values(m)`,
`(cycle_max - cycle_min)(m)`. Skip `cycle_length(m)` for the
`cycle_length = m+1` majority — uninteresting; submit only the non-trivial
subseries (m where `cycle_length ≠ m+1`). Also search the recurring
attractor extremes as a stand-alone sequence (2638, 4442, 4612, 4744,
5158, 6238, 9406, …) — these are the `cycle_max` constants of §2's
clusters and are good OEIS candidates in their own right. Hits / misses
logged in `NOTES.md`. Manual paste into oeis.org — no network automation.

## 8. `NOTES.md` research log

Lead with the attractor catalog. Sections: problem statement, finite-state-
space periodicity argument, attractor catalog summary, m·ln(m) bound
conjecture with plots, outlier list (§4) with notes, linear-segment list
(§5), OEIS hits / misses, open questions (non-uniform seeds, generalised
arithmetic functions — explicitly out of scope here).

## What is explicitly out of scope

- Generalizing to other arithmetic functions (σ, φ, ω, Ω, λ).
- GPU / SIMD. Revisit only if detection is the bottleneck again after Phase B.
- Non-uniform seeds, basin-of-attraction maps.
- Materialising full ordered cycle periods to disk (memory blowup at large m).
- Publishing the crate, WASM demo, CI.

## Verification

- `cargo test --release` and `cargo bench --bench r` — pass per CLAUDE.md.
- m=560..=572 spot diff against `results_new.csv` per CLAUDE.md (covers
  the historically tricky m=569).
- `jupyter nbconvert --execute analysis/explore.ipynb` runs clean on
  `results_new.csv` and produces every plot in §3.
- `dump-signature --m N` is deterministic: two runs on the same m produce
  byte-identical output.
- Attractor clustering: every member of a cluster shares the
  representative's `signature_hash`. Clusters of size ≥ 2 verified by
  comparing the dumped multisets pairwise.
- `analysis/oeis_bfiles/*.txt` lint clean (one `n value` per line,
  strictly increasing n, no gaps); first 20 terms match
  `results_new.csv`.

## Critical-path files

- `src/lib.rs::summarize_cycle` (lib.rs:549) — already builds the
  value→count `HashMap`; needs an entry point that returns the map (not
  just `CycleStats`) so the CLI can persist it.
- `src/main.rs` — add `dump-signature` subcommand alongside `scan` /
  `revisit`.
- `analysis/explore.ipynb`, `analysis/attractors.csv`,
  `analysis/cycle_signatures/`, `analysis/oeis_bfiles/`, `NOTES.md` —
  all new.

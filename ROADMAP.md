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

## Phase A — Performance rewrite (weekend 1)

1. **Split lib/bin.** Move `r`, `RResult`, `build_fac_table`, and new cycle detector to `lib.rs`. Keep `main.rs` as CLI only. This unlocks unit tests and benches.

2. **Replace `gs_find` + full-sequence storage with Brent's cycle detection on window states.**
   - State = ring-buffer `[u16; m]` + running sum (sum is redundant but cheap). Only the window is compared.
   - Brent: snapshot the tortoise at power-of-two steps; at each subsequent step, compare current window to snapshot. On match, period = steps since snapshot.
   - Recover `repeat_after` with a second pass: advance two pointers in lock-step, one starting at window at-snapshot-time, the other at step 0 reconstructed from the initial m ones; they meet at `repeat_after`. Since the window at time t is fully determined by `(fac_table, previous window)`, the reconstruction is straightforward.
   - Replaces the entire `seq: Vec<u16>` allocation. Memory per trial drops from O(repeat_after) to O(m).

3. **Linear smallest-prime-factor sieve for `fac_table`.** Replace the `PrimeFactors::from` per-number call with a single O(N log log N) sieve of SPF, then derive divisor counts in one pass using the standard `τ(p^a · k) = τ(k) · (a+1)/a` recurrence (or the SPF-groups method). Drop the `prime-factor` dependency.

4. **Make fac_table size dynamic and safe.** Current hard cap of 32768 is a latent panic (m=577 already hits max_value=7808; m>700 trends upward). Options, in order of preference:
   - Grow fac_table on demand inside `r()` with a geometric resize guarded by a mutex-free check (each worker owns its own extension) — simplest, works with `Arc`.
   - Or: pre-size to a generous bound (e.g., 1 << 18) based on the observed trend, with an explicit `assert!` on overflow so failures are loud.
   Pick (b) for simplicity in this focused pass; (a) is a follow-up if m-range grows further.

5. **CLI via `clap`.** `--m-range START..=END`, `--max-steps N`, `--output PATH`, `--threads N`, `--fac-table-size N`. Replace the hardcoded `results_500.csv`, `1..=2000`, batch size, etc.

6. **Unit tests.** For m ∈ {1, 2, 3, 5, 8}, run both the new Brent-based `r()` and a stored-sequence reference (kept in `tests/` only) and assert `repeat_after`, `max_value`, cycle length, and first 1000 terms agree. Cross-check the numbers in `results.csv` / `compiled_results.csv` for small m.

7. **Criterion bench.** `r(m, ·)` for m ∈ {16, 64, 256}. Establishes a baseline for future tuning (SIMD, state hashing, etc.).

## Phase B — Math output (weekend 2)

1. **Extend the result record.** `RResult` gains `cycle_length`, `cycle_max`, `cycle_min`, `most_common_tail_value`, `distinct_tail_values`. CSV header updated to match `compiled_results.csv` plus the new columns. This reproduces and supersedes the existing compiled CSV from a single run.

2. **Extended data run.** With the rewrite, re-run m = 1..=2000 (or further — determined by real runtime after the rewrite lands). Resolve the m=569 `None, None` gap. Save under `data/` with the run parameters recorded in a sidecar `.toml`.

3. **`analysis/explore.ipynb`.** Load CSV, plot:
   - repeat_after(m), log-log with a fit.
   - max_value(m), plus max_value / m.
   - cycle_length(m).
   - Histogram of most-common-tail values.
   Goal: eyeball growth law candidates (polynomial? sub-exponential?), flag outliers.

4. **OEIS artifacts.** Generate b-files for each derived sequence in `analysis/oeis_bfiles/` (plain `n value\n` per line, standard OEIS format). Run local OEIS search (paste first 20 terms into oeis.org manually — no network automation). Record hits / misses in `NOTES.md`. If any are new, draft a submission.

5. **`NOTES.md` research log.** One-page-ish: problem statement, state-space framing, guaranteed-periodicity argument (finite state space), empirical growth-rate conjectures with the plots that support them, open questions (e.g., basin-of-attraction under non-uniform seeds — flagged as follow-up, explicitly out of scope here).

## What is explicitly out of scope

- Generalizing to other arithmetic functions (σ, φ, ω, Ω, λ). Deferred per user instruction.
- GPU / SIMD. Revisit only if Brent-based detection is still the bottleneck after the rewrite.
- Non-uniform seeds, basin-of-attraction maps, dynamical-systems theory beyond the minimum needed to justify the perf rewrite.
- Publishing the crate, WASM demo, CI. These are software-quality goals outside this pass.

## Verification

- `cargo test` — unit tests vs. reference implementation for small m pass; cross-checks against existing CSV rows (m ≤ 50) match exactly.
- `cargo bench` — Brent implementation beats a rebuilt-from-scratch `gs_find` baseline on m ∈ {64, 256} by at least a factor of 5 (conservative; expect more).
- **End-to-end:** `cargo run --release -- --m-range 560..=580 --max-steps 2_000_000_000` — m=569 resolves (no `None`), and max-value / repeat-after values for m ∈ {560..568, 570..580} reproduce the existing CSV.
- `jupyter nbconvert --execute analysis/explore.ipynb` runs clean on the extended CSV and produces the plots.
- `analysis/oeis_bfiles/*.txt` lint clean (one `n value` per line, strictly increasing n, no gaps). First 20 terms match CSV.

## Critical-path files when execution starts

- `src/main.rs:1-193` — currently monolithic; gets split.
- `src/main.rs:9-20` (`repeats_m`) and `src/main.rs:107-127` (`binary_repeat_search`) — both deleted, replaced by Brent detector in `lib.rs`.
- `src/main.rs:23-39` (`build_fac_table`) — replaced with SPF sieve.
- `src/main.rs:52-104` (`r`) — replaced with window-state iterator using the Brent detector; `Vec<u16>` sequence storage removed.
- `Cargo.toml:8-12` — drop `galil-seiferas`, `prime-factor`; add `clap`, dev-dep `criterion`.

# Phase C — Performance roadmap

Phase B (math output, notebook, OEIS artifacts) is paused. This plan focuses
purely on making `r()` run further before the per-trial wall-clock becomes
unacceptable. Empirically: with the current Brent implementation, m=863 takes
hours at repeat_after ≈ 6.7 × 10⁹, and each new m trends longer.

## Bottleneck analysis

At m=863, repeat_after ≈ 6.7 × 10⁹. Per iteration the hot loop does:

- `State::step` — 1 table lookup, 2 arithmetic ops, 2 writes, mod-m head
  advance. ~5 ns.
- `State::window_eq` — runs every iteration against the Brent snapshot.
  Early-exits on `div_sum`, but for large m the divisor sum lives in a narrow
  band (at m=863, cycle_min=5130 and cycle_max=5158 — ~29 distinct values), so
  sum-collisions are common and the O(m) ring-buffer scan fires frequently.

Back-of-envelope: even if the full scan triggers only 1 time per 10³ steps, at
6.7 × 10⁹ iterations that's ~6 × 10⁹ extra u16 comparisons. That's the bulk of
runtime, not `step()` itself.

Secondary cost: `find_cycle_start` replays from step 0 with two lock-step
states — another ~mu steps after cycle detection. Total work ≈ **2 × mu** real
iterations.

## C1 — Rolling hash on the window state (primary lever)

Add a `u64 hash` field to `State`, maintained in O(1)/step via Rabin-Karp:

```
h_new = (h_old - old_value_leaving * B^(m-1)) * B + new_value   (mod p)
```

Precompute `B^(m-1) mod p` once per trial. Replace the existing `window_eq`
front-door with: compare hashes → on hash match, verify with the existing O(m)
scan. For 64-bit hash and 6.7 × 10⁹ states, expected false positives ≈
(6.7e9)² / 2⁶⁴ ≈ 0.02 — and we verify on match, so correctness is unchanged.

- **Expected gain:** 10–50× on the main loop for large m.
- **Benchmark target:** m=256 ≥ 10×; m=700 ≥ 20×.
- **Files:** `src/lib.rs` — extend `State`, modify `step()`, replace
  `window_eq` call sites.

## C2 — Cheaper mu recovery

`find_cycle_start` currently replays from step 0. Instead, **keep all Brent
snapshots** — there are only ⌈log₂ mu⌉ ≈ 33 of them at mu = 6.7 × 10⁹, so
storage is ~33 × (m u16 + m u8 + overhead), trivially small.

On cycle detection, binary-search the snapshots for the last one taken before
mu, then replay from there. Average replay is O(mu/2) → halves total work.

- **Expected gain:** ~2× on long-mu trials. No cost elsewhere.
- **Files:** `src/lib.rs` — replace `snapshot: State` with
  `snapshots: Vec<State>`; rewrite `find_cycle_start` to start from the
  appropriate snapshot.

## C3 — Work-stealing across m

Replace the fixed-batch `into_par_iter()` + `collect()` in
`main.rs::run_batches` with streaming parallel execution. Today one slow m
(e.g., m=697 at ~5.7 × 10⁹ steps) stalls its entire batch of 8. Streaming lets
finished trials land while stragglers continue.

Rough shape: `par_iter` over the whole range, send each result through an
`mpsc` channel as it completes, drain on the main thread, re-sort before
writing CSV (or write out-of-order with m in column 0 — the CSV is already
keyed by m).

- **Expected gain:** Better core utilization on mixed-m ranges; no help for
  any single m.
- **Files:** `src/main.rs` — rewrite `run_batches` as `run_stream`.

## C4 — Checkpoint & resume for long single-trials

Hours-long trials should be crash-safe. Periodically (every N × 10⁸ steps)
dump `(m, steps, state, snapshots, power, lam, max_value)` to a sidecar
`.ckpt` file. On resume, deserialize and continue.

- **Expected gain:** Eliminates redoing work on crash / reboot / Ctrl-C.
  Enables splitting one trial across sessions.
- **Files:** `src/lib.rs` — add `r_with_checkpoint`; `src/main.rs` — CLI flag
  `--checkpoint-dir` and `--resume`.

## C5 — Progress heartbeat per trial

Print `m=863: step 1.2e9 / cap 1e10 (12%), max_value=…` every N × 10⁸ steps.
Today output is per-batch, which is opaque during hours-long trials. Needs a
`Mutex<Stdout>` or a progress channel since trials run in parallel.

- **Expected gain:** UX — lets the user tell whether a trial is advancing.
- **Files:** `src/lib.rs::r` — thread a progress callback; `src/main.rs` —
  wire a printing callback.

## C6 — Benchmark baseline (run first)

Extend `benches/r.rs` with m ∈ {64, 256, 512, 700}, low `max_length` that
still reaches a cycle for each m. Capture numbers **before** C1 so the gain
is demonstrable and future regressions get flagged by criterion.

- **Expected gain:** Visibility. Prevents flying blind on subsequent changes.
- **Files:** `benches/r.rs`.

## Explicitly out of scope

- **SIMD / fixed-size generics for small m.** Revisit only if benches after
  C1 still show cache/ALU bound.
- **Predicting `repeat_after` from `m` analytically.** Math direction —
  belongs with a re-opened Phase B.
- **GPU.** Still overkill.
- **Alternative cycle-detection (Nivasch, Gosper).** Same asymptotics,
  uncertain constants; Brent + rolling hash is already near the floor for
  this structure.
- **Dataset reorganization (`data/` + sidecar `.toml`).** Phase B2 — paused.

## Suggested order

1. **C6** — bench baseline (30 min, prevents flying blind).
2. **C1** — rolling hash (biggest single win).
3. **C2** — snapshot list for mu recovery (~30 LOC, clean follow-on to C1).
4. **C5** — heartbeat (free UX, bundle with C1/C2).
5. **C4** — checkpoint/resume (only if C1+C2 still leave trials hours long).
6. **C3** — work-stealing (only if planning batch re-runs where stragglers
   stall).

## Verification

- `cargo test` — existing reference tests in `tests/reference.rs` still
  pass; rolling hash doesn't change `r()`'s return values for small m.
- `cargo bench` — after C1, ≥ 10× speedup at m=256 vs the C6 baseline.
- End-to-end spot check: rerun m ∈ {560..580, 690..700, 860..863} and
  compare against `results_new*.csv`. All scalar columns must match
  exactly — a rolling-hash bug would manifest as a wrong `repeat_after`.

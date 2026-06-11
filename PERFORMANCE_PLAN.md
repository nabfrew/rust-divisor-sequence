# Performance Plan — Divisor-Sequence Brent Loop on Ryzen 7 4800H (measured rewrite, 2026-06-11)

Supersedes the previous unmeasured plan. The old plan assumed the inner loop is
**latency-bound** on the `div_sum → fac_table[div_sum] → div_sum` dependent-load
chain and built everything around hiding that latency. Measurement says
otherwise: the loop spends half its time on per-step τ-set bookkeeping, and the
fac_table hot region is far smaller than assumed. The biggest wins are cheaper
and lower-risk than the multi-stream refactor the old plan centered on.

**Hardware (unchanged):** AMD Ryzen 7 4800H (Zen 2), 8C/16T, AVX2, no AVX-512.
L1d 32 KB/core, L2 512 KB/core, L3 8 MB. Vega 7 iGPU only. SIMD gather
(`vpgatherqq` is microcoded on Zen 2) and GPU offload remain dismissed — that
part of the old plan stands.

---

## Measurements (2026-06-11, this machine)

Protocol: single trial m=700 (`repeat_after` = 277 023 487), `--threads 1`,
net of 0.68 s fixed overhead (process start + 2²⁴-entry sieve). Brent walks
≈554 M steps for this trial: detection at 2²⁹ ≈ 537 M (μ = 277 M sits just
above 2²⁸, near worst case for the power-of-2 schedule) plus ≈17 M in
`find_cycle_start`.

| configuration                              | net time | steps/s | ≈cycles/step |
|--------------------------------------------|----------|---------|--------------|
| current code, default build                | 3.98 s   | 139 M   | ~30          |
| τ-set bookkeeping disabled (experiment)    | 2.06 s   | 269 M   | ~15.5        |
| default code + LTO/CGU=1/target-cpu=native | 3.37 s   | 164 M   | ~25          |

Key facts these establish:

1. **The loop is throughput-bound, not latency-bound.** 30 cycles/step vs a
   dependent-load chain of ~8–12 cycles. The τ-set tracking added for the
   lock-in metric (`tau_counts` / `tau_set_bitset` updates in `State::step`)
   costs **1.93×** by itself. Almost all of that is the two branchy
   count-table updates; the 32-byte bitset copy+compare is nearly free.
2. **The lock-in metric being paid for is mostly returning `None`.** The τ-set
   flickers within the cycle at large m (m=700 reports `None` even on a fresh
   run), and every row in `results_new*.csv` has `None` in that column.
3. **The fac_table hot region is tiny.** `max_value` ≤ ~27.5 K for all
   m ≤ 1788 in the recorded results, so the hot region is ≤ 55 KB of the 32 MB
   u16 table — ~20 KB at m=700 (mostly L1-resident), 45–55 KB at m ≥ 1500
   (L2-resident). The old plan's "256 KB table, every load is L2" framing was
   wrong on both ends.
4. **Build flags are worth 1.18×** (`lto = "fat"`, `codegen-units = 1`,
   `-C target-cpu=native`), verified bit-exact on the m=700 row.

## Verdicts on the old plan

- **Discard 1.1 (bounds-check / panic-formatting elimination).** Already
  implemented — `State::step` documents exactly this (slim panic via direct
  indexing, `assert_unchecked` on `head`). Do **not** remove the remaining
  `fac_table[self.div_sum]` bounds check: it is the only guard against orbit
  escape past the table, and the compare-and-branch is off the load chain.
- **Defer 1.2 (default 8 threads).** Backwards as stated: SMT *helps* a
  latency-bound loop (two independent chains per core for free), and the loop
  becomes *more* latency-bound after Stage 1, not less. Decide by benchmark
  (Stage 4); keep rayon's default 16 until then.
- **Demote 2.1 (N=2 multi-trial interleave).** The idea is sound but the
  1.8–2.5× estimate ignored that SMT already overlaps two chains per core, and
  that interleaving does nothing for the single longest trial — which floors
  scan wall-clock once fewer trials than threads remain. Kept only as a
  bench-gated experiment (Stage 5), framed as "8 threads × 2 streams vs
  16 threads × 1".
- **Discard 2.2 (eliminate `div_counts`).** The analysis was wrong:
  `div_counts[head]` is a *sequential* ring read — an L1 hit the prefetcher
  handles, off the critical chain. Replacing it with `fac_table[old_value]`
  adds a second *random* load without shortening the chain — strictly more
  cache pressure. (Also moot as stated: `div_counts` is never persisted, so no
  `CKPT_VERSION` bump would have been involved.)
- **Discard Stage 4 (software prefetch).** The chain's next address cannot be
  known before the previous load returns, and the OoO core already overlaps
  the *independent* streams' loads. Nothing left for `_mm_prefetch` to do.
- **Keep** the SIMD/GPU dismissal and the verification gates (reused below).
- **Missing from the old plan entirely:** the τ-tracking cost (its single
  largest finding was sitting unmeasured in `step`), build configuration, and
  the algorithmic level — the Brent schedule itself wastes up to ~2× on
  long-μ trials (see Stage 2; the measured m=700 trial is a near-worst case).

---

## New plan (staged, ship in order)

### Stage 0 — build configuration (measured 1.18×, ~15 min, zero risk)

Add to `Cargo.toml`:

```toml
[profile.release]
lto = "fat"
codegen-units = 1
```

and `.cargo/config.toml` with `rustflags = ["-C", "target-cpu=native"]`
(this is a single-machine project; generality explicitly traded away).
Verified bit-exact on m=700. Run the spot-check gate anyway.

### Stage 1 — gate τ/lock-in tracking out of the hot loop (measured 1.93×, ~2–3 h)

Make `State::step` const-generic: `step::<const TRACK_LOCK_IN: bool>` (or a
parallel `step_fast`), with the `tau_counts`/`tau_set_bitset`/
`tau_set_stable_steps` updates and `r_inner`'s per-step `lock_in_step` checks
compiled out when false. Add a `--lock-in` CLI flag; default **off** for
`scan` — the metric is `None` in every recorded row, so default-off changes no
output. Keep the fields in `State` (checkpoint loader already reconstructs
them; no format change).

- Monomorphize `r_inner` over the same const so the Brent loop's
  `tau_set_stable_steps >= 2*m` check also disappears.
- Tests: run reference m ∈ {1,2,3,5,8} through both variants; assert identical
  `RResult` apart from `steps_to_lock_in`.
- Update `analysis/explore.ipynb` §12: lock-in metric becomes opt-in.

### Stage 2 — geometric Brent schedule (expected ~1.5–1.7× avg on long-μ trials, ~4–6 h)

Algorithmic, zero per-step cost. The power-of-2 tortoise schedule detects at
the next power of two ≥ μ — up to 2× overshoot (m=700: detection at 537 M for
μ = 277 M) — and then `find_cycle_start` replays up to μ/2 steps × 2 cursors
from a snapshot that can be half an octave stale. Expected total ≈ 2.0μ,
worst ≈ 3μ.

Replace `power *= 2` with a geometric growth factor 1+ε, ε = 1/8: reposition
the tortoise when `lam == run_len` where `run_len = max(pos >> 3, 64)`.
Detection then costs ≤ (1+ε)μ + λ, and snapshot spacing εμ caps the
`find_cycle_start` replay at ~2·(εμ/2). Expected total ≈ (1+1.5ε)μ ≈ 1.19μ →
**~1.7× average, ~2.4× on worst-case μ** (which includes the m=700 reference
trial), ~0.85× only for the rare luckiest μ just under a power of 2.

- Correctness is the same argument as classic Brent: detection requires the
  run length to reach λ, and run lengths grow geometrically, so it always
  eventually does. λ here is ~m+1, and `pos ≥ 8λ` long before `pos ≥ μ` on
  every trial that matters.
- Snapshot count grows from ~⌈log₂ μ⌉ to ~⌈log₁.₁₂₅ μ⌉ ≈ 200 at μ = 10¹¹,
  each O(m) bytes — still negligible; clone cost amortizes to nothing.
- `r_resumable` persists `power` → schedule state changes → **bump
  `CKPT_VERSION` to 3** and update the format docstring. Confirm an old
  checkpoint is rejected with a clean error.
- The CLAUDE.md "Brent needs ~2× repeat_after" note becomes "~1.2×"; update it
  and the load-bearing-invariants section.
- This is the one stage that changes *which* steps are walked, not just how
  fast: run the **full** `scan --m-range 1..=1349` diff against
  `results_new.csv` (signatures included) before declaring it done.

### Stage 3 — u8 shadow table for the hot loop (bench-gated, mainly m ≳ 1200, ~2–3 h)

τ ≤ 96 for every value ≤ 30 K, so the entire empirical orbit range fits u8.
Build a `Vec<u8>` shadow of `fac_table` with 255 as an "overflow" sentinel
falling back to the u16 table (branch never taken in practice, perfectly
predicted). Halves the hot footprint: 55 KB → 27.5 KB at m ≈ 1750 — the
L2-resident regime of the mega-trials becomes (mostly) L1-resident, cutting
the dependent chain from ~12 to ~5 cycles where it matters most. Costs 16 MB
RAM. Expect little at m ≤ 1000 (already L1); gate on a bench at
m ∈ {700, 1500} (see bench changes below).

### Stage 4 — thread count + dispatch order (bench-gated, ~1 h)

- After Stages 0–2, bench a heavy mixed range (e.g. `--m-range 690..=760`)
  with `--threads 16` vs `--threads 8`. Keep the winner as the documented
  recommendation; only change the default if 8 wins clearly.
- Dispatch trials in **descending m** within `run_stream` so the probable
  mega-trials start first (LPT-style). The consumer already reorders output to
  ascending m, and holding completed `RResult`s is cheap. This protects
  against the worst case where the longest trial is scheduled last and runs
  alone at the end.

### Stage 5 — optional: explicit N=2 interleave (only if Stage 4 says latency-bound)

Run only if, after Stages 0–3, per-step cycles at large m still sit well above
the instruction-throughput floor *and* `--threads 8` beats 16 (i.e. SMT is not
already harvesting the latency). Design notes from the old plan (a `step2` on
`[State; 2]`, paired Brent bookkeeping, fall back to single-stream when one
trial finishes, pair-chunked dispatch in `run_stream`) remain valid. Honest
expectation over SMT: **1.0–1.3×**, for the largest code change in the plan —
which is why it is last.

### Micro-tier (opportunistic, each individually bench-gated)

- Hoist the tortoise's hash into a local register across the inner loop
  (refresh on snapshot push) instead of `snapshots.last()` + field load every
  step — the compiler cannot prove non-aliasing and likely reloads.
- Interleave `window` and `div_counts` into one ring of packed entries so each
  step touches one stream, not two. Marginal; only if profiling shows store
  pressure.

## What does not pay on this hardware (settled)

SIMD gather (microcoded on Zen 2), Vega 7 iGPU offload, software prefetch on
the dependent chain, removing the `fac_table` bounds check, and eliminating
`div_counts`. Parallelizing *within* a trial is impossible — the recurrence is
inherently sequential — so once the bulk of a scan drains, the longest trial
is a hard wall-clock floor; only per-step cost (Stages 0/1/3) and the
detection schedule (Stage 2) move it.

## Verification (per stage)

1. **Correctness gate** — `cargo test --release`, then the CLAUDE.md
   spot-check (m=560..=572 vs `results_new.csv`, empty diff; m=569 is the
   historically tricky one).
2. **Perf gate** — `cargo bench --bench r` before/after. Extend the sweep to
   add m=1024 (335 M steps, fits a larger cap) and a **fixed-step bench** at
   m=1500 (`max_length = 100 M + m`, timing the capped timeout path) so the
   large-m cache regime is measurable without the 42 B-step full trial.
3. **Stage 2 only: full-history gate** — fresh `scan --m-range 1..=1349`,
   whole-CSV diff vs `results_new.csv` including signature-derived columns.
4. **Checkpoint gate (Stage 2)** — old version rejected cleanly;
   checkpoint-then-resume reproduces the non-resumed `RResult`.

## Expected cumulative

| stage | basis | factor |
|-------|-------|--------|
| 0 — build flags | measured | ~1.18× |
| 1 — τ-tracking gated | measured | ~1.9× |
| 2 — geometric Brent | derived (validated step counts) | ~1.5–1.7× avg on long trials |
| 3 — u8 table | bench-gated | ~1.0–1.4× (large m only) |
| 4/5 — threads/interleave | bench-gated | ~1.0–1.3× |

Stages 0–2 alone: **~3.4–3.8× on the long-tail trials** that dominate scan
wall-clock, for roughly 8–10 hours of work — ahead of the old plan's 2.5–4.5×
promise at less than half the engineering risk, with the two biggest factors
already measured rather than estimated.

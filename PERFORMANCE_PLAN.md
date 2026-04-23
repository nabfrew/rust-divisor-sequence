# Performance Plan — Divisor-Sequence Brent Loop on Ryzen 7 4800H                                                                                                                                                                                                                                         
## Context                                                                                                                                                                                                                                                                                                
The CLI already runs trial-level rayon parallelism, a Rabin-Karp rolling-hash                                                                                                                                                                                                                             
cycle check (≈4× at m=512), and a snapshot-stack `find_cycle_start` (≈2× on                                                                                                                                                                                                                             
long-μ). Wall-clock is now dominated by the inner `State::step` loop running                                                                                                                                                                                                                            
billions of times per long-tail trial: m=700 needs 2.8×10⁸ steps, m=1654 needs
.4×10¹¹. The user wants the next round of speedups, including SIMD/GPU if
they pay off on this hardware.
**Hardware:** AMD Ryzen 7 4800H (Zen 2), 8C/16T, AVX2+FMA+BMI2, **no AVX-512**.
L1d 32 KB/core, L2 512 KB/core, L3 8 MB shared. Vega 7 iGPU only — no discrete
GPU; ROCm/HIP on Windows is poor; iGPU shares DRAM bandwidth with the CPU.
**Bottleneck identified.** `State::step` (`src/lib.rs:157-185`) has a
loop-carried dependent-load chain:
```
div_sum[t]  →  fac_table[div_sum[t]]  →  new_d[t]  →  div_sum[t+1]
```
`fac_table` is 256 KB (fits L2, not L1), and `div_sum` indexes it
unpredictably. The critical path per step is one ~12-cycle L2-latency load.
Zen 2 has ~10 outstanding L1 misses per core (MLP=10), but a single trial only
exploits MLP=1 because each step waits on the previous load. The OoO engine
cannot speculate past this because the next load's address depends on the
current load's value.
**SIMD and GPU are dismissed up front and not part of this plan:**
- `vpgatherqq` on Zen 2 is microcoded (~5–7 cyc/lane, slow setup); a 4-wide
SIMD gather is slower than four scalar dependent loads issued in parallel
via OoO. The dependent-load chain also blocks single-trial SIMD.
- Vega 7 iGPU is weak on integer-gather workloads, ROCm-on-Windows is
unreliable, and the iGPU competes with the CPU for the same DRAM. Porting
cost is high; expected speedup is negative.
The plan below exploits the actual win available on this hardware: hide the
dependent-load latency by running multiple independent streams per worker
thread (memory-level parallelism), and clean up wasted cycles in the inner
loop along the way.
---
## Recommended approach (staged, ship in order)
### Stage 1 — Tier 1 quick wins (~1.1–1.5× combined, ~3 hours)
**1.1. Eliminate bounds checks and panic formatting in `State::step`.**
Current `step` has five indexed accesses per iteration plus a `match` on
`fac_table.get(div_sum)` whose `None` arm calls `panic!` with `format!(...)`.
LLVM keeps that panic block live, which throttles inlining and register
allocation on the dependent-load critical path. This is not a micro-cleanup —
it's likely 5–25% on its own.
- Hoist a one-time check at trial start: assert `fac_table.len() > MAX_DIV_SUM`
where `MAX_DIV_SUM = m * MAX_TAU` (or simply assert at construction that
`div_sum` will never exceed `fac_table.len() - 1` for the configured ranges).
- Inside `step`, use `*fac_table.get_unchecked(self.div_sum)` and
`*self.window.get_unchecked(head)` / `get_unchecked_mut`. `head` is invariant
`< window.len()` by construction; assert once on entry.
- Keep a debug-build `debug_assert!` so tests still catch any regression.
**1.2. Default `--threads` to physical core count (8), not logical (16).**
`src/main.rs:188-189` already builds `rayon::ThreadPoolBuilder::new()
.num_threads(cli.threads)` and `cli.threads = 0` falls through to rayon's
default (= 16 logical). The current single-stream code is memory-latency bound,
so SMT helps a little; once Stage 2 ships and each thread is MLP-saturated
internally, SMT will fight for L1d/L2 bandwidth and become a regression.
- Change the CLI default to `8` (physical cores), or make the default be
`num_cpus::get_physical()`.
- Run a baseline bench *now* with `--threads 8` vs `--threads 16` to confirm
the current code isn't already losing to SMT contention. Keep whichever
wins for the Stage-1 release.
### Stage 2 — Combined refactor: N=2 multi-trial interleave + drop `div_counts` (~1.8–2.5× over Stage 1, ~12–16 hours)
This is the main engineering work. Two changes that share the same inner-loop
rewrite, so they ship together:
**2.1. Multi-trial interleaving (N=2).**
Process two independent trials per rayon task, advancing both one step at a
time inside a tight inner loop. The CPU's OoO engine then has two independent
dependent-load chains in flight simultaneously, so trial-A's L2 latency is
hidden by trial-B's compute and vice versa.
- Introduce `step2(states: &mut [State; 2], fac_table: &[u8]) -> [u16; 2]`
that issues both gathers, both window reads, both stores back-to-back.
The two trials share the same `fac_table` — same cache lines, no extra
pressure.
- Add an `r_inner_pair` analogue of `r_inner` (`src/lib.rs:295`) that drives
two trials through the Brent loop with a shared step counter and per-trial
snapshot stacks / cycle bookkeeping. Each trial detects its cycle
independently; when one finishes, fall back to the single-stream `r_inner`
for the surviving one (avoids wasting cycles on a finished trial).
- Wire `run_stream` (`src/main.rs:561`) to chunk the trial list into pairs
before dispatching to rayon, dispatching the leftover singleton through the
existing single-trial path.
- Why N=2 first, not N=4: at m=1500, `State` is ~4.5 KB, so N=4 puts 18 KB
of active per-trial state in L1d (32 KB, 8-way assoc). Conflict-miss risk
is real at large m. N=2 is comfortably safe; N=4 is bench-gated in Stage 3.
**2.2. Eliminate `div_counts: Vec<u8>`.**
Currently `div_counts[head]` exists only to know what to subtract from
`div_sum` when the slot is overwritten. But that count was already determined
exactly `m` steps ago when the slot was *written*. Replace with a recompute:
```rust
self.div_sum -= fac_table[self.window[head] as usize] as usize;
```
This adds a *second* `fac_table` load per step — but its address is
`old_value`, **independent** of the gather on `div_sum`. So within a single
trial the in-trial MLP rises from 1 to 2: the CPU can issue both loads in
parallel.
Combined with 2.1, effective MLP per worker becomes ~4, matching what raw
N=4 would give but with **half the per-state L1 footprint** (no more
`div_counts` ring). The State struct shrinks by `m` bytes; for m=1500 that's
~30% smaller, so Stage 3 (N=4) becomes more viable too.
`State.div_counts` is referenced from `State::initial`, `State::from_window`,
`State::step`, `State::window_eq_slow` (line 191 — checks `div_sum` not
`div_counts` directly, so OK), and from checkpoint serialization. The
checkpoint format docstring above `CKPT_MAGIC` will need updating; bump
`CKPT_VERSION` per the load-bearing invariant in CLAUDE.md.
**2.3. Verification gate.**
Bit-for-bit compare every field of `RResult` (including `signature`, the
SHA256 of the cycle's value-multiset) between single-stream and pair-stream
runs across a non-trivial range. The CLAUDE.md spot-check on m=560..=572 is
the established gate; extend it to include the cycle-stat columns. Pass
criterion = empty diff vs `results_new.csv`.
### Stage 3 — N=4 multi-trial (bench-gated, ~1.0–1.3× over Stage 2, ~4–6 hours)
After Stage 2 lands, generalise `step2` to `step_n::<N>(states: &mut [State; N], ...)`
and try N=4. Bench at m ∈ {512, 700, 1024, 1500, 2000}. Ship N=4 only if it
wins at *all* tested m's; otherwise keep N=2. Likely outcome: N=4 wins at
small/medium m, regresses at m≥1500 due to L1d conflict misses, in which case
make N a per-m choice (small/medium m bundled into 4-tuples, large m into
pairs).
### Stage 4 — Software prefetch (bench-gated, ~1.05–1.15×, ~2–4 hours)
In the multi-stream loop, before issuing trial-A's next-step compute, emit
`_mm_prefetch::<_MM_HINT_T0>(...)` on `fac_table.as_ptr().add(state_b.div_sum)`
so trial-B's *next* gather is in-flight while trial-A computes. Use
`std::arch::x86_64::_mm_prefetch`; no new deps. Ship only if it shows ≥5%.
---
## Critical files
- `src/lib.rs` — all hot-path code:
- `State` struct (84-92): drop `div_counts` field
- `State::step` (157-185): bounds-check elimination, recompute `div_sum -=`
via `fac_table[old_value]`
- `State::initial`, `State::from_window`, `window_eq_slow`: drop
`div_counts` plumbing
- `r_inner` (295): factor inner loop so single-stream path remains
- new `r_inner_pair` / `step2` entry points
- `CKPT_MAGIC` block and `read_state`/`write_state`: bump `CKPT_VERSION`
- `src/main.rs`:
- `run_stream` (561): pair-chunk dispatch, fall-back to single-trial for
odd leftover
- `run_basin_scan` (~803): same pair-chunking — basin-scan is an *ideal*
multi-stream beneficiary because all trials at a given m share the same
`fac_table` and have identical state shape; group by m and batch seeds
- CLI `--threads` default change (or use `num_cpus::get_physical()`)
- `benches/r.rs`: extend the m sweep to `{16, 64, 256, 512, 700, 1024, 1500}`
and add a `pair` group benching the new `r_inner_pair` path so stage gates
are measurable
- `tests/reference.rs`: existing m ∈ {1,2,3,5,8} reference still passes; add
a "pair vs single equivalence" test running the same m through both paths
and asserting `RResult` equality
- `Cargo.toml`: add `num_cpus` (only if used for the threads default)
- `CLAUDE.md`: update load-bearing-invariants section to reflect that
`div_counts` is gone and that `step` reads `fac_table` twice per step
## Verification
End-to-end checks before declaring each stage done:
1. **Correctness gate** — `cargo test --release` (full reference + new
pair-equivalence test) plus the spot-check from CLAUDE.md:
```bash
cargo run --release --quiet -- --progress-interval 0 \
scan --m-range 560..=572 --output /tmp/spot.csv
diff <(awk -F',' 'NR>1 { gsub(/ /,""); print }' /tmp/spot.csv) \
<(awk -F',' 'NR>1 && $1>=560 && $1<=572 { gsub(/ /,""); print }' \
results_new.csv)
```
Empty diff is the pass criterion. m=569 is the historically tricky one.
2. **Perf gate** — `cargo bench --bench r` before and after each stage.
Record numbers for {16, 64, 256, 512, 700, 1024, 1500}. Ship a stage only
if its bench delta matches the predicted range; if not, root-cause first.
3. **Long-run sanity** — for Stage 2 specifically, run a fresh
`scan --m-range 1..=1349 --output /tmp/full.csv` and diff the entire CSV
against `results_new.csv`. Cycle signatures (the SHA256 column) catch any
subtle inner-loop drift that aggregate stats might mask.
4. **Checkpoint compatibility** — Stage 2 bumps `CKPT_VERSION`. Confirm an
old checkpoint is rejected with a clean error, and a fresh
checkpoint-then-resume still produces the same `RResult` as a non-resumed
run.
## Expected cumulative speedup
- Stage 1: 1.1–1.5× on long-tail trials, ~free
- Stage 2: 1.8–2.5× over Stage 1
- Stage 3: 1.0–1.3× over Stage 2 (m-dependent)
- Stage 4: 1.05–1.15× over Stage 3
Total realistic: ~2.5–4.5× on the long-tail trials that dominate wall-clock.
Smaller m (already L1-resident) gain less. Whole-scan wall-clock for
`scan 1..=2000` should drop substantially.
# Build and test

- Use `--release` everywhere — debug builds are 50–100× slower and the reference tests won't finish at m ≥ 64. Always run `cargo test --release`, `cargo bench --bench r`, and `cargo run --release -- ...`.
- `tests/reference.rs` covers m ∈ {1, 2, 3, 5, 8} only. Bugs that only surface at large m won't be caught.
- Single test: `cargo test --release <test_name>`, e.g. `cargo test --release brent_matches_reference_small_m`.

# Commit

- Commit changes with descriptive message in conventional commites format.

# Architecture

- `r() → r_with_progress() → r_resumable()` is a layered API: each is a strict superset of the previous, sharing the Brent main loop on `State`. `r()` is a no-progress wrapper used by tests/benches; `r_with_progress` adds a heartbeat callback for the CLI; `r_resumable` adds checkpoint save/load on top.
- `find_cycle_start` runs *after* Brent detects a cycle; it walks the snapshot stack newest → oldest to pick the most recent pre-cycle state, then lock-steps tortoise/hare from there to find μ. This replaces the original "replay from step 0" recovery and is roughly 2× faster on long-μ trials.
- `main.rs::run_stream` drives all trials: a `std::thread` runs `into_par_iter().for_each_with(tx, ...)` on the rayon pool, sending each completed `(m, RResult)` through an mpsc channel. The consumer (main thread) holds completed-but-not-yet-flushable results in a `HashMap` and emits them to the on-result callback strictly in m-order, so the CSV stays sorted even though completion order is arbitrary. This replaces the old fixed-batch design where one slow m stalled all peers.
- Checkpoint format is documented inline above the `CKPT_MAGIC` constant in `lib.rs`. Persists only what's not derivable: window, hash, head, plus the Brent loop bookkeeping (`steps`, `power`, `lam`, `max_value`, snapshot list).

# Verifying perf changes

Before declaring a perf change correct, spot-check a non-trivial range bit-exactly against the recorded results:

```bash
cargo run --release --quiet -- --progress-interval 0 scan --m-range 560..=572 --output /tmp/spot.csv
diff <(awk -F',' 'NR>1 { gsub(/ /,""); print }' /tmp/spot.csv) \
     <(awk -F',' 'NR>1 && $1>=560 && $1<=572 { gsub(/ /,""); print }' results_new.csv)
```

Empty diff is the pass criterion. m=560..=572 covers the historically tricky m=569 and runs in ~4 s. `results_new.csv`, `results_new_2.csv`, etc. are the user's accumulated ground-truth results.

# Brent needs ~2× repeat_after to detect

Cycle detection fires at the next power-of-two step ≥ μ, then runs another λ steps. If `--max-steps` is below roughly 2 × repeat_after, the trial times out even though the algorithm "should" have found the cycle. Account for this when sizing test caps — picking `--max-steps 500_000_000` for an m with `repeat_after = 277_000_000` is **not** enough, you need ~600M+.

# Load-bearing invariants in src/lib.rs

- `State.hash` is a Rabin-Karp rolling hash mod 2⁶⁴; `window_eq` short-circuits on it and that's the main perf win (≈4× at m=512). Don't compare windows without going through `window_eq`.
- `r()` retains **all** power-of-two snapshots in `snapshots: Vec<(usize, State)>`. `find_cycle_start` walks them newest → oldest to avoid replaying from step 0. Don't collapse this back to a single snapshot.
- `div_counts`, `div_sum`, and `b_pow_m_minus_1` are derivable from `window` + `fac_table` and are **not** persisted in checkpoints — `read_state` reconstructs them on load. Bump `CKPT_VERSION` on any incompatible format change.
- `r()` is the no-progress wrapper around `r_with_progress`. Tests and benches call `r()`; keep that signature stable.

# Stale-binary lock on Windows

If a `cargo run` is killed externally (timeout, Ctrl-C through a wrapper, etc.), the spawned binary can outlive cargo and hold a lock on `target/release/divisor_series.exe`, breaking the next `cargo build` with `Access is denied (os error 5)`. Recover with PowerShell:

```powershell
Get-Process | Where-Object { $_.ProcessName -like "divisor*" } | Stop-Process -Force
```

The user runs hours-long scans on this binary. **Confirm with them before force-killing** if any might be in flight.

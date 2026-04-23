# divisor-series

Numerical exploration of the sequence

> R(n, m) = τ(R(n−1, m)) + τ(R(n−2, m)) + … + τ(R(n−m, m)),  seeded with R(1..m, m) = 1

where τ(k) is the number of divisors of k. For each m the sequence lives in a finite state space (the last m terms), so it must eventually cycle. The interesting quantities are when it first repeats and how large the terms get.

## What's in here

- `src/lib.rs` — `r(m, max_steps, fac_table) -> RResult`, Brent cycle detection on the sliding-window state (O(m) memory). The window carries a Rabin-Karp rolling hash so the tortoise/hare comparison is O(1) per step instead of O(m), and Brent retains all power-of-two snapshots so cycle-start recovery replays from the most recent pre-cycle snapshot rather than step 0. When a cycle is found `RResult` also carries per-cycle summary statistics (length, min/max, most common tail value, distinct-value count); the full period itself is not materialised — at larger m it can reach 10^7+ terms. `build_fac_table(n)` is a linear SPF sieve producing `τ(0..n)`. Two extra entry points: `r_with_progress` accepts a heartbeat callback, and `r_resumable` periodically writes a sidecar checkpoint and resumes from it if one exists.
- `src/main.rs` — clap CLI that streams `r` over ranges of m through rayon's work-stealing scheduler.
- `results.csv`, `results_500.csv` — per-m results from earlier runs in the legacy 3-column format (`m, repeat_after, max_value`); accepted as input to `revisit`. The parser also tolerates tab-separated rows (some old `<m>\tNone\tNone` timeout lines mix that style in). A fresh `scan` emits the 8-column format described below and supersedes `compiled_results.csv`.
- `compiled_results.csv` — older output with an extra `most common value in tail` column. Kept for reference; the new `scan` output is a strict superset.
- `analysis/explore.ipynb` — the consolidated analysis document: problem statement, bounded-orbits proof, empirical structure (m·ln m band, conservation law, the length-(m+1) K-invariant, fixed points, sustained ceiling, attractors, basin scans), and the further-work list. Generated from `analysis/_build_explore_nb.py`.
- `PERFORMANCE_PLAN.md` — engineering plan for the inner-loop speedups (memory-level parallelism, bounds-check elimination).
- `benches/r.rs` — criterion benches at m ∈ {16, 64, 256, 512, 700} (run via `cargo bench`).

## Build

```
cargo build --release
```

The toolchain is pinned to Rust 1.95 in `rust-toolchain.toml`.

## Usage

```
divisor_series [OPTIONS] <COMMAND>
```

Global options:

| Flag | Default | Meaning |
| --- | --- | --- |
| `--max-steps N` | `10_000_000_000` | Give up after N terms without a cycle. |
| `--threads N` | `0` | Rayon worker threads (`0` = rayon default). |
| `--fac-table-size N` | `262_144` | Entries in the precomputed τ table. `r()` panics if a term exceeds this. |
| `--progress-interval N` | `100_000_000` | Print a heartbeat every N steps within each in-flight trial (`0` disables). |
| `--checkpoint-dir DIR` | unset | If set, every trial saves a sidecar `m{m}.ckpt` and resumes from it on restart. The directory is created if missing. The file is deleted on cycle detection and preserved on timeout (so re-running with a higher `--max-steps` resumes the search). |
| `--checkpoint-interval N` | `1_000_000_000` | Save the checkpoint every N steps (`0` disables saves; existing checkpoints are still loaded). |

`--batch-size` is accepted for backwards compatibility but ignored — trials now stream through rayon's work-stealing scheduler, so there are no batches and a single slow m no longer stalls peers.

### `scan` — sweep a range of m

```
cargo run --release -- scan --m-range 1..=2000 --output results.csv
```

`--m-range` accepts inclusive `START..=END` or half-open `START..END`. Output CSV columns:

```
m, repeat_after, max_value, most_common_tail_value,
cycle_length, cycle_max, cycle_min, distinct_tail_values
```

Rows that hit `--max-steps` without cycling write `None` for every field except `m`. The full cycle sequence is intentionally *not* stored: cycle lengths cross 10^7 by m ≈ 600, so reproducing a specific period means re-running `r` with that single m.

### `revisit` — re-run unresolved rows with a larger budget

```
cargo run --release -- revisit \
    --input  results.csv \
    --output results.csv \
    --max-steps 100_000_000_000
```

Reads `--input` (either the legacy 3-column format or the 8-column format above), re-runs only the rows whose `repeat_after` is `None` at the current `--max-steps`, and writes a merged CSV to `--output` in the 8-column format (row order preserved; `--input == --output` overwrites in place). Rows that came from a legacy 3-column input and already had a `repeat_after` are preserved as-is, with the new cycle columns left as `None` — only the newly-resolved rows are fully populated.

## Tuning notes

- `--fac-table-size` must exceed the largest term emitted. In observed data `max_value / m ≲ 14` (e.g. m=806 → 12594, see `results_500.csv:807`), so the default `1 << 18` clears m up to ~18 000 with margin.
- Per-trial memory is `O(m)` for the current window plus `O(m × log₂ steps)` for the snapshot stack (~33 snapshots at `--max-steps 10¹⁰`). At m = 2000 that's ~140 KB per in-flight trial, so concurrency is bounded by `--threads`, not memory.
- `--max-steps` is the dominant knob for "None" rows. `revisit` exists specifically to chip away at gaps that appear when the range is extended or a previous run used too tight a budget. Brent cycle detection needs roughly `2 × repeat_after` steps to fire, so set the cap accordingly.
- For long runs (hours per m at large m), set `--checkpoint-dir`. A killed/crashed process loses at most `--checkpoint-interval` steps of progress; on restart each trial picks up from its sidecar `.ckpt`. Resuming with a different `--max-steps` is safe — the runtime state is independent of the cap.

## Analysis notebook

`analysis/explore.ipynb` is the consolidated analysis document — structured from an introduction to the problem through everything currently understood (bounded orbits, the m·ln m band, the conservation law `mean_v = m·mean_τ`, the length-(m+1) invariant `x + τ(x) = K`, the full fixed-point catalogue, the sustained ceiling M*(m), the attractor catalogue, and the random-seed basin scans), ending with a Further-work section. It reads `results_new.csv`, `gaps.csv`, and the per-m artefacts under `analysis/`.

Install the Python deps once:

```
python -m pip install pandas matplotlib jupyter nbformat
```

Open interactively:

```
jupyter lab analysis/explore.ipynb
```

Or execute headlessly (the verification path — re-emits every figure into the `.ipynb`):

```
jupyter nbconvert --to notebook --execute --inplace analysis/explore.ipynb
```

Regenerate from source after changing the chart set or the data merge:

```
python analysis/_build_explore_nb.py
jupyter nbconvert --to notebook --execute --inplace analysis/explore.ipynb
```

`_build_explore_nb.py` is the text source of truth; the `.ipynb` is its (committed) build output. Static-export the executed notebook to HTML for sharing with `jupyter nbconvert --to html analysis/explore.ipynb`.

Open analysis threads live in §12 ("Further work") of `analysis/explore.ipynb`; see `PERFORMANCE_PLAN.md` for the engineering perf plan (rolling hash, snapshot-based mu recovery, heartbeat, checkpointing, work-stealing history plus the staged MLP plan).

# divisor-series

Numerical exploration of the sequence

> R(n, m) = τ(R(n−1, m)) + τ(R(n−2, m)) + … + τ(R(n−m, m)),  seeded with R(1..m, m) = 1

where τ(k) is the number of divisors of k. For each m the sequence lives in a finite state space (the last m terms), so it must eventually cycle. The interesting quantities are when it first repeats and how large the terms get.

## What's in here

- `src/lib.rs` — `r(m, max_steps, fac_table) -> RResult`, Brent cycle detection on the sliding-window state (O(m) memory). When a cycle is found `RResult` also carries per-cycle summary statistics (length, min/max, most common tail value, distinct-value count); the full period itself is not materialised — at larger m it can reach 10^7+ terms. `build_fac_table(n)` is a linear SPF sieve producing `τ(0..n)`.
- `src/main.rs` — clap CLI that drives `r` over ranges of m in parallel via rayon.
- `results.csv`, `results_500.csv` — per-m results from earlier runs in the legacy 3-column format (`m, repeat_after, max_value`); accepted as input to `revisit`. A fresh `scan` emits the 8-column format described below and supersedes `compiled_results.csv`.
- `compiled_results.csv` — older output with an extra `most common value in tail` column. Kept for reference; the new `scan` output is a strict superset.
- `ROADMAP.md` — performance-rewrite and math-output plan.

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
| `--batch-size N` | `8` | Parallel batch size. |

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
- For large m, shrink `--batch-size` — each worker holds its own ring buffer, and peak memory scales as `batch_size × O(m)`.
- `--max-steps` is the dominant knob for "None" rows. The current `results.csv` (m = 1..=831) has no unresolved rows; `revisit` exists specifically to chip away at gaps that appear when the range is extended or a previous run used too tight a budget.

See `ROADMAP.md` for the broader plan (cycle-length / tail statistics, OEIS b-files, notebook).

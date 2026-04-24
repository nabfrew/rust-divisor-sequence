# divisor-series

Numerical exploration of the sequence

> R(n, m) = τ(R(n−1, m)) + τ(R(n−2, m)) + … + τ(R(n−m, m)),  seeded with R(1..m, m) = 1

where τ(k) is the number of divisors of k. For each m the sequence lives in a finite state space (the last m terms), so it must eventually cycle. The interesting quantities are when it first repeats and how large the terms get.

## What's in here

- `src/lib.rs` — `r(m, max_steps, fac_table) -> RResult`, Brent cycle detection on the sliding-window state (O(m) memory). `build_fac_table(n)` is a linear SPF sieve producing `τ(0..n)`.
- `src/main.rs` — clap CLI that drives `r` over ranges of m in parallel via rayon.
- `results.csv`, `results_500.csv` — per-m results, columns `m, repeat_after, max_value`.
- `compiled_results.csv` — older output with an extra `most common value in tail` column; superseded by upcoming work (see `ROADMAP.md`, Phase B).
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

`--m-range` accepts inclusive `START..=END` or half-open `START..END`. Output CSV columns: `m, repeat_after, max_value`. Rows that hit `--max-steps` without cycling are written as `m, None, None`.

### `revisit` — re-run unresolved rows with a larger budget

```
cargo run --release -- revisit \
    --input  results.csv \
    --output results.csv \
    --max-steps 100_000_000_000
```

Reads `--input`, re-runs only the rows whose `repeat_after` is `None` at the current `--max-steps`, and writes a merged CSV to `--output` (row order preserved; `--input == --output` overwrites in place).

## Tuning notes

- `--fac-table-size` must exceed the largest term emitted. In observed data `max_value / m ≲ 14` (e.g. m=806 → 12594, see `results_500.csv:807`), so the default `1 << 18` clears m up to ~18 000 with margin.
- For large m, shrink `--batch-size` — each worker holds its own ring buffer, and peak memory scales as `batch_size × O(m)`.
- `--max-steps` is the dominant knob for "None, None" rows. The current `results.csv` has a handful of unresolved rows around m ∈ {665, 666, 670, 671}; `revisit` exists specifically to chip away at these.

See `ROADMAP.md` for the broader plan (cycle-length / tail statistics, OEIS b-files, notebook).

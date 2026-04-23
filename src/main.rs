use std::{
    collections::{HashMap, HashSet},
    fs::File,
    io::{BufRead, BufReader, Write},
    path::{Path, PathBuf},
    sync::{Arc, mpsc},
    time::{Duration, Instant},
};

use clap::{Parser, Subcommand};
use rayon::prelude::{IntoParallelIterator, ParallelIterator};

use divisor_series::{
    Progress, ProgressPhase, RResult, build_fac_table, r_resumable, r_seeded_with_progress,
    r_with_progress,
};

/// Explore the divisor-sum sequence R(n, m) over ranges of m.
#[derive(Parser, Debug)]
#[command(version, about)]
struct Cli {
    /// Maximum sequence length to search before giving up. Default
    /// `usize::MAX` means "no cap" — the bounded-orbit proof guarantees every
    /// trial terminates, and capping previously produced misleading
    /// partial-trial CSV rows. Set to a finite value only for forensic
    /// short-circuits (debug runs, smoke tests).
    #[arg(long, default_value_t = usize::MAX, global = true)]
    max_steps: usize,

    /// Number of rayon worker threads. 0 uses rayon's default (≈ logical CPUs).
    #[arg(long, default_value_t = 0, global = true)]
    threads: usize,

    /// Size of the precomputed divisor-count table (τ(0..N)). Must exceed
    /// every value the run could emit; r() panics with `index out of bounds`
    /// otherwise. Default 1 << 24 = 16 M entries (32 MB at u16) covers any
    /// trajectory the bounded-orbit proof admits for m up to ~2 000.
    #[arg(long, default_value_t = 1usize << 24, global = true)]
    fac_table_size: usize,

    /// Deprecated. The runner now streams trials through rayon's work-stealing
    /// scheduler so a single slow m no longer stalls a whole batch; this flag
    /// is accepted for compatibility but ignored.
    #[arg(long, default_value_t = 8, global = true, hide = true)]
    batch_size: usize,

    /// Print a heartbeat every N steps within each in-flight trial.
    /// 0 disables heartbeats. Default 100M ≈ 1 line/sec at large m.
    #[arg(long, default_value_t = 100_000_000, global = true)]
    progress_interval: usize,

    /// Directory in which to write per-trial checkpoint files (one per m).
    /// If unset, no checkpoints are written and crash-resume is disabled.
    /// If set, the directory is created if missing; each trial writes
    /// `m{m}.ckpt` and resumes from it on restart. The file is deleted on
    /// successful completion and preserved on timeout.
    #[arg(long, global = true)]
    checkpoint_dir: Option<PathBuf>,

    /// Save a checkpoint every N steps within each in-flight trial. 0
    /// disables saves (existing checkpoints are still loaded). Default
    /// 1B steps ≈ once every 10 s at large m.
    #[arg(long, default_value_t = 1_000_000_000, global = true)]
    checkpoint_interval: usize,

    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand, Debug)]
enum Command {
    /// Scan a range of m and write a CSV with per-m result + cycle statistics.
    Scan {
        /// Range of m, inclusive on both ends, e.g. `1..=2000` or `1..2001`.
        #[arg(long, value_parser = parse_range, default_value = "1..=2000")]
        m_range: (usize, usize),

        /// Output CSV path.
        #[arg(long, default_value = "results.csv")]
        output: PathBuf,

        /// Additional result CSV(s) to treat as read-only sources of
        /// already-completed m's. Any m appearing in any `--skip-from` file
        /// (regardless of row order) is excluded from the work list, the same
        /// way m's already in `--output` are. Repeat the flag to pass several:
        /// `--skip-from results_new.csv --skip-from results_new_4.csv`. Lets a
        /// fresh `--output` shard pick up from a prior shard without having to
        /// merge or copy the old rows in first.
        #[arg(long)]
        skip_from: Vec<PathBuf>,

        /// Per-m attractor-signature output directory. For every m whose trial
        /// resolves a cycle, scan writes `<dir>/<m>.csv` (the value→count
        /// multiset, sorted by value — byte-identical to `dump-signature`'s
        /// output). Files that already exist with non-zero size are left
        /// untouched, matching `analysis/build_attractors.py`'s idempotent
        /// reuse contract. Skipped on timeout (no signature to write).
        #[arg(long, default_value = "analysis/cycle_signatures")]
        signatures_dir: PathBuf,
    },
    /// Re-run rows whose repeat_after is 'None' with the current --max-steps
    /// and write a refreshed CSV in the new format.
    Revisit {
        /// Existing CSV produced by a previous run. Old 3-column CSVs are accepted.
        #[arg(long)]
        input: PathBuf,

        /// Output CSV path. May equal --input to overwrite in place.
        #[arg(long)]
        output: PathBuf,
    },
    /// Re-run a single m and write the cycle's value→count multiset (the attractor
    /// "signature") to a CSV. Output rows are sorted by value so two runs on the
    /// same m produce byte-identical output. The ordered period is never
    /// materialised — periods of 10⁷+ terms exist at large m.
    DumpSignature {
        /// The single m to dump.
        #[arg(long)]
        m: usize,

        /// Output CSV path (`value,count` per line, sorted by value).
        #[arg(long)]
        output: PathBuf,
    },
    /// Random-seed basin-of-attraction probe (analysis/explore.ipynb §11). For each m in
    /// `--m-list`, run `--trials` trials with the m-element window seeded by
    /// independent draws from `round(LogNormal(ln(m·ln m), sigma))`. Output
    /// rows are sorted by (m, trial_idx) and carry the attractor's distinct
    /// value set so a Python pipeline can join to `analysis/attractors.csv`.
    BasinScan {
        /// Comma-separated explicit list of m's (e.g. `127,167,211`),
        /// or `START..=END:N` for N log-stepped samples (e.g. `100..=1500:50`).
        #[arg(long)]
        m_list: String,

        /// Trials per m.
        #[arg(long, default_value_t = 200)]
        trials: usize,

        /// Standard deviation of the log-normal seed distribution. Default
        /// 0.71 puts the central 95% over a factor-16 spread — enough to
        /// straddle the seed=1 cycle band (analysis/explore.ipynb §11).
        #[arg(long, default_value_t = 0.71)]
        sigma: f64,

        /// Master RNG seed for reproducibility. Per-trial RNG state is
        /// derived deterministically from `(rng_seed, m, trial_idx)`.
        #[arg(long, default_value_t = 42u64)]
        rng_seed: u64,

        /// Optional seed=1 results CSV. When set, the per-trial cap is
        /// `cap_multiplier · repeat_after_seed_1(m)`; otherwise falls back to
        /// the global `--max-steps`. Trials whose m is not in the CSV (or
        /// whose seed=1 row is `None`) use the global `--max-steps`.
        #[arg(long)]
        seed_1_csv: Option<PathBuf>,

        /// Multiplier on `repeat_after_seed_1(m)` when `--seed-1-csv` is set.
        #[arg(long, default_value_t = 5)]
        cap_multiplier: usize,

        /// Coefficient C on `m²` for a per-trial cap floor: the effective cap
        /// becomes `max(cap_multiplier · r_seed1(m), C · m²)`. With C=100 and
        /// m=140 (where `r_seed1` = 3215 → 5× cap = 16k), the floor lifts the
        /// cap to ≈2 M, enough for the random-seed transient. Set to 0 to
        /// disable the floor.
        #[arg(long, default_value_t = 100)]
        cap_floor_c_m_sq: usize,

        /// If set, append to an existing output CSV and skip any
        /// `(m, trial_idx)` pair already present. Lets a long run survive
        /// kills/crashes and pick up where it left off.
        #[arg(long, default_value_t = false)]
        resume: bool,

        /// Output CSV path.
        #[arg(long)]
        output: PathBuf,
    },
}

fn parse_range(s: &str) -> Result<(usize, usize), String> {
    let s = s.trim();
    let (start_str, end_str, inclusive) = if let Some(idx) = s.find("..=") {
        (&s[..idx], &s[idx + 3..], true)
    } else if let Some(idx) = s.find("..") {
        (&s[..idx], &s[idx + 2..], false)
    } else {
        return Err(format!("expected START..=END or START..END, got {s:?}"));
    };
    let start: usize = start_str
        .parse()
        .map_err(|e: std::num::ParseIntError| e.to_string())?;
    let end_raw: usize = end_str
        .parse()
        .map_err(|e: std::num::ParseIntError| e.to_string())?;
    let end = if inclusive {
        end_raw
    } else {
        end_raw.checked_sub(1).ok_or("END < START")?
    };
    if end < start {
        return Err("END < START".to_string());
    }
    Ok((start, end))
}

fn main() {
    let cli = Cli::parse();

    if cli.threads > 0 {
        rayon::ThreadPoolBuilder::new()
            .num_threads(cli.threads)
            .build_global()
            .expect("failed to configure rayon thread pool");
    }

    let fac_table = Arc::new(build_fac_table(cli.fac_table_size));
    let program_start = Instant::now();

    if let Some(dir) = cli.checkpoint_dir.as_deref()
        && !dir.exists()
    {
        std::fs::create_dir_all(dir).expect("failed to create checkpoint directory");
    }

    let _ = cli.batch_size; // deprecated

    match cli.command {
        Command::Scan {
            m_range,
            output,
            skip_from,
            signatures_dir,
        } => {
            run_scan(
                m_range.0..=m_range.1,
                cli.max_steps,
                cli.progress_interval,
                cli.checkpoint_dir.clone(),
                cli.checkpoint_interval,
                &output,
                &skip_from,
                &signatures_dir,
                fac_table,
            );
        }
        Command::Revisit { input, output } => {
            run_revisit(
                &input,
                &output,
                cli.max_steps,
                cli.progress_interval,
                cli.checkpoint_dir.clone(),
                cli.checkpoint_interval,
                fac_table,
            );
        }
        Command::DumpSignature { m, output } => {
            run_dump_signature(
                m,
                cli.max_steps,
                cli.progress_interval,
                cli.checkpoint_dir.clone(),
                cli.checkpoint_interval,
                &output,
                fac_table,
            );
        }
        Command::BasinScan {
            m_list,
            trials,
            sigma,
            rng_seed,
            seed_1_csv,
            cap_multiplier,
            cap_floor_c_m_sq,
            resume,
            output,
        } => {
            run_basin_scan(
                &m_list,
                trials,
                sigma,
                rng_seed,
                seed_1_csv.as_deref(),
                cap_multiplier,
                cap_floor_c_m_sq,
                resume,
                cli.max_steps,
                cli.progress_interval,
                &output,
                fac_table,
            );
        }
    }

    println!(
        "Elapsed time: {} seconds",
        program_start.elapsed().as_secs_f64()
    );
}

// CSV header for the new result format. All scalar columns — the full cycle sequence is
// not stored (some m produce periods of 10^7+ terms; see lib.rs::summarize_cycle).
const CSV_HEADER: &str = "m, repeat_after, max_value, most_common_tail_value, cycle_length, cycle_max, cycle_min, distinct_tail_values, steps_to_lock_in";

fn run_scan(
    trials: std::ops::RangeInclusive<usize>,
    max_length: usize,
    progress_interval: usize,
    checkpoint_dir: Option<PathBuf>,
    checkpoint_interval: usize,
    output: &Path,
    skip_from: &[PathBuf],
    signatures_dir: &Path,
    fac_table: Arc<Vec<u16>>,
) {
    // Auto-resume from the existing CSV: any m already present is treated as
    // done. Rows are streamed in completion order during the run (so a kill
    // mid-run loses at most the in-flight trials), then re-sorted by m on
    // clean exit so the final CSV matches the historical sorted layout.
    let existing_rows: Vec<Row> = if output.exists() {
        read_csv(output)
    } else {
        Vec::new()
    };
    let mut already_done: HashSet<usize> = existing_rows.iter().map(|r| r.m).collect();
    let from_output = already_done.len();
    for src in skip_from {
        let before = already_done.len();
        let rows = read_csv(src);
        let total_in_file = rows.len();
        for row in rows {
            already_done.insert(row.m);
        }
        let added = already_done.len() - before;
        println!(
            "skip-from {}: {} new m's added ({} of its {} rows already in the skip set)",
            src.display(),
            added,
            total_in_file - added,
            total_in_file,
        );
    }
    let total_target = trials.end() + 1 - trials.start();
    let work: Vec<usize> = trials
        .clone()
        .filter(|m| !already_done.contains(m))
        .collect();
    let from_skip = already_done.len() - from_output;
    if !already_done.is_empty() {
        println!(
            "Resume: {} m's from {} + {} from --skip-from sources; {} new to run",
            from_output,
            output.display(),
            from_skip,
            work.len(),
        );
    }
    if work.is_empty() {
        println!(
            "All {} requested m's already covered by --output and --skip-from; nothing to do.",
            total_target,
        );
        return;
    }

    let mut file = if existing_rows.is_empty() {
        let mut f = File::create(output).expect("failed to open output CSV");
        writeln!(f, "{}", CSV_HEADER).unwrap();
        f
    } else {
        std::fs::OpenOptions::new()
            .append(true)
            .open(output)
            .expect("failed to open output CSV for append")
    };

    if !signatures_dir.exists() {
        std::fs::create_dir_all(signatures_dir).expect("failed to create signatures directory");
    }

    run_stream(
        work,
        max_length,
        progress_interval,
        checkpoint_dir,
        checkpoint_interval,
        fac_table,
        |m, result| {
            write_result_row(&mut file, m, &result);
            file.flush().unwrap();
            if let Some(sig) = result.signature.as_ref() {
                let sig_path = signatures_dir.join(format!("{}.csv", m));
                let already_present = std::fs::metadata(&sig_path)
                    .map(|md| md.len() > 0)
                    .unwrap_or(false);
                if !already_present {
                    write_signature_csv(&sig_path, sig);
                }
            }
        },
    );
    file.flush().unwrap();
    drop(file);

    // Sort the CSV by m on clean exit. Read everything back, sort, write to a
    // sibling temp file, atomic-rename into place.
    let mut all_rows = read_csv(output);
    all_rows.sort_by_key(|r| r.m);
    let tmp = output.with_extension("csv.sorting");
    write_csv(&tmp, &all_rows, &HashMap::new());
    std::fs::rename(&tmp, output).expect("failed to rename sorted CSV into place");
}

fn run_revisit(
    input: &Path,
    output: &Path,
    max_length: usize,
    progress_interval: usize,
    checkpoint_dir: Option<PathBuf>,
    checkpoint_interval: usize,
    fac_table: Arc<Vec<u16>>,
) {
    let rows = read_csv(input);
    let none_ms: Vec<usize> = rows
        .iter()
        .filter(|row| row.repeat_after.is_none())
        .map(|row| row.m)
        .collect();

    if none_ms.is_empty() {
        println!("No 'None' rows in {}; nothing to revisit.", input.display());
        write_csv(output, &rows, &HashMap::new());
        return;
    }

    println!(
        "Revisiting {} 'None' row(s) from {} with max_steps = {}",
        none_ms.len(),
        input.display(),
        max_length,
    );

    let mut resolved: HashMap<usize, RResult> = HashMap::new();
    run_stream(
        none_ms.clone(),
        max_length,
        progress_interval,
        checkpoint_dir,
        checkpoint_interval,
        fac_table,
        |m, result| {
            resolved.insert(m, result);
        },
    );

    write_csv(output, &rows, &resolved);
}

fn run_dump_signature(
    m: usize,
    max_length: usize,
    progress_interval: usize,
    checkpoint_dir: Option<PathBuf>,
    checkpoint_interval: usize,
    output: &Path,
    fac_table: Arc<Vec<u16>>,
) {
    let result = run_one_trial(
        m,
        max_length,
        progress_interval,
        checkpoint_dir.as_deref(),
        checkpoint_interval,
        fac_table,
    );
    let signature = result.signature.as_ref().unwrap_or_else(|| {
        panic!(
            "dump-signature: no cycle found for m={} within --max-steps={}",
            m, max_length
        )
    });
    write_signature_csv(output, signature);
    println!(
        "dump-signature m={}: wrote {} distinct values to {}",
        m,
        result.distinct_tail_values.unwrap_or(0),
        output.display()
    );
}

// Writes the value→count multiset as `value,count` lines, sorted ascending by value,
// preceded by a `value,count` header. Output is byte-identical regardless of caller
// (scan's inline emission and the standalone `dump-signature` command both go through
// here), so `analysis/build_attractors.py`'s sha256 cluster hashes stay stable.
fn write_signature_csv(path: &Path, signature: &HashMap<u32, u64>) {
    let mut entries: Vec<(u32, u64)> = signature.iter().map(|(v, c)| (*v, *c)).collect();
    entries.sort_unstable_by_key(|(v, _)| *v);

    let mut file = File::create(path).expect("failed to open signature CSV");
    writeln!(file, "value,count").unwrap();
    for (v, c) in entries {
        writeln!(file, "{},{}", v, c).unwrap();
    }
    file.flush().unwrap();
}

// One CSV row in the new format. Fields loaded from an old 3-column CSV keep the new
// fields as None.
#[derive(Default)]
struct Row {
    m: usize,
    repeat_after: Option<usize>,
    max_value: Option<u32>,
    most_common_tail_value: Option<u32>,
    cycle_length: Option<usize>,
    cycle_max: Option<u32>,
    cycle_min: Option<u32>,
    distinct_tail_values: Option<usize>,
    steps_to_lock_in: Option<usize>,
}

impl Row {
    fn from_result(m: usize, r: &RResult) -> Self {
        let repeat_after = r.repeat_after;
        // Preserve the old CSV convention: if the run timed out, max_value is reported
        // as None too (written as "None" in the CSV).
        let max_value = repeat_after.map(|_| r.max_value);
        Row {
            m,
            repeat_after,
            max_value,
            most_common_tail_value: r.most_common_tail_value,
            cycle_length: r.cycle_length,
            cycle_max: r.cycle_max,
            cycle_min: r.cycle_min,
            distinct_tail_values: r.distinct_tail_values,
            steps_to_lock_in: r.steps_to_lock_in,
        }
    }
}

// Parses the input CSV, accepting both the legacy 3-column format
// (`m, repeat_after, max_value`) and the new 8-column format.
fn read_csv(path: &Path) -> Vec<Row> {
    let file = File::open(path).unwrap_or_else(|e| panic!("open {}: {}", path.display(), e));
    let reader = BufReader::new(file);
    let mut rows = Vec::new();
    let mut seen_m: HashSet<usize> = HashSet::new();
    let mut header_cols: Option<usize> = None;

    for (lineno, line) in reader.lines().enumerate() {
        let line = line.expect("read line");
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        // Split on commas or tabs: older `results.csv` rows use tab separators for
        // `m\tNone\tNone` timeout lines while everything else is comma-separated.
        let parts: Vec<&str> = trimmed
            .split(|c| c == ',' || c == '\t')
            .map(str::trim)
            .collect();

        if lineno == 0 && parts.first().map(|p| p.eq_ignore_ascii_case("m")) == Some(true) {
            header_cols = Some(parts.len());
            continue;
        }

        let cols = header_cols.unwrap_or(parts.len());
        if parts.len() != cols {
            panic!(
                "line {}: expected {} columns, got {}: {:?}",
                lineno + 1,
                cols,
                parts.len(),
                line
            );
        }

        let m: usize = parts[0]
            .parse()
            .unwrap_or_else(|_| panic!("bad m on line {}: {:?}", lineno + 1, parts[0]));
        if !seen_m.insert(m) {
            panic!("duplicate m={} in {}", m, path.display());
        }

        let mut row = Row {
            m,
            ..Row::default()
        };
        row.repeat_after = parse_opt(parts[1]);
        row.max_value = parse_opt(parts[2]);
        if cols >= 8 {
            row.most_common_tail_value = parse_opt(parts[3]);
            row.cycle_length = parse_opt(parts[4]);
            row.cycle_max = parse_opt(parts[5]);
            row.cycle_min = parse_opt(parts[6]);
            row.distinct_tail_values = parse_opt(parts[7]);
            if parts.len() >= 9 {
                row.steps_to_lock_in = parse_opt(parts[8]);
            }
        } else if cols != 3 && cols != 8 && cols != 9 {
            panic!(
                "unsupported CSV column count {} in {} (expected 3, 8, or 9)",
                cols,
                path.display()
            );
        }
        rows.push(row);
    }
    rows
}

fn parse_opt<T: std::str::FromStr>(s: &str) -> Option<T> {
    let s = s.trim();
    if s.is_empty() || s.eq_ignore_ascii_case("none") {
        None
    } else {
        Some(
            s.parse()
                .unwrap_or_else(|_| panic!("parse error on {:?}", s)),
        )
    }
}

fn write_csv(
    path: &Path,
    rows: &[Row],
    resolved: &std::collections::HashMap<usize, RResult>,
) {
    let mut file = File::create(path).expect("failed to open output CSV");
    writeln!(file, "{}", CSV_HEADER).unwrap();
    for row in rows {
        match resolved.get(&row.m) {
            Some(r) => write_row(&mut file, &Row::from_result(row.m, r)),
            None => write_row(&mut file, row),
        }
    }
    file.flush().unwrap();
}

fn run_one_trial(
    m: usize,
    max_length: usize,
    progress_interval: usize,
    checkpoint_dir: Option<&Path>,
    checkpoint_interval: usize,
    fac_table: Arc<Vec<u16>>,
) -> RResult {
    let progress_cb = |p: Progress| {
        let phase = match p.phase {
            ProgressPhase::Brent => "brent",
            ProgressPhase::FindMu => "mu   ",
        };
        // `--max-steps` defaults to `usize::MAX` (no cap); show "% of cap"
        // only when the user overrode that, otherwise it's a meaningless 0%.
        if max_length == usize::MAX {
            println!(
                "[m={:>4} {}] step {:>14} (uncapped), max_value={}",
                m, phase, p.step, p.max_value,
            );
        } else {
            let pct = (p.step as f64 / max_length as f64) * 100.0;
            println!(
                "[m={:>4} {}] step {:>14} ({:>5.1}% of cap), max_value={}",
                m, phase, p.step, pct, p.max_value,
            );
        }
    };
    match checkpoint_dir {
        Some(dir) => {
            let path = dir.join(format!("m{}.ckpt", m));
            r_resumable(
                m,
                max_length,
                fac_table,
                progress_interval,
                progress_cb,
                &path,
                checkpoint_interval,
            )
            .unwrap_or_else(|e| panic!("checkpoint error for m={}: {}", m, e))
        }
        None => r_with_progress(m, max_length, fac_table, progress_interval, progress_cb),
    }
}

// Drives a list of trials on rayon and flushes each result through `on_result`
// in *completion order* (not m-order). Callers that want a sorted final CSV
// should sort after the run; the in-order buffer was removed because it could
// hold completed-but-undelivered results in memory for hours when one slow m
// gated many faster peers, so a kill mid-run discarded them along with their
// already-deleted checkpoints.
fn run_stream<F>(
    trials: Vec<usize>,
    max_length: usize,
    progress_interval: usize,
    checkpoint_dir: Option<PathBuf>,
    checkpoint_interval: usize,
    fac_table: Arc<Vec<u16>>,
    mut on_result: F,
) where
    F: FnMut(usize, RResult),
{
    if trials.is_empty() {
        return;
    }

    let total = trials.len();
    let trials_for_worker = trials;
    let stream_start = Instant::now();
    println!("\nStreaming {} trials...", total);

    let (tx, rx) = mpsc::channel::<(usize, RResult, Duration)>();

    // Producer: rayon par_iter sends each result through `tx` as soon as it
    // finishes. The owned `tx` and clones held by `for_each_with` are dropped
    // when the iter completes, which closes the channel and unblocks the
    // consumer below.
    let producer = std::thread::spawn(move || {
        trials_for_worker.into_par_iter().for_each_with(tx, |tx, m| {
            let started = Instant::now();
            let result = run_one_trial(
                m,
                max_length,
                progress_interval,
                checkpoint_dir.as_deref(),
                checkpoint_interval,
                fac_table.clone(),
            );
            let _ = tx.send((m, result, started.elapsed()));
        });
    });

    // Consumer: drain `rx` in completion order and flush each row to
    // `on_result` immediately. No buffering — each completed trial becomes
    // durable as soon as the consumer's CSV write returns.
    while let Ok((m, result, dur)) = rx.recv() {
        if let Some(rep_after) = result.repeat_after {
            println!(
                "R(n,{}): Repeated @ n={}. Max val: {}. Cycle len: {}. ({:.2}s)",
                m,
                rep_after,
                result.max_value,
                result.cycle_length.unwrap_or(0),
                dur.as_secs_f64(),
            );
        } else {
            println!(
                "R(n,{}): no repeat for n<{} ({:.2}s)",
                m,
                max_length,
                dur.as_secs_f64()
            );
        }
        on_result(m, result);
    }

    producer.join().expect("producer thread panicked");
    println!(
        "Streamed {} trials in {:.2}s",
        total,
        stream_start.elapsed().as_secs_f64()
    );
}

fn write_result_row(file: &mut File, m: usize, result: &RResult) {
    let row = Row::from_result(m, result);
    write_row(file, &row);
}

fn write_row(file: &mut File, row: &Row) {
    write!(file, "{}", row.m).unwrap();
    write_opt(file, &row.repeat_after);
    write_opt(file, &row.max_value);
    write_opt(file, &row.most_common_tail_value);
    write_opt(file, &row.cycle_length);
    write_opt(file, &row.cycle_max);
    write_opt(file, &row.cycle_min);
    write_opt(file, &row.distinct_tail_values);
    write_opt(file, &row.steps_to_lock_in);
    writeln!(file).unwrap();
}

fn write_opt<T: std::fmt::Display>(file: &mut File, v: &Option<T>) {
    match v {
        Some(x) => write!(file, ", {}", x).unwrap(),
        None => write!(file, ", None").unwrap(),
    }
}

// ---------------------------------------------------------------------------
// E.6 random-seed basin scan
// ---------------------------------------------------------------------------

const BASIN_CSV_HEADER: &str =
    "m,trial_idx,rng_seed,timed_out,repeat_after,max_value,cycle_length,cycle_min,cycle_max,distinct_tail_values,value_set";

// SplitMix64. Single-u64 state, deterministic. Used for both per-trial seed
// derivation and for drawing the seed window.
#[inline]
fn splitmix64(state: &mut u64) -> u64 {
    *state = state.wrapping_add(0x9e3779b97f4a7c15);
    let mut z = *state;
    z = (z ^ (z >> 30)).wrapping_mul(0xbf58476d1ce4e5b9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94d049bb133111eb);
    z ^ (z >> 31)
}

#[inline]
fn next_uniform(state: &mut u64) -> f64 {
    let bits = splitmix64(state);
    // Top 53 bits → uniform in [0, 1).
    (bits >> 11) as f64 / (1u64 << 53) as f64
}

// Box-Muller; returns one sample. We discard the second value rather than
// caching it — m draws per trial is fast enough that the simpler stateless
// helper isn't worth the bookkeeping.
#[inline]
fn next_lognormal(state: &mut u64, mu: f64, sigma: f64) -> f64 {
    let u1 = next_uniform(state).max(1e-300);
    let u2 = next_uniform(state);
    let z = (-2.0 * u1.ln()).sqrt() * (2.0 * std::f64::consts::PI * u2).cos();
    (mu + sigma * z).exp()
}

fn derive_trial_seed(master: u64, m: usize, trial_idx: usize) -> u64 {
    let mut s = master.wrapping_add((m as u64).wrapping_mul(0x9e3779b97f4a7c15));
    s = s.wrapping_add((trial_idx as u64).wrapping_mul(0xbf58476d1ce4e5b9));
    splitmix64(&mut s)
}

// Draw m iid samples from `round(LogNormal(mu, sigma))`, clamped to [1, ceiling].
// Ceiling = fac_table_len - 1 so seed lookups never overflow the divisor table;
// after the u16-truncation fix, trajectory values are u32 so the only remaining
// upper bound is the precomputed table size.
fn draw_seed_window(rng_state: u64, m: usize, mu: f64, sigma: f64, ceiling: u32) -> Vec<u32> {
    let mut s = rng_state;
    (0..m)
        .map(|_| {
            let v = next_lognormal(&mut s, mu, sigma).round();
            if v < 1.0 {
                1
            } else if v > ceiling as f64 {
                ceiling
            } else {
                v as u32
            }
        })
        .collect()
}

fn parse_m_list(spec: &str) -> Vec<usize> {
    let spec = spec.trim();
    if let Some(idx) = spec.rfind(':') {
        let (range_str, count_str) = (&spec[..idx], &spec[idx + 1..]);
        let count: usize = count_str
            .parse()
            .unwrap_or_else(|_| panic!("bad sample count in m-list spec: {:?}", spec));
        let (start, end) = parse_range(range_str)
            .unwrap_or_else(|e| panic!("bad range in m-list spec {:?}: {}", spec, e));
        if count == 0 {
            return Vec::new();
        }
        if count == 1 {
            return vec![start];
        }
        // Log-stepped: m_i = round(start · (end/start)^(i/(count-1))). Dedup
        // because rounding can collide on small ranges.
        let mut out = Vec::with_capacity(count);
        let log_start = (start as f64).ln();
        let log_end = (end as f64).ln();
        for i in 0..count {
            let t = i as f64 / (count - 1) as f64;
            let v = (log_start + t * (log_end - log_start)).exp().round() as usize;
            let v = v.clamp(start, end);
            if !out.contains(&v) {
                out.push(v);
            }
        }
        out.sort_unstable();
        return out;
    }
    let mut out: Vec<usize> = spec
        .split(',')
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(|s| {
            s.parse::<usize>()
                .unwrap_or_else(|_| panic!("bad m in m-list: {:?}", s))
        })
        .collect();
    out.sort_unstable();
    out.dedup();
    out
}

// Parse a seed=1 results CSV (possibly the legacy 3-column format) into m → repeat_after.
// Rows whose `repeat_after` column is `None` are omitted. Duplicate m's are tolerated
// (last value wins) — the main `read_csv` enforces uniqueness for the scan/revisit
// flows but basin-scan only needs caps, so a stray dup shouldn't abort the run.
fn load_seed_1_caps(path: &Path) -> HashMap<usize, usize> {
    let file = File::open(path).unwrap_or_else(|e| panic!("open {}: {}", path.display(), e));
    let reader = BufReader::new(file);
    let mut out: HashMap<usize, usize> = HashMap::new();
    for (lineno, line) in reader.lines().enumerate() {
        let line = line.expect("read line");
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        let parts: Vec<&str> = trimmed
            .split(|c| c == ',' || c == '\t')
            .map(str::trim)
            .collect();
        if lineno == 0 && parts.first().map(|p| p.eq_ignore_ascii_case("m")) == Some(true) {
            continue;
        }
        if parts.len() < 2 {
            continue;
        }
        let m: usize = match parts[0].parse() {
            Ok(v) => v,
            Err(_) => continue,
        };
        if let Some(rep) = parse_opt::<usize>(parts[1]) {
            out.insert(m, rep);
        }
    }
    out
}

#[allow(clippy::too_many_arguments)]
fn run_basin_scan(
    m_list_spec: &str,
    trials: usize,
    sigma: f64,
    rng_seed: u64,
    seed_1_csv: Option<&Path>,
    cap_multiplier: usize,
    cap_floor_c_m_sq: usize,
    resume: bool,
    global_max_steps: usize,
    progress_interval: usize,
    output: &Path,
    fac_table: Arc<Vec<u16>>,
) {
    let ms = parse_m_list(m_list_spec);
    if ms.is_empty() {
        eprintln!("basin-scan: empty m-list, nothing to do");
        return;
    }

    // Caps removed: the u16-truncation fix means trials no longer need a per-m
    // wall to bound the corrupted-transient regime. `--cap-multiplier`,
    // `--cap-floor-c-m-sq`, `--seed-1-csv`, and the global `--max-steps` are
    // accepted for compatibility but ignored — every trial runs until the
    // bounded-orbit proof fires (cycle detected). Warn loudly if caller
    // overrode any of them so they understand it's a no-op now.
    if seed_1_csv.is_some() || cap_multiplier != 5 || cap_floor_c_m_sq != 100
        || global_max_steps != usize::MAX
    {
        eprintln!(
            "basin-scan: --max-steps / --cap-multiplier / --cap-floor-c-m-sq / --seed-1-csv \
             are no longer honored; trials run uncapped to avoid the partial-trial corruption \
             that the old u16 window produced."
        );
    }
    let _ = (cap_multiplier, cap_floor_c_m_sq, global_max_steps);
    let _ = seed_1_csv.map(load_seed_1_caps);
    // fac_table sized to handle every value the scan might emit; seed draws
    // are clamped to its largest valid index.
    let ceiling: u32 = fac_table.len().saturating_sub(1) as u32;

    // Resume: load already-completed (m, trial_idx) pairs from the existing CSV.
    let already_done: HashSet<(usize, usize)> = if resume && output.exists() {
        load_completed_pairs(output)
    } else {
        HashSet::new()
    };

    // Build the work list, filtered against `already_done`. Every trial uses
    // an unbounded `max_length` (`usize::MAX`) — the bounded-orbit proof
    // guarantees Brent terminates, and a finite cap risks emitting a
    // partial-trial row whose cycle stats reflect the corrupted transient
    // rather than the real attractor.
    let mut work: Vec<(usize, usize, u64, usize)> = Vec::with_capacity(ms.len() * trials);
    let mut skipped = 0usize;
    for &m in &ms {
        for t in 0..trials {
            if already_done.contains(&(m, t)) {
                skipped += 1;
                continue;
            }
            let trial_seed = derive_trial_seed(rng_seed, m, t);
            work.push((m, t, trial_seed, usize::MAX));
        }
    }
    let total = work.len();
    let total_target = ms.len() * trials;

    println!(
        "basin-scan: {} m's × {} trials = {} target ({} skipped from existing CSV, {} new), \
         sigma={}, rng_seed={}, ceiling={}, max_length=unbounded",
        ms.len(),
        trials,
        total_target,
        skipped,
        total,
        sigma,
        rng_seed,
        ceiling,
    );

    if total == 0 {
        println!("basin-scan: nothing to do (all trials already completed in {})", output.display());
        return;
    }

    // Open output for streaming append. Each completed trial flushes its row
    // to disk so a kill mid-run doesn't lose progress.
    let mut file = if !output.exists() || already_done.is_empty() {
        // Fresh run (or `output` exists but had no rows / no header). Truncate
        // and write the header.
        let mut f = File::create(output).expect("failed to open basin-scan output CSV");
        writeln!(f, "{}", BASIN_CSV_HEADER).unwrap();
        f
    } else {
        std::fs::OpenOptions::new()
            .append(true)
            .open(output)
            .expect("failed to open basin-scan output CSV for append")
    };

    let scan_start = Instant::now();
    let (tx, rx) = mpsc::channel::<BasinRow>();

    let sigma_f = sigma;
    let fac_table_for_worker = fac_table.clone();
    let work_for_worker = work;
    let producer = std::thread::spawn(move || {
        work_for_worker
            .into_par_iter()
            .for_each_with(tx, |tx, (m, trial_idx, trial_seed, max_length)| {
                let mu_ln = (m as f64 * (m as f64).ln()).ln();
                let seed_window = draw_seed_window(trial_seed, m, mu_ln, sigma_f, ceiling);
                let started = Instant::now();
                let result = r_seeded_with_progress(
                    m,
                    &seed_window,
                    max_length,
                    fac_table_for_worker.clone(),
                    progress_interval,
                    |_p: Progress| {},
                );
                let elapsed = started.elapsed();
                let row = BasinRow::from_result(m, trial_idx, trial_seed, &result);
                let _ = tx.send(row);
                if trial_idx == 0 {
                    println!(
                        "basin m={:>5} t={:>4}: cycle_min={:?} cycle_max={:?} timed_out={} ({:.2}s)",
                        m,
                        trial_idx,
                        result.cycle_min,
                        result.cycle_max,
                        result.repeat_after.is_none(),
                        elapsed.as_secs_f64(),
                    );
                }
            });
    });

    let mut completed = 0usize;
    let mut timeouts = 0usize;
    let mut last_print = Instant::now();
    while let Ok(row) = rx.recv() {
        if row.timed_out {
            timeouts += 1;
        }
        // Stream write + flush per row. fsync isn't strictly needed — a kill
        // before the OS flushes the page cache loses at most a handful of
        // rows, and `--resume` re-runs them deterministically.
        row.write(&mut file);
        let _ = file.flush();
        completed += 1;
        if last_print.elapsed() > Duration::from_secs(15) {
            println!(
                "basin-scan progress: {}/{} ({:.1}%, {:.1}s elapsed, {} timeouts)",
                completed,
                total,
                100.0 * completed as f64 / total as f64,
                scan_start.elapsed().as_secs_f64(),
                timeouts,
            );
            last_print = Instant::now();
        }
    }
    producer.join().expect("basin-scan producer panicked");

    println!(
        "basin-scan: wrote {} rows ({} timeouts) to {} in {:.2}s (rows in completion order; \
         post-processor sorts by (m, trial_idx))",
        completed,
        timeouts,
        output.display(),
        scan_start.elapsed().as_secs_f64(),
    );
}

// Parse an existing basin-scan CSV and collect the (m, trial_idx) pairs of
// rows that successfully decoded both columns. Used by `--resume`. A truncated
// last row (e.g. from a kill mid-write) is silently dropped so the next run
// will redo just that one trial.
fn load_completed_pairs(path: &Path) -> HashSet<(usize, usize)> {
    let file = File::open(path).expect("failed to open existing basin-scan CSV");
    let reader = BufReader::new(file);
    let mut out: HashSet<(usize, usize)> = HashSet::new();
    for (lineno, line) in reader.lines().enumerate() {
        let line = match line {
            Ok(l) => l,
            Err(_) => break,
        };
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        if lineno == 0 && trimmed.starts_with("m,") {
            continue;
        }
        let mut parts = trimmed.split(',');
        let m: usize = match parts.next().and_then(|s| s.trim().parse().ok()) {
            Some(v) => v,
            None => continue,
        };
        let t: usize = match parts.next().and_then(|s| s.trim().parse().ok()) {
            Some(v) => v,
            None => continue,
        };
        out.insert((m, t));
    }
    out
}

struct BasinRow {
    m: usize,
    trial_idx: usize,
    rng_seed: u64,
    timed_out: bool,
    repeat_after: Option<usize>,
    max_value: u32,
    cycle_length: Option<usize>,
    cycle_min: Option<u32>,
    cycle_max: Option<u32>,
    distinct_tail_values: Option<usize>,
    // Sorted-ascending distinct values from the cycle (the value set, not the
    // multiset). Empty on timeout. Stored joined `;` so a single CSV column
    // round-trips losslessly.
    value_set: Vec<u32>,
}

impl BasinRow {
    fn from_result(m: usize, trial_idx: usize, rng_seed: u64, r: &RResult) -> Self {
        let timed_out = r.repeat_after.is_none();
        let mut value_set: Vec<u32> = r
            .signature
            .as_ref()
            .map(|sig| sig.keys().copied().collect())
            .unwrap_or_default();
        value_set.sort_unstable();
        Self {
            m,
            trial_idx,
            rng_seed,
            timed_out,
            repeat_after: r.repeat_after,
            max_value: r.max_value,
            cycle_length: r.cycle_length,
            cycle_min: r.cycle_min,
            cycle_max: r.cycle_max,
            distinct_tail_values: r.distinct_tail_values,
            value_set,
        }
    }

    fn write(&self, file: &mut File) {
        write!(
            file,
            "{},{},{},{}",
            self.m,
            self.trial_idx,
            self.rng_seed,
            if self.timed_out { 1 } else { 0 },
        )
        .unwrap();
        write_basin_opt(file, &self.repeat_after);
        write!(file, ",{}", self.max_value).unwrap();
        write_basin_opt(file, &self.cycle_length);
        write_basin_opt(file, &self.cycle_min);
        write_basin_opt(file, &self.cycle_max);
        write_basin_opt(file, &self.distinct_tail_values);
        write!(file, ",").unwrap();
        for (i, v) in self.value_set.iter().enumerate() {
            if i > 0 {
                write!(file, ";").unwrap();
            }
            write!(file, "{}", v).unwrap();
        }
        writeln!(file).unwrap();
    }
}

fn write_basin_opt<T: std::fmt::Display>(file: &mut File, v: &Option<T>) {
    match v {
        Some(x) => write!(file, ",{}", x).unwrap(),
        None => write!(file, ",").unwrap(),
    }
}

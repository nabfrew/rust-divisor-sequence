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
    Progress, ProgressPhase, RResult, build_fac_table, r_resumable, r_with_progress,
};

/// Explore the divisor-sum sequence R(n, m) over ranges of m.
#[derive(Parser, Debug)]
#[command(version, about)]
struct Cli {
    /// Maximum sequence length to search before giving up.
    #[arg(long, default_value_t = 10_000_000_000, global = true)]
    max_steps: usize,

    /// Number of rayon worker threads. 0 uses rayon's default (≈ logical CPUs).
    #[arg(long, default_value_t = 0, global = true)]
    threads: usize,

    /// Size of the precomputed divisor-count table (τ(0..N)).
    /// Must exceed the largest term the run will emit; r() panics with a clear
    /// message on overflow.
    #[arg(long, default_value_t = 1usize << 18, global = true)]
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
        Command::Scan { m_range, output } => {
            run_scan(
                m_range.0..=m_range.1,
                cli.max_steps,
                cli.progress_interval,
                cli.checkpoint_dir.clone(),
                cli.checkpoint_interval,
                &output,
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
    }

    println!(
        "Elapsed time: {} seconds",
        program_start.elapsed().as_secs_f64()
    );
}

// CSV header for the new result format. All scalar columns — the full cycle sequence is
// not stored (some m produce periods of 10^7+ terms; see lib.rs::summarize_cycle).
const CSV_HEADER: &str = "m, repeat_after, max_value, most_common_tail_value, cycle_length, cycle_max, cycle_min, distinct_tail_values";

fn run_scan(
    trials: std::ops::RangeInclusive<usize>,
    max_length: usize,
    progress_interval: usize,
    checkpoint_dir: Option<PathBuf>,
    checkpoint_interval: usize,
    output: &Path,
    fac_table: Arc<Vec<u8>>,
) {
    let mut file = File::create(output).expect("failed to open output CSV");
    writeln!(file, "{}", CSV_HEADER).unwrap();

    run_stream(
        trials.clone().collect(),
        max_length,
        progress_interval,
        checkpoint_dir,
        checkpoint_interval,
        fac_table,
        |m, result| {
            write_result_row(&mut file, m, &result);
            file.flush().unwrap();
        },
    );
    file.flush().unwrap();
}

fn run_revisit(
    input: &Path,
    output: &Path,
    max_length: usize,
    progress_interval: usize,
    checkpoint_dir: Option<PathBuf>,
    checkpoint_interval: usize,
    fac_table: Arc<Vec<u8>>,
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
    fac_table: Arc<Vec<u8>>,
) {
    let result = run_one_trial(
        m,
        max_length,
        progress_interval,
        checkpoint_dir.as_deref(),
        checkpoint_interval,
        fac_table,
    );
    let signature = result.signature.unwrap_or_else(|| {
        panic!(
            "dump-signature: no cycle found for m={} within --max-steps={}",
            m, max_length
        )
    });
    let mut entries: Vec<(u16, u64)> = signature.into_iter().collect();
    entries.sort_unstable_by_key(|(v, _)| *v);

    let mut file = File::create(output).expect("failed to open output CSV");
    writeln!(file, "value,count").unwrap();
    for (v, c) in entries {
        writeln!(file, "{},{}", v, c).unwrap();
    }
    file.flush().unwrap();
    println!(
        "dump-signature m={}: wrote {} distinct values to {}",
        m,
        result.distinct_tail_values.unwrap_or(0),
        output.display()
    );
}

// One CSV row in the new format. Fields loaded from an old 3-column CSV keep the new
// fields as None.
#[derive(Default)]
struct Row {
    m: usize,
    repeat_after: Option<usize>,
    max_value: Option<u16>,
    most_common_tail_value: Option<u16>,
    cycle_length: Option<usize>,
    cycle_max: Option<u16>,
    cycle_min: Option<u16>,
    distinct_tail_values: Option<usize>,
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
        } else if cols != 3 {
            panic!(
                "unsupported CSV column count {} in {} (expected 3 or 8)",
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
    fac_table: Arc<Vec<u8>>,
) -> RResult {
    let progress_cb = |p: Progress| {
        let phase = match p.phase {
            ProgressPhase::Brent => "brent",
            ProgressPhase::FindMu => "mu   ",
        };
        let pct = (p.step as f64 / max_length as f64) * 100.0;
        println!(
            "[m={:>4} {}] step {:>14} ({:>5.1}% of cap), max_value={}",
            m, phase, p.step, pct, p.max_value,
        );
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

// Streams trials through rayon's work-stealing scheduler, sending each completed
// (m, result) on a channel. The consumer holds completed-but-not-yet-flushable
// results in a `HashMap` and emits them to `on_result` strictly in m-order so the
// output CSV stays sorted. Per-trial completion lines print in completion order
// (not m-order) so live progress reflects which workers actually finished.
fn run_stream<F>(
    trials: Vec<usize>,
    max_length: usize,
    progress_interval: usize,
    checkpoint_dir: Option<PathBuf>,
    checkpoint_interval: usize,
    fac_table: Arc<Vec<u8>>,
    mut on_result: F,
) where
    F: FnMut(usize, RResult),
{
    if trials.is_empty() {
        return;
    }

    let total = trials.len();
    let trials_for_worker = trials.clone();
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

    // Consumer: drain `rx` in completion order; flush to `on_result` strictly
    // in m-order using the input `trials` vector as the expected sequence.
    let mut pending: HashMap<usize, RResult> = HashMap::new();
    let mut next_idx = 0usize;
    while next_idx < total {
        let next_m = trials[next_idx];
        if let Some(r) = pending.remove(&next_m) {
            on_result(next_m, r);
            next_idx += 1;
            continue;
        }
        match rx.recv() {
            Ok((m, result, dur)) => {
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
                pending.insert(m, result);
            }
            Err(_) => break,
        }
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
    writeln!(file).unwrap();
}

fn write_opt<T: std::fmt::Display>(file: &mut File, v: &Option<T>) {
    match v {
        Some(x) => write!(file, ", {}", x).unwrap(),
        None => write!(file, ", None").unwrap(),
    }
}

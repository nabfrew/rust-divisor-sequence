use std::{
    cmp::min,
    collections::HashSet,
    fs::File,
    io::{BufRead, BufReader, Write},
    path::{Path, PathBuf},
    sync::Arc,
    time::Instant,
};

use clap::{Parser, Subcommand};
use rayon::prelude::{IntoParallelIterator, ParallelIterator};

use divisor_series::{RResult, build_fac_table, r};

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

    /// Parallel batch size. Larger than the CPU count gives better load
    /// balancing; smaller reduces peak memory at large m.
    #[arg(long, default_value_t = 8, global = true)]
    batch_size: usize,

    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand, Debug)]
enum Command {
    /// Scan a range of m and write a CSV of (m, repeat_after, max_value).
    Scan {
        /// Range of m, inclusive on both ends, e.g. `1..=2000` or `1..2001`.
        #[arg(long, value_parser = parse_range, default_value = "1..=2000")]
        m_range: (usize, usize),

        /// Output CSV path.
        #[arg(long, default_value = "results.csv")]
        output: PathBuf,
    },
    /// Re-run rows whose repeat_after is 'None' with the current --max-steps
    /// and write a refreshed CSV.
    Revisit {
        /// Existing CSV produced by a previous run.
        #[arg(long)]
        input: PathBuf,

        /// Output CSV path. May equal --input to overwrite in place.
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

    match cli.command {
        Command::Scan { m_range, output } => {
            run_scan(
                m_range.0..=m_range.1,
                cli.max_steps,
                cli.batch_size,
                &output,
                fac_table,
            );
        }
        Command::Revisit { input, output } => {
            run_revisit(
                &input,
                &output,
                cli.max_steps,
                cli.batch_size,
                fac_table,
            );
        }
    }

    println!(
        "Elapsed time: {} seconds",
        program_start.elapsed().as_secs_f64()
    );
}

fn run_scan(
    trials: std::ops::RangeInclusive<usize>,
    max_length: usize,
    batch_size: usize,
    output: &Path,
    fac_table: Arc<Vec<u8>>,
) {
    let mut file = File::create(output).expect("failed to open output CSV");
    writeln!(file, "m, repeat_after, max_value").unwrap();

    run_batches(
        trials.clone().collect(),
        max_length,
        batch_size,
        fac_table,
        |m, result| write_row(&mut file, m, result),
    );
    file.flush().unwrap();
}

fn run_revisit(
    input: &Path,
    output: &Path,
    max_length: usize,
    batch_size: usize,
    fac_table: Arc<Vec<u8>>,
) {
    let rows = read_csv(input);
    let none_ms: Vec<usize> = rows
        .iter()
        .filter_map(|row| match row {
            Row::None { m } => Some(*m),
            Row::Done { .. } => None,
        })
        .collect();

    if none_ms.is_empty() {
        println!("No 'None' rows in {}; nothing to revisit.", input.display());
        // Still produce an output CSV so downstream tooling has a predictable file.
        write_csv(output, &rows, &Default::default());
        return;
    }

    println!(
        "Revisiting {} 'None' row(s) from {} with max_steps = {}",
        none_ms.len(),
        input.display(),
        max_length,
    );

    let mut resolved: std::collections::HashMap<usize, RResult> =
        std::collections::HashMap::new();
    run_batches(
        none_ms.clone(),
        max_length,
        batch_size,
        fac_table,
        |m, result| {
            resolved.insert(m, result);
        },
    );

    write_csv(output, &rows, &resolved);
}

enum Row {
    Done {
        m: usize,
        repeat_after: usize,
        max_value: u16,
    },
    None {
        m: usize,
    },
}

fn read_csv(path: &Path) -> Vec<Row> {
    let file = File::open(path).unwrap_or_else(|e| panic!("open {}: {}", path.display(), e));
    let reader = BufReader::new(file);
    let mut rows = Vec::new();
    let mut seen_m: HashSet<usize> = HashSet::new();
    for (lineno, line) in reader.lines().enumerate() {
        let line = line.expect("read line");
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        if lineno == 0 && trimmed.starts_with("m") {
            continue;
        }
        let parts: Vec<&str> = trimmed.split(',').map(str::trim).collect();
        if parts.len() != 3 {
            panic!("malformed row {}: {:?}", lineno + 1, line);
        }
        let m: usize = parts[0]
            .parse()
            .unwrap_or_else(|_| panic!("bad m on line {}: {:?}", lineno + 1, parts[0]));
        if !seen_m.insert(m) {
            panic!("duplicate m={} in {}", m, path.display());
        }
        let row = if parts[1].eq_ignore_ascii_case("None") || parts[2].eq_ignore_ascii_case("None")
        {
            Row::None { m }
        } else {
            let repeat_after: usize = parts[1].parse().unwrap_or_else(|_| {
                panic!("bad repeat_after on line {}: {:?}", lineno + 1, parts[1])
            });
            let max_value: u16 = parts[2].parse().unwrap_or_else(|_| {
                panic!("bad max_value on line {}: {:?}", lineno + 1, parts[2])
            });
            Row::Done {
                m,
                repeat_after,
                max_value,
            }
        };
        rows.push(row);
    }
    rows
}

fn write_csv(
    path: &Path,
    rows: &[Row],
    resolved: &std::collections::HashMap<usize, RResult>,
) {
    let mut file = File::create(path).expect("failed to open output CSV");
    writeln!(file, "m, repeat_after, max_value").unwrap();
    for row in rows {
        match row {
            Row::Done {
                m,
                repeat_after,
                max_value,
            } => {
                writeln!(file, "{}, {}, {}", m, repeat_after, max_value).unwrap();
            }
            Row::None { m } => match resolved.get(m) {
                Some(RResult {
                    repeat_after: Some(rep_after),
                    max_value,
                }) => {
                    writeln!(file, "{}, {}, {}", m, rep_after, max_value).unwrap();
                }
                _ => {
                    writeln!(file, "{}, None, None", m).unwrap();
                }
            },
        }
    }
    file.flush().unwrap();
}

fn run_batches<F>(
    trials: Vec<usize>,
    max_length: usize,
    batch_size: usize,
    fac_table: Arc<Vec<u8>>,
    mut on_result: F,
) where
    F: FnMut(usize, RResult),
{
    assert!(batch_size >= 1, "--batch-size must be >= 1");
    let mut start = 0;
    while start < trials.len() {
        let end = min(start + batch_size, trials.len());
        let batch = &trials[start..end];
        start = end;

        let first = batch.first().copied().unwrap_or(0);
        let last = batch.last().copied().unwrap_or(0);
        println!("\nStarting batch: {}..={}", first, last);
        let batch_start = Instant::now();
        let results: Vec<(usize, RResult)> = batch
            .to_vec()
            .into_par_iter()
            .map(|m| (m, r(m, max_length, fac_table.clone())))
            .collect();
        for (m, result) in results {
            if let Some(rep_after) = result.repeat_after {
                println!(
                    "R(n,{}): Repeated @ n={}. Max val: {}.",
                    m, rep_after, result.max_value
                );
            } else {
                println!("R(n,{})", m);
                println!("!!!!  No repeat for n<{}", max_length);
            }
            on_result(m, result);
        }
        println!(
            "Batch finished in {} seconds",
            batch_start.elapsed().as_secs_f64()
        );
    }
}

fn write_row(file: &mut File, m: usize, result: RResult) {
    if let Some(rep_after) = result.repeat_after {
        writeln!(file, "{}, {}, {}", m, rep_after, result.max_value).unwrap();
    } else {
        writeln!(file, "{}, None, None", m).unwrap();
    }
    file.flush().unwrap();
}

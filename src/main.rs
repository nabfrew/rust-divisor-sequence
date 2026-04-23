use std::{cmp::min, fs::File, io::Write, sync::Arc, time::Instant};

use rayon::prelude::{IntoParallelIterator, ParallelIterator};

use divisor_series::{RResult, build_fac_table, r};

fn main() {
    // Set the maximum sequence length before giving up.
    // WARNING: 100,000,000 will take a long time (half an hour or more, depending on your computer)
    let max_length = 1_000_000_000;
    // Range of values to test
    let trials = 1..=2000;

    // Process in batches this large, for the sake of parallelism.
    // Choose a number larger than your number of CPU cores for best performance.
    // However, for large values of m, you may need to decrease it depending on available memory.
    let batch_size = 8;

    let mut file = File::create("results_500.csv").unwrap();
    let mut w = Vec::new();
    write!(w, "m, repeat_after, max_value\n").unwrap();
    file.write(&w).unwrap();

    let program_start = Instant::now();

    // Sized for div_sum up to 2^18 = 262144. max_value/m ≲ 14 in observed data (m=577:
    // 7808/577 ≈ 13.5), so this clears m ≤ ~18_000 with a wide safety margin; r() panics
    // with a clear message if a future run outgrows it.
    let fac_table = Arc::new(build_fac_table(1 << 18));

    let mut start_val = *trials.start();
    while start_val <= *trials.end() {
        let batch = start_val..min(start_val + batch_size, *trials.end() + 1);
        start_val += batch_size;
        println!("\nStarting batch: {:?}", batch);

        let batch_start = Instant::now();
        let results: Vec<(usize, RResult)> = batch
            .into_par_iter()
            .map(|m| (m, r(m, max_length, fac_table.clone())))
            .collect();
        for (m, result) in &results {
            let mut w = Vec::new();
            if let Some(rep_after) = result.repeat_after {
                println!(
                    "R(n,{}): Repeated @ n={}. Max val: {}.",
                    m, rep_after, result.max_value
                );

                write!(w, "{}, {}, {}\n", m, rep_after, result.max_value).unwrap();
            } else {
                println!("R(n,{})", m);
                println!("!!!!  No repeat for n<{}", max_length);
                write!(w, "{}, None, None\n", m).unwrap();
            }
            file.write(&w).unwrap();
        }
        let elapsed_time = batch_start.elapsed();
        println!("Batch finished in {} seconds", elapsed_time.as_secs_f64());
        file.flush().unwrap();
    }

    let elapsed_time = program_start.elapsed();
    println!("Elapsed time: {} seconds", elapsed_time.as_secs_f64());
}

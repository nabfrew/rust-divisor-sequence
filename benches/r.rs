use std::sync::Arc;

use criterion::{BenchmarkId, Criterion, criterion_group, criterion_main};

use divisor_series::{build_fac_table, r};

fn bench_r(c: &mut Criterion) {
    let fac_table: Arc<Vec<u16>> = Arc::new(build_fac_table(1 << 18));
    let mut group = c.benchmark_group("r");
    group.sample_size(10);

    // max_length chosen so each m resolves (reaches a cycle) rather than timing out.
    // Observed repeat_after from results_new*.csv: m=16→481, 64→10k, 256→463k,
    // 512→909k, 700→277M. 500M cap handles them all.
    for &m in &[16usize, 64, 256, 512, 700] {
        group.bench_with_input(BenchmarkId::from_parameter(m), &m, |b, &m| {
            b.iter(|| r(m, 500_000_000, fac_table.clone()));
        });
    }

    group.finish();
}

criterion_group!(benches, bench_r);
criterion_main!(benches);

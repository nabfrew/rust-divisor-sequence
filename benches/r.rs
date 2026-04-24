use std::sync::Arc;

use criterion::{BenchmarkId, Criterion, criterion_group, criterion_main};

use divisor_series::{build_fac_table, r};

fn bench_r(c: &mut Criterion) {
    let fac_table: Arc<Vec<u8>> = Arc::new(build_fac_table(1 << 18));
    let mut group = c.benchmark_group("r");
    group.sample_size(10);

    for &m in &[16usize, 64, 256] {
        group.bench_with_input(BenchmarkId::from_parameter(m), &m, |b, &m| {
            b.iter(|| r(m, 10_000_000, fac_table.clone()));
        });
    }

    group.finish();
}

criterion_group!(benches, bench_r);
criterion_main!(benches);

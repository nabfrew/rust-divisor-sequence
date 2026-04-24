use std::sync::Arc;

use divisor_series::{RResult, build_fac_table, r};

// Naive stored-sequence reference for the divisor-sum sliding-window system.
//
// Generates the sequence term-by-term, storing every value, and searches for the first
// window repetition by scanning all earlier windows. O(L^2 · m) in the sequence length L;
// only used as a correctness oracle in tests.
//
// Returns (repeat_after, max_value, cycle_length, seq) where `repeat_after` matches the
// convention used by `r()`: the total sequence length at which the trailing m-window
// coincides with an earlier m-window (i.e. mu + lam + m).
fn reference(
    m: usize,
    max_length: usize,
    fac_table: &[u8],
) -> (Option<usize>, u16, Option<usize>, Vec<u16>) {
    assert!(m >= 1);
    let mut seq: Vec<u16> = vec![1u16; m];
    let mut max_value: u16 = 1;
    let mut sum: usize = m;

    loop {
        if seq.len() >= max_length {
            return (None, max_value, None, seq);
        }

        let next_val: u16 = sum.try_into().expect("reference: next_val overflows u16");
        let new_d = fac_table[sum] as usize;
        let oldest = seq[seq.len() - m];
        let oldest_d = fac_table[oldest as usize] as usize;
        sum = sum + new_d - oldest_d;
        seq.push(next_val);
        if next_val > max_value {
            max_value = next_val;
        }

        let k = seq.len() - m;
        for j in 0..k {
            if seq[j..j + m] == seq[k..k + m] {
                return (Some(seq.len()), max_value, Some(k - j), seq);
            }
        }
    }
}

// Independent naive generator of the first `len` terms of the sequence. Does not stop at
// cycle detection, so it can produce more terms than `reference()` returns once a cycle is
// hit. Used to compare the first 1000 terms.
fn generate_n(m: usize, len: usize, fac_table: &[u8]) -> Vec<u16> {
    assert!(m >= 1);
    let mut seq: Vec<u16> = vec![1u16; m];
    if len <= m {
        seq.truncate(len);
        return seq;
    }
    let mut sum: usize = m;
    while seq.len() < len {
        let next_val: u16 = sum.try_into().expect("generate_n: next_val overflows u16");
        let new_d = fac_table[sum] as usize;
        let oldest = seq[seq.len() - m];
        let oldest_d = fac_table[oldest as usize] as usize;
        sum = sum + new_d - oldest_d;
        seq.push(next_val);
    }
    seq
}

#[test]
fn brent_matches_reference_small_m() {
    let fac_table_vec = build_fac_table(1 << 16);
    let fac_table: Arc<Vec<u8>> = Arc::new(fac_table_vec.clone());
    let max_length = 100_000usize;

    for &m in &[1usize, 2, 3, 5, 8] {
        let (ref_repeat, ref_max, ref_cycle, ref_seq) = reference(m, max_length, &fac_table_vec);
        let RResult {
            repeat_after,
            max_value,
        } = r(m, max_length, fac_table.clone());

        assert_eq!(
            repeat_after, ref_repeat,
            "repeat_after mismatch for m={}",
            m
        );
        assert_eq!(max_value, ref_max, "max_value mismatch for m={}", m);
        let cycle = ref_cycle.expect("reference must resolve a cycle for small m");
        assert!(cycle >= 1, "cycle length must be positive for m={}", m);
        assert!(
            cycle + m <= ref_repeat.unwrap(),
            "cycle + m must fit within repeat_after for m={}",
            m,
        );

        // Cross-check the first 1000 terms: the reference generator and an independent
        // naive generator must agree up to the length the reference actually produced.
        let cmp_len = std::cmp::min(1000, ref_seq.len());
        let independent = generate_n(m, cmp_len, &fac_table_vec);
        assert_eq!(
            &ref_seq[..cmp_len],
            &independent[..cmp_len],
            "first {} terms disagree for m={}",
            cmp_len,
            m,
        );
    }
}

#[test]
fn crosscheck_results_csv_small_m() {
    // Rows copied verbatim from the top of results.csv; must continue to match bit-exactly.
    let expected: &[(usize, usize, u16)] = &[
        (1, 2, 1),
        (2, 9, 5),
        (3, 24, 14),
        (4, 23, 19),
        (5, 35, 19),
        (6, 32, 34),
        (7, 75, 43),
        (8, 114, 43),
        (9, 81, 43),
        (10, 241, 82),
        (11, 95, 69),
        (12, 298, 94),
        (13, 200, 118),
        (14, 759, 118),
    ];

    let fac_table: Arc<Vec<u8>> = Arc::new(build_fac_table(1 << 16));
    for &(m, expected_repeat, expected_max) in expected {
        let RResult {
            repeat_after,
            max_value,
        } = r(m, 100_000, fac_table.clone());
        assert_eq!(
            repeat_after,
            Some(expected_repeat),
            "repeat_after mismatch vs results.csv for m={}",
            m,
        );
        assert_eq!(
            max_value, expected_max,
            "max_value mismatch vs results.csv for m={}",
            m,
        );
    }
}

#[test]
fn max_length_none_returns_partial_max() {
    // When max_length is reached before cycle detection, r() and the reference should
    // agree that no repeat was found, and both should report the same max_value seen so far.
    let m = 8usize;
    let (results_repeat, _, _, _) = reference(m, 50, &build_fac_table(1 << 14));
    let fac_table: Arc<Vec<u8>> = Arc::new(build_fac_table(1 << 14));
    let res = r(m, 50, fac_table);
    assert_eq!(res.repeat_after, results_repeat);
    assert!(res.repeat_after.is_none());
    assert!(res.max_value >= 1);
}

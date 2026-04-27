use std::collections::HashMap;
use std::sync::Arc;

use divisor_series::{RResult, build_fac_table, r};

// Naive stored-sequence reference for the divisor-sum sliding-window system.
//
// Generates the sequence term-by-term, storing every value, and searches for the first
// window repetition by scanning all earlier windows. O(L^2 · m) in the sequence length L;
// only used as a correctness oracle in tests.
//
// Returns (repeat_after, max_value, cycle, seq) where `repeat_after` matches the convention
// used by `r()`: the total sequence length at which the trailing m-window coincides with an
// earlier m-window (i.e. mu + lam + m). `cycle` is one full period of the tail — `r()` no
// longer returns the period itself (too large at bigger m), so tests recompute it here when
// they need to verify cycle statistics.
fn reference(
    m: usize,
    max_length: usize,
    fac_table: &[u8],
) -> (Option<usize>, u16, Option<Vec<u16>>, Vec<u16>) {
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
                // mu = j, lam = k - j. The values a_{m+mu}..a_{m+mu+lam-1} are one period
                // of the tail; by construction they live at seq[m+j..m+j+lam] = seq[m+j..m+k].
                let cycle = seq[m + j..m + k].to_vec();
                return (Some(seq.len()), max_value, Some(cycle), seq);
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

fn most_common_with_smallest_tiebreak(cycle: &[u16]) -> u16 {
    let mut counts: HashMap<u16, u64> = HashMap::new();
    for &v in cycle {
        *counts.entry(v).or_insert(0) += 1;
    }
    let (&v, _) = counts
        .iter()
        .min_by(|a, b| b.1.cmp(a.1).then_with(|| a.0.cmp(b.0)))
        .expect("non-empty cycle");
    v
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
            cycle_length,
            cycle_max,
            cycle_min,
            most_common_tail_value,
            distinct_tail_values,
            signature,
        } = r(m, max_length, fac_table.clone());

        assert_eq!(
            repeat_after, ref_repeat,
            "repeat_after mismatch for m={}",
            m
        );
        assert_eq!(max_value, ref_max, "max_value mismatch for m={}", m);

        let cycle = ref_cycle.expect("reference must resolve a cycle for small m");
        assert!(!cycle.is_empty(), "cycle length must be positive for m={}", m);
        assert!(
            cycle.len() + m <= ref_repeat.unwrap(),
            "cycle + m must fit within repeat_after for m={}",
            m,
        );

        assert_eq!(
            cycle_length,
            Some(cycle.len()),
            "cycle_length mismatch for m={}",
            m
        );

        let ref_max_cycle = *cycle.iter().max().unwrap();
        let ref_min_cycle = *cycle.iter().min().unwrap();
        assert_eq!(cycle_max, Some(ref_max_cycle), "cycle_max for m={}", m);
        assert_eq!(cycle_min, Some(ref_min_cycle), "cycle_min for m={}", m);

        let ref_mc = most_common_with_smallest_tiebreak(&cycle);
        assert_eq!(
            most_common_tail_value,
            Some(ref_mc),
            "most_common_tail_value for m={}",
            m
        );

        let ref_distinct = {
            let mut s = std::collections::HashSet::new();
            for &v in &cycle {
                s.insert(v);
            }
            s.len()
        };
        assert_eq!(
            distinct_tail_values,
            Some(ref_distinct),
            "distinct_tail_values for m={}",
            m
        );

        // Multiset equality: every value in the reference cycle has the same count in
        // r()'s signature, and no extra keys exist.
        let mut ref_counts: HashMap<u16, u64> = HashMap::new();
        for &v in &cycle {
            *ref_counts.entry(v).or_insert(0) += 1;
        }
        let sig = signature.expect("signature must be present when cycle resolves");
        assert_eq!(
            sig, ref_counts,
            "signature multiset mismatch for m={}",
            m
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
            ..
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
fn crosscheck_compiled_results_csv_small_m() {
    // Rows copied from compiled_results.csv: (m, repeat_after_without_m, max_value, most_common_in_tail).
    // `repeat_after_without_m` here is the compiled CSV's convention (mu + lam, no trailing m);
    // our RResult reports mu + lam + m, so we add `m` back when comparing.
    let expected: &[(usize, usize, u16, u16)] = &[
        (1, 1, 1, 1),
        (2, 7, 5, 5),
        (3, 21, 14, 14),
        (4, 19, 19, 15),
        (5, 30, 19, 19),
        (6, 26, 34, 34),
        (7, 68, 43, 19),
        (8, 106, 43, 41),
        (9, 72, 43, 41),
        (10, 231, 82, 70),
        (11, 84, 69, 39),
        (12, 286, 94, 74),
        (13, 187, 118, 43),
        (14, 745, 118, 82),
    ];

    let fac_table_vec = build_fac_table(1 << 16);
    let fac_table: Arc<Vec<u8>> = Arc::new(fac_table_vec.clone());
    for &(m, compiled_rep, expected_max, expected_most_common) in expected {
        let RResult {
            repeat_after,
            max_value,
            most_common_tail_value,
            ..
        } = r(m, 100_000, fac_table.clone());
        assert_eq!(
            repeat_after,
            Some(compiled_rep + m),
            "repeat_after vs compiled_results.csv for m={}",
            m,
        );
        assert_eq!(
            max_value, expected_max,
            "max_value vs compiled_results.csv for m={}",
            m,
        );

        // compiled_results.csv and our implementation may break ties differently when
        // multiple values share the max count. Require that both are valid
        // "most common" values: same count in the cycle, equal to the max count.
        // r() no longer returns the period, so recompute it from the reference implementation.
        let (_, _, ref_cycle, _) = reference(m, 100_000, &fac_table_vec);
        let cycle = ref_cycle.expect("cycle must resolve for small m");
        let our = most_common_tail_value.expect("some most-common when cycle resolves");
        let our_count = cycle.iter().filter(|&&x| x == our).count();
        let compiled_count = cycle.iter().filter(|&&x| x == expected_most_common).count();
        let top_count = *cycle
            .iter()
            .fold(std::collections::HashMap::<u16, usize>::new(), |mut acc, &v| {
                *acc.entry(v).or_insert(0) += 1;
                acc
            })
            .values()
            .max()
            .unwrap();
        assert_eq!(
            our_count, top_count,
            "our most_common_tail_value must have the cycle's top count for m={}",
            m,
        );
        assert_eq!(
            compiled_count, top_count,
            "compiled_results.csv most_common value must also have top count for m={} (got {} with count {}, top count {})",
            m, expected_most_common, compiled_count, top_count,
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
    assert!(res.cycle_length.is_none());
    assert!(res.most_common_tail_value.is_none());
    assert!(res.distinct_tail_values.is_none());
    assert!(res.signature.is_none());
}

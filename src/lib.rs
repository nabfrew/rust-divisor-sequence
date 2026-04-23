use std::sync::Arc;

use galil_seiferas::gs_find;
use primefactor::PrimeFactors;

pub struct RResult<T> {
    pub sequence: Vec<T>,
    pub repeated: Option<Vec<T>>,
    pub repeated_at: Option<usize>,
}

pub fn repeats_m<T>(seq: &[T], m: usize) -> Option<usize>
where
    T: Eq,
{
    if seq.len() < 1 {
        return None;
    }
    let subseq = &seq[seq.len() - m..seq.len()];
    let remaining_seq = &seq[0..seq.len() - 1];

    gs_find(remaining_seq, subseq)
}

pub fn binary_repeat_search<T>(seq: &Vec<T>, m: usize) -> usize
where
    T: Eq,
{
    let mut low: usize = 0;
    let mut high: usize = seq.len();

    while low < high {
        let mid = ((high - low) / 2) + low;

        if let Some(_n) = repeats_m(&seq[0..mid], m) {
            high = mid;
        } else {
            low = mid + 1;
        }
    }

    low
}

pub fn build_fac_table(length: usize) -> Vec<u8> {
    (0..length)
        .map(|num| {
            let prime_factors = PrimeFactors::from(num as u128);

            let num_factors = prime_factors
                .iter()
                .fold(1, |n, factor| n * (1 + factor.exponent));

            num_factors.try_into().unwrap()
        })
        .collect()
}

// R(n,m) =
// the sum of the number of divisors of the last m elements
// Sequence starts with m 1's.
pub fn r(m: usize, max_length: usize, fac_table: Arc<Vec<u8>>) -> RResult<u16> {
    if m == 0 {
        return RResult {
            sequence: vec![],
            repeated: None,
            repeated_at: None,
        };
    }

    const CHECK_EVERY: usize = 1000000;

    let mut seq: Vec<u16> = Vec::new();
    let mut div_num_seq: Vec<usize> = Vec::new();
    let mut div_sum: usize = m.try_into().unwrap();
    for _i in 0..m {
        seq.push(1);
        div_num_seq.push(1);
    }

    while seq.len() < max_length {
        for _i in 0..CHECK_EVERY {
            seq.push(div_sum as u16);
            let new_n_divisors: usize = fac_table[div_sum as usize].into();

            div_sum -= div_num_seq[seq.len() % m];
            div_sum += new_n_divisors;

            div_num_seq[seq.len() % m] = new_n_divisors;
        }

        if let Some(_n) = repeats_m(&seq, m) {
            let rep_pos = binary_repeat_search(&seq, m) - m;
            let last_m = &seq[seq.len() - m..seq.len()];
            return RResult {
                sequence: seq.clone(),
                repeated: Some(last_m.to_owned()),
                repeated_at: Some(rep_pos),
            };
        }
    }

    RResult {
        sequence: seq,
        repeated: None,
        repeated_at: None,
    }
}

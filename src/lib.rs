use std::sync::Arc;

pub struct RResult {
    pub repeat_after: Option<usize>,
    pub max_value: u16,
}

// Table of divisor counts: `build_fac_table(n)[i] = τ(i)` for 1 <= i < n, plus τ(0) = 0.
//
// Built via a smallest-prime-factor sieve (Eratosthenes-style, O(n log log n)) followed by
// a linear pass using τ(p^a · k) = τ(k) · (a+1) when gcd(p, k) = 1 — i.e.
// τ(i) = τ(i/p) · (a+1) / a where p = spf(i), a = v_p(i).
pub fn build_fac_table(length: usize) -> Vec<u8> {
    let mut tau = vec![0u8; length];
    if length == 0 {
        return tau;
    }

    let mut spf = vec![0u32; length];
    for i in 2..length {
        if spf[i] == 0 {
            let mut j = i;
            while j < length {
                if spf[j] == 0 {
                    spf[j] = i as u32;
                }
                j += i;
            }
        }
    }

    // `cnt[i]` = v_p(i) for p = spf(i); scratch, not returned.
    let mut cnt = vec![0u8; length];
    if length > 1 {
        tau[1] = 1;
    }
    for i in 2..length {
        let p = spf[i] as usize;
        let j = i / p;
        let t: u16 = if spf[j] as usize == p {
            cnt[i] = cnt[j] + 1;
            tau[j] as u16 * (cnt[i] as u16 + 1) / (cnt[j] as u16 + 1)
        } else {
            cnt[i] = 1;
            tau[j] as u16 * 2
        };
        tau[i] = t.try_into().unwrap();
    }
    tau
}

// Ring-buffered state of the sliding-window dynamical system.
//
// `window[i]` holds one of the last `m` emitted terms; `div_counts[i] = d(window[i])`;
// `div_sum = sum(div_counts)` is the next term to be emitted. `head` is the slot that
// will be overwritten next (equivalently: the current oldest entry).
#[derive(Clone)]
struct State {
    window: Vec<u16>,
    div_counts: Vec<u8>,
    head: usize,
    div_sum: usize,
}

impl State {
    fn initial(m: usize) -> Self {
        Self {
            window: vec![1; m],
            div_counts: vec![1; m],
            head: 0,
            div_sum: m,
        }
    }

    #[inline]
    fn step(&mut self, fac_table: &[u8]) -> u16 {
        let next_value = self.div_sum as u16;
        let new_d = match fac_table.get(self.div_sum) {
            Some(&d) => d,
            None => panic!(
                "fac_table too small: need divisor count of {} but table has {} entries — raise the fac_table size",
                self.div_sum,
                fac_table.len()
            ),
        };
        let head = self.head;
        self.div_sum += new_d as usize;
        self.div_sum -= self.div_counts[head] as usize;
        self.window[head] = next_value;
        self.div_counts[head] = new_d;
        self.head = head + 1;
        if self.head == self.window.len() {
            self.head = 0;
        }
        next_value
    }

    #[inline]
    fn window_eq(&self, other: &Self) -> bool {
        if self.div_sum != other.div_sum {
            return false;
        }
        let m = self.window.len();
        for i in 0..m {
            let mut ai = self.head + i;
            if ai >= m {
                ai -= m;
            }
            let mut bi = other.head + i;
            if bi >= m {
                bi -= m;
            }
            if self.window[ai] != other.window[bi] {
                return false;
            }
        }
        true
    }
}

// R(n,m) = sum of the number of divisors of the last m terms; seeded with m 1's.
//
// Uses Brent's cycle detection on the sliding-window state, so memory is O(m) rather than
// O(repeat_after). Returns `repeat_after = mu + lambda + m` — the sequence length at which
// the last m terms first coincide with an earlier run of m terms (matching `results.csv`).
pub fn r(m: usize, max_length: usize, fac_table: Arc<Vec<u8>>) -> RResult {
    if m == 0 {
        return RResult {
            repeat_after: None,
            max_value: 0,
        };
    }

    let mut state = State::initial(m);
    let mut max_value: u16 = 1;

    let max_steps = max_length.saturating_sub(m);
    if max_steps == 0 {
        return RResult {
            repeat_after: None,
            max_value,
        };
    }

    // Brent's cycle detection. `snapshot` is the tortoise, `state` is the hare.
    let mut snapshot = state.clone();
    let v = state.step(&fac_table);
    if v > max_value {
        max_value = v;
    }
    let mut steps: usize = 1;

    let mut power: usize = 1;
    let mut lam: usize = 1;

    loop {
        if state.window_eq(&snapshot) {
            let mu = find_cycle_start(m, lam, &fac_table);
            return RResult {
                repeat_after: Some(mu + lam + m),
                max_value,
            };
        }

        if steps >= max_steps {
            return RResult {
                repeat_after: None,
                max_value,
            };
        }

        if power == lam {
            snapshot = state.clone();
            power *= 2;
            lam = 0;
        }

        let v = state.step(&fac_table);
        if v > max_value {
            max_value = v;
        }
        steps += 1;
        lam += 1;
    }
}

// Given the cycle period `lam`, replay from the initial state and return the index `mu`
// at which the cycle begins: the smallest k with W(k) == W(k + lam).
fn find_cycle_start(m: usize, lam: usize, fac_table: &[u8]) -> usize {
    let mut tortoise = State::initial(m);
    let mut hare = State::initial(m);
    for _ in 0..lam {
        hare.step(fac_table);
    }
    let mut mu: usize = 0;
    while !tortoise.window_eq(&hare) {
        tortoise.step(fac_table);
        hare.step(fac_table);
        mu += 1;
    }
    mu
}

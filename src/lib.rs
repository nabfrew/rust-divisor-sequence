use std::collections::HashMap;
use std::io::{self, Read, Write};
use std::path::Path;
use std::sync::Arc;

pub struct RResult {
    pub repeat_after: Option<usize>,
    pub max_value: u32,
    pub cycle_length: Option<usize>,
    pub cycle_max: Option<u32>,
    pub cycle_min: Option<u32>,
    pub most_common_tail_value: Option<u32>,
    pub distinct_tail_values: Option<usize>,
    // Phase C.3 scaffolding: step at which the trajectory first locks into its
    // eventual cycle (the smallest k with W(k) == W(k+λ)). Currently always
    // `None` — the metric is wired through CSV / Row / RResult so the column
    // exists, but the underlying step is not yet computed in the Brent loop.
    // Reserved for the lock-in metric (analysis/explore.ipynb §12, Further work).
    pub steps_to_lock_in: Option<usize>,
    // Value→count multiset for one full period of the tail. Populated whenever a cycle is
    // detected (alongside the scalar stats above) and `None` on timeout. Lets callers like
    // `dump-signature` persist the attractor signature without re-running the trial; the
    // ordered period is intentionally **not** materialised — it can be 10⁷+ terms at large m.
    pub signature: Option<HashMap<u32, u64>>,
}

// Table of divisor counts: `build_fac_table(n)[i] = τ(i)` for 1 <= i < n, plus τ(0) = 0.
//
// Built via a smallest-prime-factor sieve (Eratosthenes-style, O(n log log n)) followed by
// a linear pass using τ(p^a · k) = τ(k) · (a+1) when gcd(p, k) = 1 — i.e.
// τ(i) = τ(i/p) · (a+1) / a where p = spf(i), a = v_p(i).
//
// Entries are u16 so the table can cover trajectory values up to ~10⁷ without τ
// overflowing — the smallest n with τ(n) > 65 535 is well above any value the
// dynamics can reach (the bounded-orbit proof in `analysis/explore.ipynb` §1
// caps every trajectory by 4·m² ≪ 10⁹).
pub fn build_fac_table(length: usize) -> Vec<u16> {
    let mut tau = vec![0u16; length];
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
    let mut cnt = vec![0u16; length];
    if length > 1 {
        tau[1] = 1;
    }
    for i in 2..length {
        let p = spf[i] as usize;
        let j = i / p;
        let t: u32 = if spf[j] as usize == p {
            cnt[i] = cnt[j] + 1;
            tau[j] as u32 * (cnt[i] as u32 + 1) / (cnt[j] as u32 + 1)
        } else {
            cnt[i] = 1;
            tau[j] as u32 * 2
        };
        tau[i] = t.try_into().unwrap();
    }
    tau
}

// Rabin-Karp base. Odd 64-bit constant (FNV-1a 64-bit prime) chosen for its
// good bit-mixing properties under `wrapping_mul`. Collision probability is
// ~2^-64 per compare; correctness is unaffected because on a hash match we
// still verify the window bit-for-bit.
const HASH_B: u64 = 0x100_0000_01b3;

// Ring-buffered state of the sliding-window dynamical system.
//
// `window[i]` holds one of the last `m` emitted terms; `div_counts[i] = d(window[i])`;
// `div_sum = sum(div_counts)` is the next term to be emitted. `head` is the slot that
// will be overwritten next (equivalently: the current oldest entry).
//
// `hash` is a Rabin-Karp rolling hash of the window in temporal order (oldest-first),
// maintained in O(1) per step. Two states have the same temporal window iff their
// hashes agree (up to 2^-64 false-positive) — lets Brent's tortoise/hare comparison
// short-circuit almost every iteration without the O(m) ring-buffer scan.
//
// `b_pow_m_minus_1 = HASH_B^(m-1)` (mod 2^64, wrapping) is precomputed once at
// State creation so the step update is a handful of wrapping ops.
//
// `window` is `Vec<u32>` so trajectories can hold their true values without
// truncation. The original `Vec<u16>` silently wrapped via `as u16` once
// `div_sum` exceeded 65 535 — cheap on memory but corrupted random-seed
// transients at larger m, where seed values pushed div_sum well past u16::MAX
// for the first few thousand steps until the orbit relaxed into its real
// cycle. u32 covers any trajectory value the bounded-orbit proof (4·m²)
// admits for m up to ~32 000.
#[derive(Clone)]
struct State {
    window: Vec<u32>,
    div_counts: Vec<u16>,
    head: usize,
    div_sum: usize,
    hash: u64,
    b_pow_m_minus_1: u64,
    tau_counts: [u16; 256],
    tau_set_bitset: [u64; 4],
    tau_set_stable_steps: usize,
}

impl State {
    fn initial(m: usize) -> Self {
        // hash of m ones in temporal order = B^(m-1) + B^(m-2) + ... + B + 1
        let mut hash: u64 = 0;
        for _ in 0..m {
            hash = hash.wrapping_mul(HASH_B).wrapping_add(1);
        }
        let mut b_pow_m_minus_1: u64 = 1;
        for _ in 0..m.saturating_sub(1) {
            b_pow_m_minus_1 = b_pow_m_minus_1.wrapping_mul(HASH_B);
        }
        let mut tau_counts = [0u16; 256];
        tau_counts[1] = m as u16;
        let mut tau_set_bitset = [0u64; 4];
        tau_set_bitset[0] |= 1 << 1; // divisor count 1 is present
        Self {
            window: vec![1; m],
            div_counts: vec![1; m],
            head: 0,
            div_sum: m,
            hash,
            b_pow_m_minus_1,
            tau_counts,
            tau_set_bitset,
            tau_set_stable_steps: 0,
        }
    }

    // Build a state from an arbitrary seed window (in temporal/oldest-first order).
    // Used by E.4/E.6 basin probes — the regular `r()` path keeps seeding with all 1s.
    // Panics if `seed.len() != m` or any value indexes past `fac_table`.
    fn from_window(m: usize, seed: &[u32], fac_table: &[u16]) -> Self {
        assert_eq!(
            seed.len(),
            m,
            "seed window length {} must equal m={}",
            seed.len(),
            m,
        );
        let mut hash: u64 = 0;
        let mut div_counts: Vec<u16> = Vec::with_capacity(m);
        let mut div_sum: usize = 0;
        for &v in seed {
            hash = hash.wrapping_mul(HASH_B).wrapping_add(v as u64);
            let idx = v as usize;
            let d = match fac_table.get(idx) {
                Some(&d) => d,
                None => panic!(
                    "seed value {} exceeds fac_table size {} — raise --fac-table-size",
                    v,
                    fac_table.len()
                ),
            };
            div_counts.push(d);
            div_sum += d as usize;
        }
        let mut b_pow_m_minus_1: u64 = 1;
        for _ in 0..m.saturating_sub(1) {
            b_pow_m_minus_1 = b_pow_m_minus_1.wrapping_mul(HASH_B);
        }
        let mut tau_counts = [0u16; 256];
        let mut tau_set_bitset = [0u64; 4];
        for &d in &div_counts {
            let d_idx = d as usize;
            if d_idx < 256 {
                tau_counts[d_idx] += 1;
                tau_set_bitset[d_idx / 64] |= 1 << (d_idx % 64);
            }
        }
        Self {
            window: seed.to_vec(),
            div_counts,
            head: 0,
            div_sum,
            hash,
            b_pow_m_minus_1,
            tau_counts,
            tau_set_bitset,
            tau_set_stable_steps: 0,
        }
    }

    // Hot loop. Direct indexing on `fac_table` keeps the bounds-check panic semantics
    // (produces a slim `slice_index_len_fail` cold-call rather than the original
    // `match` arm with a formatted panic message that bloated codegen). Window/
    // div_counts indexing is hoisted: `head < self.window.len()` is invariant (the wrap
    // step below resets to 0 on reaching len, `initial`/`from_window` start at 0), so
    // a single `assert_unchecked` lets LLVM elide the per-access bounds checks.
    //
    // `next_value = self.div_sum as u32` is exact for any orbit the bounded-orbit
    // proof permits (4·m² ≪ u32::MAX for m up to ~32 000). The fac_table lookup
    // would panic with `index out of bounds` long before u32 truncation became
    // possible, since fac_table is sized to cover every value the run can emit.
    #[inline]
    fn step(&mut self, fac_table: &[u16]) -> u32 {
        let next_value = self.div_sum as u32;
        let new_d = fac_table[self.div_sum];

        let head = self.head;
        let m = self.window.len();
        debug_assert_eq!(self.div_counts.len(), m);
        debug_assert!(head < m);
        // SAFETY: invariant `head < m` documented above.
        unsafe { core::hint::assert_unchecked(head < m) };
        unsafe { core::hint::assert_unchecked(head < self.div_counts.len()) };

        let old_value = self.window[head];
        let old_d = self.div_counts[head];
        self.div_sum += new_d as usize;
        self.div_sum -= old_d as usize;
        self.window[head] = next_value;
        self.div_counts[head] = new_d;

        let prev_bitset = self.tau_set_bitset;
        // Update tau_counts and bitset
        if (old_d as usize) < 256 {
            self.tau_counts[old_d as usize] -= 1;
            if self.tau_counts[old_d as usize] == 0 {
                self.tau_set_bitset[old_d as usize / 64] &= !(1 << (old_d as usize % 64));
            }
        }
        if (new_d as usize) < 256 {
            if self.tau_counts[new_d as usize] == 0 {
                self.tau_set_bitset[new_d as usize / 64] |= 1 << (new_d as usize % 64);
            }
            self.tau_counts[new_d as usize] += 1;
        }

        if self.tau_set_bitset == prev_bitset {
            self.tau_set_stable_steps += 1;
        } else {
            self.tau_set_stable_steps = 0;
        }

        let new_head = head + 1;
        self.head = if new_head == m { 0 } else { new_head };

        // Rolling update: h_{t+1} = (h_t - old * B^(m-1)) * B + new   (mod 2^64)
        self.hash = self
            .hash
            .wrapping_sub((old_value as u64).wrapping_mul(self.b_pow_m_minus_1))
            .wrapping_mul(HASH_B)
            .wrapping_add(next_value as u64);
        next_value
    }

    // Bit-for-bit comparison of the temporal window. Called only when hashes
    // collide (vanishingly rare); kept correct-by-construction.
    #[inline(never)]
    fn window_eq_slow(&self, other: &Self) -> bool {
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

    #[inline]
    fn window_eq(&self, other: &Self) -> bool {
        self.hash == other.hash && self.window_eq_slow(other)
    }
}

// R(n,m) = sum of the number of divisors of the last m terms; seeded with m 1's.
//
// Uses Brent's cycle detection on the sliding-window state, so memory is O(m) rather than
// O(repeat_after). Returns `repeat_after = mu + lambda + m` — the sequence length at which
// the last m terms first coincide with an earlier run of m terms (matching `results.csv`).
//
// When a cycle is found, also computes stats over one full period of the tail (cycle length
// lambda, min/max/most-common/distinct counts) by streaming the lambda terms without storing
// them — some m produce cycles of 10^7+ terms where materialising the period would blow out
// memory.
pub fn r(m: usize, max_length: usize, fac_table: Arc<Vec<u16>>) -> RResult {
    r_with_progress(m, max_length, fac_table, 0, |_| {})
}

// Progress event emitted from `r_with_progress` during long trials, so callers can
// surface heartbeat output without waiting for the trial to finish.
#[derive(Clone, Copy, Debug)]
pub struct Progress {
    pub phase: ProgressPhase,
    pub step: usize,
    pub max_value: u32,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ProgressPhase {
    Brent,
    FindMu,
}

// Like `r` but emits a `Progress` event every `progress_interval` steps to `on_progress`
// (set `progress_interval = 0` to disable). Used by the CLI to print heartbeat output;
// tests and benches use the no-op `r` wrapper.
//
// Pass `max_length = usize::MAX` to disable the step cap entirely (the trial then runs
// until a cycle is detected — the bounded-orbit proof guarantees termination). The CLI
// defaults to `usize::MAX` after the u16-truncation fix; a finite cap is now only
// useful for tests that intentionally exercise the timeout branch.
pub fn r_with_progress<F>(
    m: usize,
    max_length: usize,
    fac_table: Arc<Vec<u16>>,
    progress_interval: usize,
    on_progress: F,
) -> RResult
where
    F: FnMut(Progress),
{
    if m == 0 {
        return timed_out(0);
    }
    r_inner(
        m,
        State::initial(m),
        max_length,
        fac_table,
        progress_interval,
        on_progress,
    )
}

// Like `r_with_progress` but starts from an arbitrary seed window instead of all 1s.
// Used by basin-of-attraction probes (E.4 flat-ceiling, E.6 random-around-mlnm).
// `seed` must be in temporal order (oldest first) and have length `m`.
pub fn r_seeded_with_progress<F>(
    m: usize,
    seed: &[u32],
    max_length: usize,
    fac_table: Arc<Vec<u16>>,
    progress_interval: usize,
    on_progress: F,
) -> RResult
where
    F: FnMut(Progress),
{
    if m == 0 {
        return timed_out(0);
    }
    let state = State::from_window(m, seed, &fac_table);
    r_inner(m, state, max_length, fac_table, progress_interval, on_progress)
}

// Inner Brent loop, parameterised over the starting state. Both the seed=ones path
// (`r_with_progress`) and the seeded path (`r_seeded_with_progress`) flow through here.
fn r_inner<F>(
    m: usize,
    initial_state: State,
    max_length: usize,
    fac_table: Arc<Vec<u16>>,
    progress_interval: usize,
    mut on_progress: F,
) -> RResult
where
    F: FnMut(Progress),
{
    let mut state = initial_state;
    // For seed=ones the initial window max is 1; for arbitrary seeds we must seed
    // `max_value` from the window or we'd under-report when a seed value exceeds
    // anything later emitted.
    let mut max_value: u32 = state.window.iter().copied().max().unwrap_or(1);

    let max_steps = max_length.saturating_sub(m);
    if max_steps == 0 {
        return timed_out(max_value);
    }

    let progress_interval = if progress_interval == 0 {
        usize::MAX
    } else {
        progress_interval
    };
    let mut next_progress = progress_interval;

    // Brent's cycle detection. The current tortoise is `snapshots.last()`; `state` is the
    // hare. Unlike classic Brent we retain every past tortoise (one per power-of-2 step)
    // so `find_cycle_start` can pick up from the most recent pre-cycle snapshot instead of
    // replaying from step 0. The snapshot stack is at most ⌈log₂ steps⌉ entries (≈33 at
    // steps = 10¹⁰), so memory is negligible.
    let mut snapshots: Vec<(usize, State)> = Vec::with_capacity(40);
    snapshots.push((0, state.clone()));
    let v = state.step(&fac_table);
    if v > max_value {
        max_value = v;
    }
    let mut steps: usize = 1;

    let mut power: usize = 1;
    let mut lam: usize = 1;
    let mut lock_in_step: Option<usize> = if state.tau_set_stable_steps >= 2 * m {
        Some(steps + 1 - 2 * m)
    } else {
        None
    };

    loop {
        if state.window_eq(&snapshots.last().expect("snapshot stack is non-empty").1) {
            let detection_step = steps;
            let (mu, cycle_state) = find_cycle_start(
                m,
                lam,
                &snapshots,
                &fac_table,
                detection_step,
                progress_interval,
                &mut on_progress,
                max_value,
            );
            let (stats, signature) = summarize_cycle(cycle_state, lam, &fac_table);
            return RResult {
                repeat_after: Some(mu + lam + m),
                max_value,
                cycle_length: Some(lam),
                cycle_max: Some(stats.max),
                cycle_min: Some(stats.min),
                most_common_tail_value: Some(stats.most_common),
                distinct_tail_values: Some(stats.distinct),
                steps_to_lock_in: lock_in_step,
                signature: Some(signature),
            };
        }

        if steps >= max_steps {
            return timed_out(max_value);
        }

        if power == lam {
            snapshots.push((steps, state.clone()));
            power *= 2;
            lam = 0;
        }

        let v = state.step(&fac_table);
        if v > max_value {
            max_value = v;
        }

        if state.tau_set_stable_steps >= 2 * m {
            if lock_in_step.is_none() {
                lock_in_step = Some(steps + 1 - 2 * m);
            }
        } else {
            lock_in_step = None;
        }

        steps += 1;
        lam += 1;

        if steps >= next_progress {
            on_progress(Progress {
                phase: ProgressPhase::Brent,
                step: steps,
                max_value,
            });
            next_progress = next_progress.saturating_add(progress_interval);
        }
    }
}

fn timed_out(max_value: u32) -> RResult {
    RResult {
        repeat_after: None,
        max_value,
        cycle_length: None,
        cycle_max: None,
        cycle_min: None,
        most_common_tail_value: None,
        distinct_tail_values: None,
        steps_to_lock_in: None,
        signature: None,
    }
}

#[derive(Debug)]
pub struct CheckpointError(pub String);

impl std::fmt::Display for CheckpointError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for CheckpointError {}

impl From<io::Error> for CheckpointError {
    fn from(e: io::Error) -> Self {
        CheckpointError(e.to_string())
    }
}

// Like `r_with_progress`, but periodically writes a sidecar checkpoint at
// `checkpoint_path` and resumes from it on restart. Use 0 for
// `checkpoint_interval_steps` to disable saves (the file is still loaded if it
// exists). On a successful cycle detection the checkpoint file is deleted; on
// timeout it is preserved so the trial can be resumed with a higher
// `--max-steps`. Only the Brent main loop is checkpointed — `find_cycle_start`
// runs to completion uninterrupted.
pub fn r_resumable<F>(
    m: usize,
    max_length: usize,
    fac_table: Arc<Vec<u16>>,
    progress_interval: usize,
    mut on_progress: F,
    checkpoint_path: &Path,
    checkpoint_interval_steps: usize,
) -> Result<RResult, CheckpointError>
where
    F: FnMut(Progress),
{
    if m == 0 {
        return Ok(timed_out(0));
    }

    let max_steps = max_length.saturating_sub(m);
    if max_steps == 0 {
        return Ok(timed_out(1));
    }

    let progress_interval = if progress_interval == 0 {
        usize::MAX
    } else {
        progress_interval
    };
    let checkpoint_interval = if checkpoint_interval_steps == 0 {
        usize::MAX
    } else {
        checkpoint_interval_steps
    };

    // Either resume from disk or initialise the same way `r_with_progress` does.
    let resumed = checkpoint_load(checkpoint_path, m, max_length, &fac_table)?;
    let (mut state, mut snapshots, mut steps, mut power, mut lam, mut max_value, mut lock_in_step) =
        if let Some(c) = resumed {
            (c.state, c.snapshots, c.steps, c.power, c.lam, c.max_value, None)
        } else {
            let mut state = State::initial(m);
            let mut snapshots: Vec<(usize, State)> = Vec::with_capacity(40);
            snapshots.push((0, state.clone()));
            let v = state.step(&fac_table);
            let max_value = v.max(1);
            let lock_in_step = if state.tau_set_stable_steps >= 2 * m {
                Some(1 + 1 - 2 * m)
            } else {
                None
            };
            (state, snapshots, 1usize, 1usize, 1usize, max_value, lock_in_step)
        };

    let mut next_progress = steps.saturating_add(progress_interval);
    let mut next_checkpoint = steps.saturating_add(checkpoint_interval);

    loop {
        if state.window_eq(&snapshots.last().expect("snapshot stack is non-empty").1) {
            let detection_step = steps;
            let (mu, cycle_state) = find_cycle_start(
                m,
                lam,
                &snapshots,
                &fac_table,
                detection_step,
                progress_interval,
                &mut on_progress,
                max_value,
            );
            let (stats, signature) = summarize_cycle(cycle_state, lam, &fac_table);
            // Trial complete: drop the sidecar so a future invocation starts fresh.
            let _ = std::fs::remove_file(checkpoint_path);
            return Ok(RResult {
                repeat_after: Some(mu + lam + m),
                max_value,
                cycle_length: Some(lam),
                cycle_max: Some(stats.max),
                cycle_min: Some(stats.min),
                most_common_tail_value: Some(stats.most_common),
                distinct_tail_values: Some(stats.distinct),
                steps_to_lock_in: lock_in_step,
                signature: Some(signature),
            });
        }

        if steps >= max_steps {
            // Preserve the checkpoint so the user can resume with a larger cap.
            checkpoint_save(
                checkpoint_path,
                m,
                max_length,
                steps,
                power,
                lam,
                max_value,
                &state,
                &snapshots,
            )?;
            return Ok(timed_out(max_value));
        }

        if power == lam {
            snapshots.push((steps, state.clone()));
            power *= 2;
            lam = 0;
        }

        let v = state.step(&fac_table);
        if v > max_value {
            max_value = v;
        }

        if state.tau_set_stable_steps >= 2 * m {
            if lock_in_step.is_none() {
                lock_in_step = Some(steps + 1 - 2 * m);
            }
        } else {
            lock_in_step = None;
        }

        steps += 1;
        lam += 1;

        if steps >= next_progress {
            on_progress(Progress {
                phase: ProgressPhase::Brent,
                step: steps,
                max_value,
            });
            next_progress = next_progress.saturating_add(progress_interval);
        }

        if steps >= next_checkpoint {
            checkpoint_save(
                checkpoint_path,
                m,
                max_length,
                steps,
                power,
                lam,
                max_value,
                &state,
                &snapshots,
            )?;
            next_checkpoint = next_checkpoint.saturating_add(checkpoint_interval);
        }
    }
}

// Given the cycle period `lam` and the stack of past tortoises (one per power-of-2 step,
// plus the initial state), return `(mu, state_at_mu)`: `mu` is the smallest k with
// W(k) == W(k + lam); `state_at_mu` is the tortoise parked at W(mu), ready to be stepped
// forward to enumerate one period of the cycle.
//
// Previously this replayed from the initial state — O(mu) extra steps. Instead, pick the
// most recent snapshot whose step is strictly less than mu (equivalently: the most recent
// snapshot S whose state differs from its own state advanced by lam). Replay from there,
// saving up to ~mu/2 steps at large mu.
fn find_cycle_start<F>(
    m: usize,
    lam: usize,
    snapshots: &[(usize, State)],
    fac_table: &[u16],
    detection_step: usize,
    progress_interval: usize,
    on_progress: &mut F,
    max_value: u32,
) -> (usize, State)
where
    F: FnMut(Progress),
{
    // Walk snapshots newest → oldest. A snapshot at step s is pre-cycle iff advancing its
    // state by lam yields a different window (i.e. W(s) != W(s + lam), so s < mu).
    // The first such snapshot is the closest pre-cycle starting point.
    let (start_step, start_state) = {
        let mut chosen: Option<(usize, &State)> = None;
        for (s, st) in snapshots.iter().rev() {
            let mut advanced = st.clone();
            for _ in 0..lam {
                advanced.step(fac_table);
            }
            if !advanced.window_eq(st) {
                chosen = Some((*s, st));
                break;
            }
        }
        match chosen {
            Some((s, st)) => (s, st.clone()),
            // All snapshots — including step 0 — are already inside the cycle. This implies
            // mu = 0 (the initial state W(0) already satisfies W(0) == W(lam)). Return that.
            None => (0, State::initial(m)),
        }
    };

    let mut tortoise = start_state;
    let mut hare = tortoise.clone();
    for _ in 0..lam {
        hare.step(fac_table);
    }
    let mut mu: usize = start_step;
    let mut next_progress = detection_step.saturating_add(progress_interval);
    let mut virtual_step = detection_step;
    while !tortoise.window_eq(&hare) {
        tortoise.step(fac_table);
        hare.step(fac_table);
        mu += 1;
        virtual_step = virtual_step.saturating_add(2); // tortoise + hare each took one step
        if virtual_step >= next_progress {
            on_progress(Progress {
                phase: ProgressPhase::FindMu,
                step: virtual_step,
                max_value,
            });
            next_progress = next_progress.saturating_add(progress_interval);
        }
    }
    (mu, tortoise)
}

struct CycleStats {
    max: u32,
    min: u32,
    most_common: u32,
    distinct: usize,
}

// Stream one full period of the tail — the `lam` values emitted starting from state W(mu),
// i.e. a_{m+mu}..a_{m+mu+lam-1} — and compute summary stats without materialising the vec.
// The vec would be O(lam) which hits 10^7+ at larger m; stats fit in a HashMap keyed by the
// distinct tail values (always ≪ lam in practice). Ties on "most common" break toward the
// smaller value so the result is deterministic regardless of HashMap iteration order.
//
// Returns (stats, counts): `counts` is the value→count multiset of the period. Phase B's
// attractor catalog needs this map; the original signature discarded it. Returning the
// HashMap is essentially free — `summarize_cycle` allocated it anyway.
fn summarize_cycle(mut state: State, lam: usize, fac_table: &[u16]) -> (CycleStats, HashMap<u32, u64>) {
    assert!(lam >= 1, "cycle must have positive length");
    let first = state.step(fac_table);
    let mut counts: HashMap<u32, u64> = HashMap::new();
    counts.insert(first, 1);
    let mut max = first;
    let mut min = first;
    for _ in 1..lam {
        let v = state.step(fac_table);
        *counts.entry(v).or_insert(0) += 1;
        if v > max {
            max = v;
        }
        if v < min {
            min = v;
        }
    }
    let (&most_common, _) = counts
        .iter()
        .min_by(|a, b| b.1.cmp(a.1).then_with(|| a.0.cmp(b.0)))
        .expect("non-empty cycle has at least one distinct value");
    (
        CycleStats {
            max,
            min,
            most_common,
            distinct: counts.len(),
        },
        counts,
    )
}

// ---------------------------------------------------------------------------
// Checkpoint format
//
// Little-endian binary, packed:
//   magic[4]      = "DSCK"
//   version: u32  = 2  (was 1 with u16 windows; v2 widens to u32 windows after
//                       the silent-truncation fix in `State::step`)
//   m: u64
//   max_length: u64
//   steps: u64
//   power: u64
//   lam: u64
//   max_value: u32
//   n_snapshots: u32
//   for each snapshot:
//     snap_step: u64
//     head: u32, hash: u64, window: m × u32
//   current state:
//     head: u32, hash: u64, window: m × u32
//
// Only `window` is persisted per state; `div_counts`, `div_sum`, and
// `b_pow_m_minus_1` are reconstructed from `fac_table` and `m` on load.
// Saves are atomic via write-to-tmp + rename so a kill mid-write cannot
// corrupt an existing checkpoint.

const CKPT_MAGIC: [u8; 4] = *b"DSCK";
const CKPT_VERSION: u32 = 2;

struct Resumed {
    state: State,
    snapshots: Vec<(usize, State)>,
    steps: usize,
    power: usize,
    lam: usize,
    max_value: u32,
}

fn checkpoint_load(
    path: &Path,
    expected_m: usize,
    _expected_max_length: usize,
    fac_table: &[u16],
) -> Result<Option<Resumed>, CheckpointError> {
    let mut f = match std::fs::File::open(path) {
        Ok(f) => f,
        Err(e) if e.kind() == io::ErrorKind::NotFound => return Ok(None),
        Err(e) => return Err(e.into()),
    };

    let mut magic = [0u8; 4];
    f.read_exact(&mut magic)?;
    if magic != CKPT_MAGIC {
        return Err(CheckpointError(format!(
            "{}: bad magic {:?}",
            path.display(),
            magic
        )));
    }
    let version = read_u32(&mut f)?;
    if version != CKPT_VERSION {
        return Err(CheckpointError(format!(
            "{}: unsupported checkpoint version {} (expected {}). v1 used u16 windows \
             that silently truncated random-seed transients; delete the .ckpt and re-run \
             — the trial restarts from scratch with the u32 fix.",
            path.display(),
            version,
            CKPT_VERSION
        )));
    }
    let m = read_u64(&mut f)? as usize;
    // `_max_length` is recorded for forensics but not enforced — the runtime state is
    // independent of the cap, so resuming with a higher (or lower) `--max-steps` is fine.
    let _max_length = read_u64(&mut f)? as usize;
    if m != expected_m {
        return Err(CheckpointError(format!(
            "{}: m mismatch (file {} vs requested {})",
            path.display(),
            m,
            expected_m
        )));
    }
    let steps = read_u64(&mut f)? as usize;
    let power = read_u64(&mut f)? as usize;
    let lam = read_u64(&mut f)? as usize;
    let max_value = read_u32(&mut f)?;
    let n_snapshots = read_u32(&mut f)? as usize;

    let mut snapshots: Vec<(usize, State)> = Vec::with_capacity(n_snapshots);
    for _ in 0..n_snapshots {
        let step = read_u64(&mut f)? as usize;
        let st = read_state(&mut f, m, fac_table)?;
        snapshots.push((step, st));
    }
    let state = read_state(&mut f, m, fac_table)?;

    Ok(Some(Resumed {
        state,
        snapshots,
        steps,
        power,
        lam,
        max_value,
    }))
}

fn checkpoint_save(
    path: &Path,
    m: usize,
    max_length: usize,
    steps: usize,
    power: usize,
    lam: usize,
    max_value: u32,
    state: &State,
    snapshots: &[(usize, State)],
) -> Result<(), CheckpointError> {
    let tmp = path.with_extension("ckpt.tmp");
    {
        let mut f = std::io::BufWriter::new(std::fs::File::create(&tmp)?);
        f.write_all(&CKPT_MAGIC)?;
        f.write_all(&CKPT_VERSION.to_le_bytes())?;
        f.write_all(&(m as u64).to_le_bytes())?;
        f.write_all(&(max_length as u64).to_le_bytes())?;
        f.write_all(&(steps as u64).to_le_bytes())?;
        f.write_all(&(power as u64).to_le_bytes())?;
        f.write_all(&(lam as u64).to_le_bytes())?;
        f.write_all(&max_value.to_le_bytes())?;
        f.write_all(&(snapshots.len() as u32).to_le_bytes())?;
        for (snap_step, snap_state) in snapshots {
            f.write_all(&(*snap_step as u64).to_le_bytes())?;
            write_state(&mut f, snap_state)?;
        }
        write_state(&mut f, state)?;
        f.flush()?;
    }
    std::fs::rename(&tmp, path)?;
    Ok(())
}

fn write_state<W: Write>(w: &mut W, state: &State) -> io::Result<()> {
    w.write_all(&(state.head as u32).to_le_bytes())?;
    w.write_all(&state.hash.to_le_bytes())?;
    for v in &state.window {
        w.write_all(&v.to_le_bytes())?;
    }
    Ok(())
}

fn read_state<R: Read>(r: &mut R, m: usize, fac_table: &[u16]) -> Result<State, CheckpointError> {
    let head = read_u32(r)? as usize;
    if head >= m {
        return Err(CheckpointError(format!(
            "checkpoint head {} out of range for m={}",
            head, m
        )));
    }
    let hash = read_u64(r)?;
    let mut window = vec![0u32; m];
    for slot in window.iter_mut() {
        *slot = read_u32(r)?;
    }
    // Reconstruct derived fields from the persisted window.
    let mut div_counts = Vec::with_capacity(m);
    let mut div_sum: usize = 0;
    for &v in &window {
        let idx = v as usize;
        if idx >= fac_table.len() {
            return Err(CheckpointError(format!(
                "checkpoint window value {} exceeds fac_table size {} — re-run with a larger --fac-table-size",
                v,
                fac_table.len()
            )));
        }
        let d = fac_table[idx];
        div_counts.push(d);
        div_sum += d as usize;
    }
    let mut b_pow_m_minus_1: u64 = 1;
    for _ in 0..m.saturating_sub(1) {
        b_pow_m_minus_1 = b_pow_m_minus_1.wrapping_mul(HASH_B);
    }
    let mut tau_counts = [0u16; 256];
    let mut tau_set_bitset = [0u64; 4];
    for &d in &div_counts {
        let d_idx = d as usize;
        if d_idx < 256 {
            tau_counts[d_idx] += 1;
            tau_set_bitset[d_idx / 64] |= 1 << (d_idx % 64);
        }
    }
    Ok(State {
        window,
        div_counts,
        head,
        div_sum,
        hash,
        b_pow_m_minus_1,
        tau_counts,
        tau_set_bitset,
        tau_set_stable_steps: 0,
    })
}

fn read_u32<R: Read>(r: &mut R) -> io::Result<u32> {
    let mut b = [0u8; 4];
    r.read_exact(&mut b)?;
    Ok(u32::from_le_bytes(b))
}

fn read_u64<R: Read>(r: &mut R) -> io::Result<u64> {
    let mut b = [0u8; 8];
    r.read_exact(&mut b)?;
    Ok(u64::from_le_bytes(b))
}

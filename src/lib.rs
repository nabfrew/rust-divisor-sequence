use std::collections::HashMap;
use std::io::{self, Read, Write};
use std::path::Path;
use std::sync::Arc;

pub struct RResult {
    pub repeat_after: Option<usize>,
    pub max_value: u16,
    pub cycle_length: Option<usize>,
    pub cycle_max: Option<u16>,
    pub cycle_min: Option<u16>,
    pub most_common_tail_value: Option<u16>,
    pub distinct_tail_values: Option<usize>,
    // Value→count multiset for one full period of the tail. Populated whenever a cycle is
    // detected (alongside the scalar stats above) and `None` on timeout. Lets callers like
    // `dump-signature` persist the attractor signature without re-running the trial; the
    // ordered period is intentionally **not** materialised — it can be 10⁷+ terms at large m.
    pub signature: Option<HashMap<u16, u64>>,
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
#[derive(Clone)]
struct State {
    window: Vec<u16>,
    div_counts: Vec<u8>,
    head: usize,
    div_sum: usize,
    hash: u64,
    b_pow_m_minus_1: u64,
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
        Self {
            window: vec![1; m],
            div_counts: vec![1; m],
            head: 0,
            div_sum: m,
            hash,
            b_pow_m_minus_1,
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
        let old_value = self.window[head];
        self.div_sum += new_d as usize;
        self.div_sum -= self.div_counts[head] as usize;
        self.window[head] = next_value;
        self.div_counts[head] = new_d;
        self.head = head + 1;
        if self.head == self.window.len() {
            self.head = 0;
        }
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
pub fn r(m: usize, max_length: usize, fac_table: Arc<Vec<u8>>) -> RResult {
    r_with_progress(m, max_length, fac_table, 0, |_| {})
}

// Progress event emitted from `r_with_progress` during long trials, so callers can
// surface heartbeat output without waiting for the trial to finish.
#[derive(Clone, Copy, Debug)]
pub struct Progress {
    pub phase: ProgressPhase,
    pub step: usize,
    pub max_value: u16,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ProgressPhase {
    Brent,
    FindMu,
}

// Like `r` but emits a `Progress` event every `progress_interval` steps to `on_progress`
// (set `progress_interval = 0` to disable). Used by the CLI to print heartbeat output;
// tests and benches use the no-op `r` wrapper.
pub fn r_with_progress<F>(
    m: usize,
    max_length: usize,
    fac_table: Arc<Vec<u8>>,
    progress_interval: usize,
    mut on_progress: F,
) -> RResult
where
    F: FnMut(Progress),
{
    if m == 0 {
        return timed_out(0);
    }

    let mut state = State::initial(m);
    let mut max_value: u16 = 1;

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

fn timed_out(max_value: u16) -> RResult {
    RResult {
        repeat_after: None,
        max_value,
        cycle_length: None,
        cycle_max: None,
        cycle_min: None,
        most_common_tail_value: None,
        distinct_tail_values: None,
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
    fac_table: Arc<Vec<u8>>,
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
    let (mut state, mut snapshots, mut steps, mut power, mut lam, mut max_value) =
        if let Some(c) = resumed {
            (c.state, c.snapshots, c.steps, c.power, c.lam, c.max_value)
        } else {
            let mut state = State::initial(m);
            let mut snapshots: Vec<(usize, State)> = Vec::with_capacity(40);
            snapshots.push((0, state.clone()));
            let v = state.step(&fac_table);
            let max_value = v.max(1);
            (state, snapshots, 1usize, 1usize, 1usize, max_value)
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
    fac_table: &[u8],
    detection_step: usize,
    progress_interval: usize,
    on_progress: &mut F,
    max_value: u16,
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
    max: u16,
    min: u16,
    most_common: u16,
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
fn summarize_cycle(mut state: State, lam: usize, fac_table: &[u8]) -> (CycleStats, HashMap<u16, u64>) {
    assert!(lam >= 1, "cycle must have positive length");
    let first = state.step(fac_table);
    let mut counts: HashMap<u16, u64> = HashMap::new();
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
//   version: u32  = 1
//   m: u64
//   max_length: u64
//   steps: u64
//   power: u64
//   lam: u64
//   max_value: u16
//   n_snapshots: u32
//   for each snapshot:
//     snap_step: u64
//     head: u32, hash: u64, window: m × u16
//   current state:
//     head: u32, hash: u64, window: m × u16
//
// Only `window` is persisted per state; `div_counts`, `div_sum`, and
// `b_pow_m_minus_1` are reconstructed from `fac_table` and `m` on load.
// Saves are atomic via write-to-tmp + rename so a kill mid-write cannot
// corrupt an existing checkpoint.

const CKPT_MAGIC: [u8; 4] = *b"DSCK";
const CKPT_VERSION: u32 = 1;

struct Resumed {
    state: State,
    snapshots: Vec<(usize, State)>,
    steps: usize,
    power: usize,
    lam: usize,
    max_value: u16,
}

fn checkpoint_load(
    path: &Path,
    expected_m: usize,
    _expected_max_length: usize,
    fac_table: &[u8],
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
            "{}: unsupported checkpoint version {}",
            path.display(),
            version
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
    let max_value = read_u16(&mut f)?;
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
    max_value: u16,
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

fn read_state<R: Read>(r: &mut R, m: usize, fac_table: &[u8]) -> Result<State, CheckpointError> {
    let head = read_u32(r)? as usize;
    if head >= m {
        return Err(CheckpointError(format!(
            "checkpoint head {} out of range for m={}",
            head, m
        )));
    }
    let hash = read_u64(r)?;
    let mut window = vec![0u16; m];
    for slot in window.iter_mut() {
        *slot = read_u16(r)?;
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
    Ok(State {
        window,
        div_counts,
        head,
        div_sum,
        hash,
        b_pow_m_minus_1,
    })
}

fn read_u16<R: Read>(r: &mut R) -> io::Result<u16> {
    let mut b = [0u8; 2];
    r.read_exact(&mut b)?;
    Ok(u16::from_le_bytes(b))
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

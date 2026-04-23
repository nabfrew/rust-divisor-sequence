# Video Essay Plan — *The Divisor Window*

A 3Blue1Brown-style narrative video essay built from the `rust-divisor-sequence` project. Curiosity-driven; intelligent viewers without formal math education.

## Context

> **Note (2026-06):** the standalone analysis documents this plan cites as
> data sources (`analysis/system_limits.md`, `mlnm_bound.md`,
> `cycle_value_tau_structure.md`, `fixed_points.md`, `sustained_ceiling.md`,
> `length_mp1_invariant.md`, ROADMAP.md, …) have been consolidated into
> `analysis/explore.ipynb`. Section mapping there: bounded orbits §1,
> m·ln m band §3, conservation law §4, K-invariant §5, fixed points §7,
> sustained ceiling §8, basin scans §11, open items §12. The CSV artefacts
> referenced below are unchanged; the old .md files remain in git history.

The project is a multi-month numerical exploration of the recurrence
`R(n,m) = τ(R(n−1,m)) + … + τ(R(n−m,m))` seeded with m ones, where τ is the divisor-count function. The sliding window of m values lives in a finite state space, so the sequence must eventually cycle — but *when*, *how high*, and *why those scales* are deep questions, and the project has accumulated a coherent answer chain (bounded-orbits proof → m·ln m anchor → conservation law → anti-correlation seesaw → fixed-point families → four-band ceiling). The data is gap-free in m∈[1..1549] (one short range pending), with a per-m cycle catalog, an attractor catalog (300 distinct value-sets), a random-seed basin scan, and ~9 plot cells in `analysis/explore.ipynb`.

The essay's job is to take a viewer who has never heard of any of this on a curiosity-driven walk through it: open with the rule, hit a wall (4m²), notice the *real* ceiling is much lower (m·ln m), discover *why* (a conservation law you can derive from bookkeeping), look inside a single cycle (the τ-anti-correlation seesaw), find genuine fixed points the system mostly hides from itself (8m for odd primes), then end honestly with what's still open.

The deliverable from this plan is a section-by-section narrative outline with Manim shot lists, identified data/reasoning gaps to address before recording, and pointers to existing artifacts to crib from.

## Top-level shape

- **Runtime: ~26 minutes**, eight sections plus cold open and outro.
- **Three-act split.** Act I (~7 min): meet the rule, hit the worst-case wall (sections 1–2). Act II (~12 min): build the m·ln m anchor and the conservation law (sections 3–5; centerpiece is §4). Act III (~7 min): fixed points, four-band scale separation, open mysteries (sections 6–8).
- **Voice & pacing.** Warm, present-tense, first-person plural. Defer formula reveals; show the visualization first. Name objects suggestively before defining them: *the wall*, *the anchor*, *the seesaw*, *the slack band*. Spend 90–120 s on each hard moment (divisor pairing in §2, conservation argument in §4); move faster through catalog/empirical sections. Allow genuine "we don't know" beats — they're the most 3B1B thing about it.

---

## Cold open (40 s)

A single number on screen: `1`. It splits into m copies of itself, forming a window. The window slides one cell right; a new term drops in. The numbers grow — 2, 3, 5, 4, 7, 4 — but never *much*. After a while the original window flickers back into existence in front of the live one. They line up. Audio swells, then drops.

> "Sliding windows of integers. Counting divisors. A rule so simple a child could simulate it. And yet — for the first 1,549 starting points, here's how long this little machine runs before it loops back on itself."

Cut to a log-log scatter of `repeat_after(m)` building point-by-point, the y-axis stretching to `10^10`. Pause.

> "The longest one we've measured takes four billion steps to repeat. Why?"

Title card: ***The Divisor Window***.

---

## Section 1 — A rule, and a window (3 min)

**Question.** What does this thing actually do?

**Beats.**
- Define τ from first principles: divisors of 12 are {1,2,3,4,6,12}, so τ(12) = 6. Animate divisors lighting up under a number line.
- Hand-walk **m=2**: window `[1,1] → 2 → 3 → 4 → 5 → 4 → 3 → 4 → 4 → ...` (tape runs across the bottom). Highlight when the window state recurs.
- Try **m=3**: max value 14, repeats at step 24. Try **m=8**: max 43, repeats at step 114. The pattern is clearly *something* but the shape isn't yet visible.
- Casually note: there are only finitely many possible windows, so something *has* to repeat — but that's a sloppy argument; we'll do it properly in the next section.

**Idea introduced.** The recurrence as a sliding-window finite-state machine.

**Manim shots.**
1. Number line 1..30 with divisors blooming under each integer; τ(n) tally appearing.
2. m=2 window stepping in real time; emitted-values tape forming below.
3. Side-by-side small-multiples panel running m∈{2,3,5,8}, each with its own running-max readout.
4. "Loop detected" moment: window flashes, colored arc connects the two identical states.

**Data sources.** `tests/reference.rs` for known small-m sequences; `results.csv` rows m=1..10 for repeat_after / max_value; `src/lib.rs::step` for the recurrence itself.

**Bridge.** "It must repeat eventually. But how big does it get *first*?"

---

## Section 2 — How big can it get? (3 min)

**Question.** Could the sequence run away to infinity?

**Beats.**
- Try to break it: initialize m=10 with a window of ten 1,000,000s. Watch the next term collapse to ~20,000.
- Why? τ grows *slowly*. Visually demonstrate **τ(x) ≤ 2√x** via divisor-pairing — every divisor above √x is matched to one below.
- One step emits at most `m · τ(M) ≤ 2m√M`. That's *less than M* whenever `M > 4m²`. Above the wall, the sequence *must* shrink.
- Conclusion: values are forever capped at 4m². Finite state space + deterministic rule → cycles are inevitable. (Pigeonhole, plain English: more pigeons than holes means a hole gets two pigeons.)

**Idea introduced.** The bounded-orbits theorem as the *fortress wall* at 4m².

**Manim shots.**
1. Animated divisor pairing: rectangle of width √x with mirrored pairs jumping above/below the diagonal.
2. "Adversarial" panel: huge initial window, watch it collapse.
3. Curves `y = 2m√M` and `y = M` crossing at `M = 4m²`; shade the upper region as forbidden for sustained growth.
4. Pigeonhole metaphor: window-states-as-pigeons in a finite grid; revisitation lights up.

**Data sources.** `analysis/system_limits.md` (canonical proof statement).

**Bridge.** "So 4m² is a wall. But look where the actual values *live*." Cut to scatter of `cycle_max(m)` vs m, sitting two orders of magnitude *below* 4m². "The system stops itself far earlier. Why?"

---

## Section 3 — Where the values actually live (3 min)

**Question.** If 4m² is wildly loose, what's the *real* ceiling?

**Beats.**
- Plot `cycle_max(m)` for all 1,549 m's. A tight ribbon, far below 4m².
- Sweep candidate fits: `y = m` (too low), `y = m^1.5` (too high), **`y = m · ln m`** (locks in).
- Show residuals: median 1.13 · m·ln m, p95 ≈ 1.32. Highlight: **cycle_min, cycle_max, and even max_value all scale as m·ln m**, just with different multipliers (1.13, 1.32, 2.13).
- Tease: m, ln m, and τ are all about *divisor density*. Something is forcing this.

**Idea introduced.** The empirical m·ln m anchor as a *phenomenon* — not yet explained.

**Manim shots.**
1. Live log-log scatter of `cycle_max` vs m; candidate curves swept in until m·ln m clicks.
2. Three nested ribbons (cycle band, transient peak, fortress wall) all on one log plot.
3. Residual histogram of `cycle_max / (m · ln m)` peaking sharply at 1.13.
4. Outliers (74 wide-band m's) flagged in red but deferred — "we'll come back to those."

**Data sources.** `results_new.csv` + `gaps.csv` (merged); `analysis/mlnm_bound.md` for empirical constants; cells §3–§4 of `analysis/explore.ipynb` for the existing log-log plots.

**Bridge.** "ln m is what you get when you ask: how many divisors does a typical number around m have, on average? Could the system itself be *averaging* something?"

**Reasoning to flesh out for §3.** Build "average τ near N is about ln N" with a histogram, not a formula. This is the only number-theory fact the viewer takes on faith — ground it visually. (The Hardy-Ramanujan / Dirichlet hyperbola theorem is overkill; the histogram suffices.)

---

## Section 4 — A conservation law nobody put in (4 min — *centerpiece*)

**Question.** Why m·ln m and not somewhere else?

**Beats.**
- Re-state the rule, slowly: each new term is the sum of the τ's of the previous m terms.
- The **bookkeeping trick.** In a full cycle of length λ, every τ(a_k) is consumed by exactly m different window-sums (the window has width m and slides past it m times). So summing all new terms over one full lap gives `m × Σ τ(a_k)`.
- But the new terms *are* the cycle values — over one lap, sum of new terms = sum of values. Therefore:
  > **Σ value = m · Σ τ(value)**, equivalently **mean v = m · mean τ**.
- This is *exact*. Verified bit-for-bit on all 1,449 resolved cycles; max error = 0.
- Combine with §3's "average τ near v ≈ ln v": plug v = mean value. **mean v ≈ m · ln(mean v)**. This is an equation pinning the cycle's location.
- Solve graphically — the curves `y = x` and `y = m · ln x` cross at exactly the place we observe. The anchor is forced by accounting.

**Idea introduced.** The exact conservation law and how, combined with the τ-density fact, it pins the cycle band.

**Manim shots.**
1. A length-λ cycle laid out as a circular ribbon; each value has a τ "shadow." A sweep highlights every window-sum, and as it laps the ring, color-coded counters show *each τ being consumed exactly m times*. Two columns sum at the bottom; equality "lights up."
2. Curves `y = x` and `y = m · ln x` for m=100; intersection point marked. Slide m up; intersection slides up the curve. Overlay empirical 1.13·m·ln m points across m sitting on the intersection.
3. A single cycle's values color-coded by whether their τ is above/below ln m — half above, half below.
4. Scatter of `mean τ over cycle` vs `ln m`, hugging the diagonal.

**Data sources.** `analysis/cycle_value_tau_structure.md`; per-m `analysis/cycle_signatures/<m>.csv` to compute the conservation law live; cell §7 of `explore.ipynb`.

**Bridge.** "Conservation says the cycle has to *balance* — high-τ values and low-τ values, averaged together, hit ln m. What does that look like *inside* a single cycle?"

**Reasoning to flesh out for §4.** The "each τ consumed by exactly m windows" combinatorial argument needs a slow concrete window-walk animation — the entire essay rests on this. Don't say "Lambert-W"; say "the curve where x equals m times log x." The whole story is graspable without algebra.

---

## Section 5 — Inside a cycle: the seesaw (3 min)

**Question.** What does a single cycle actually *look* like?

**Beats.**
- Pick a clean cycle (e.g. m=24, value set {180, 184, 186, 188, 190, 192, 194, 198, 202, 206}). Show values *and* their τ's side by side.
- Big values have small τ; small values have big τ. A *seesaw*.
- This isn't decoration, it's forced. If every τ exceeded ln m, conservation would pull the cycle up; if every τ < ln m, down. The cheapest balance is to *split*: a few highly-composite small entrants on one side, near-prime large exits on the other.
- Empirically: **60% of well-behaved cycles** show *perfect* monotonic anti-correlation (Spearman ρ = exactly −1).

**Idea introduced.** Anti-correlation as a forced consequence of conservation in a narrow band.

**Manim shots.**
1. The seesaw: cycle values plotted against τ; diagonal red line through the points; median ρ across all well-behaved cycles ≈ −1.
2. A cycle laid out as a ring of integers with τ underlined in matched color; emphasize a high-τ small value (180 = 2²·3²·5) vs. a near-prime large value (197).
3. Histogram of Spearman ρ across 1,225 well-behaved cycles, with the spike at −1.0.
4. "Population seesaw" metaphor: an actual lever; the constraint Σ value = m · Σ τ as the fulcrum.

**Data sources.** `analysis/cycle_value_tau_structure.md` (Spearman histogram; bucketed table); `analysis/cycle_signatures/24.csv`.

**Bridge.** "What about cases where the system *can't* find a seesaw shape?" Cut to a wide-band outlier scatter for the next section's hint.

---

## Section 6 — Fixed points: where the dance stops (3 min)

**Question.** What if the cycle is just *one* value, repeating forever?

**Beats.**
- Simplest cycle: a flat window of identical values x. For x to be a fixed point, `x = m · τ(x)`.
- Hunt for solutions. m=127 (prime), try x = 8m = 1,016. τ(1016) = τ(8)·τ(127) = 4·2 = 8. Check: 8·127 = 1,016. **Works.**
- This works for *every* odd prime m (multiplicativity of τ). So x = 8m is a fixed-point candidate for every odd prime.
- Surprise: only **8 primes in the first 1,549 actually land on it** from the all-1s seed: 127, 167, 211, 613, 733, 1,103, 1,117, 1,291.
- The other primes have it *available* — they just don't reach it. The basin is hidden.
- Briefly mention: 12m, 24m families are mathematically valid candidates but never observed.
- Show the hitting times: m=127 → 18,958 steps; m=613 → 14M steps; **m=1,291 → 4 billion steps**. Wildly nonlinear.

**Idea introduced.** Fixed points as Diophantine constraints — and the basin-of-attraction question as a separate, harder problem.

**Manim shots.**
1. Number-line zoom on m=127 with x=1,016 marked; flat window of ten 1,016's evolves into itself, forever.
2. Table of 8 primes that hit 8m, with their hitting times — and a `log(repeat_after) vs m` plot.
3. For non-resolving primes (e.g. m=433, 853): show the 8m candidate sitting unvisited at the right of their cycle band.
4. Random-seed basin scan: 50 starting windows for m=613 (most hit 8m); same for m=433 (zero hits).

**Data sources.** `analysis/fixed_points.md`, `analysis/fixed_points.csv`, `analysis/random_seed_basin.csv`.

**Bridge.** "Most starting points seem to drain into the same little cycle. But what about the gigantic state space the system never visits at all?"

---

## Section 7 — The four-band picture (3 min)

**Question.** How much room is the system *not* using?

**Beats.**
- Pull all the scales together for m=1,549:
  - Cycle band: ~1.13·m·ln m ≈ **12,500**
  - Transient peak: ~2.13·m·ln m ≈ **23,500**
  - Sustained ceiling `M*(m)` (largest value sustainable, defined as the largest M with `M ≤ m·τ(M)`): **277,200**, a highly composite number `2⁴·3²·5²·7·11`.
  - Fortress wall `4m²`: **9,597,604**, the worst-case proof bound — 35× looser than reality.
- Each scale roughly an order of magnitude above the last. Four beautifully separated bands.
- The **slack band** between the transient peak (~23K) and M*(m) (~277K) is **completely unvisited from seed=1**. An entire order of magnitude of sustainable state space, never touched.

**Idea introduced.** Multi-scale separation; the unvisited slack band as a real, measurable phenomenon.

**Manim shots.**
1. Four-band log plot for m=1,549: cycle_max, max_value, M*(m), 4m² as horizontal bars on a log scale, color-coded.
2. Animated trajectory tracing through the cycle, painting only the lower band; the upper region stays dark.
3. Highlight 277,200 = 2⁴·3²·5²·7·11 with prime factorization in glowing colors.
4. Cell §8 of `explore.ipynb` (the four-band figure) replicated and animated.

**Data sources.** `analysis/sustained_ceiling.md`, `analysis/sustained_ceiling.csv`, `analysis/system_limits.md`, cell §8 of `explore.ipynb`.

**Bridge.** "Maybe seed=1 is just one tour of one neighborhood. What does the system look like from somewhere else?"

---

## Section 8 — What we still don't understand (3 min — honest outro)

**Question.** What's actually mysterious here?

**Beats.**
- **The 8m basin question.** Every odd prime m has 8m as a structural fixed point, but in 1,549 m's, only 8 land on it. With 50 random seeds per prime, primes that don't already converge to 8m **never** find it. Is the basin vanishingly small, or is 8m simply unreachable for most primes? Open.
- **Cycle_length = m+1 resonance.** For 53% of m's, the cycle length is *exactly m+1*. No satisfying explanation yet.
- **The 74 wide-band outliers** (e.g. m∈{738–751, 1244–1254}). Best current theory: τ-spectrum events, where a procession of highly-composite numbers sliding through the window breaks the seesaw. Plausible, partially verified, not proved.
- **Basin multiplicity.** m=276 has 14 distinct attractors under random seeding (most m's have 1–3). Why this m and not its neighbors?
- **The slack band.** Above ~23K and below ~277K, sustainable but unvisited. Is there an attractor up there nobody has ever seeded into?

**Manim shots.**
1. Histogram of `cycle_length mod m`; spike at +1 highlighted, captioned *"no theory."*
2. Wide-band outlier panel: m=738..751 cycle ranges as horizontal bars; HCNs in their τ neighborhood marked beneath.
3. m=276's 14 attractors fanned out in a basin diagram.
4. Final frame: the four-band picture from §7, with question marks scattered through the slack region.

**Closing voiceover.**
> "We started with the simplest possible rule. Count divisors, sum, slide. From that, an exact conservation law forces the cycle to live at m·ln m. A near-perfect anti-correlation organizes the inside of every cycle. And there's a wall at 4m² nothing can ever cross. Seven sections in, the system is still hiding things. The fixed points it won't visit. The resonance at m+1 with no proof. The outliers we can describe but not yet explain. The empty room above the cycle. The data is open. If anything in here struck you as a question rather than an answer — go run it. The state space is finite. The mysteries aren't."

---

## Identified data gaps (fill before recording)

1. **m=1,350..1,399 scan gap.** ROADMAP §D.0 — currently unscanned. Cosmetic but matters if the cold open says "first 1,549 starting points." Either run the scan or rephrase to "across the m we've measured."
2. **Resonance audit (cycle_length = m+1).** ROADMAP §C.4 unstarted. The video will need to be honest: no derivation. Optionally do the §C.4 bucketing first so the histogram in §8 has more structure (residue classes mod m for cycle_length).
3. **Wide-band outliers — quantitative HCN test.** `analysis/explore.ipynb` §7 (§B.9) attributes 74 wide-band cycles to τ-spectrum events but no controlled test (e.g. seeding a normally-tight m's window with an HCN to check that the band breaks). This would let §8 promote the outlier story from speculation to demonstration.
4. **The 8m basin question — K=200 random-seed scan on multi-element primes.** Current §E.6 random-seed scan is K=50. To cleanly state in §8 "even with 200 seeds, primes m∈{433, 853, 1,069, ...} never reach 8m," extend the basin scan with the §E.6 ROADMAP item flagged for K=200 on the 50 multi-element primes.
5. **Lambert-W identification — pin the second step.** The argument `mean v = m · mean τ` (exact) + `mean τ ≈ ln(mean v)` (empirical, `explore.ipynb` §7 / §B.9 reports `mean τ / ln m ≈ 1.10`) → `mean v ≈ m · ln(mean v)` (the cycle band) is rigorous-then-empirical. Worth a clean visual showing the second step holds across all m at the 10% level (we have the numbers — just need the chart).
6. **HCN catalog as a one-shot script.** The visualization in §7 wants the prime factorizations of `M_at(m)` (the integer attaining `M*(m)`) for m∈{500, 1,000, 1,549}. Currently embedded in `analysis/sustained_ceiling.md` for a few m's; a small script dumping the factorization column to `analysis/sustained_ceiling.csv` would make §7's animation trivial.

## Reasoning to flesh out for a no-formal-math audience

- **τ as visual concept, not formula.** Rectangle-tiling: τ(12) = 6 because there are six rectangles with integer sides and area 12. This sets up multiplicativity-as-rectangles for §6's `τ(8m) = τ(8)·τ(m)`.
- **Average τ ≈ ln N as a histogram fact.** Don't prove the Dirichlet hyperbola; show 100,000 dots on a τ-vs-n scatter; draw the running average; watch it climb logarithmically. ~60 s of patient animation.
- **Lambert-W without naming it.** "The curve where x equals m·ln x." Two curves on a graph; find their crossing.
- **Conservation law as bookkeeping, not algebra.** The "every τ consumed by m window-sums in one full lap" argument is a counting argument. Animate the windows sliding; let the viewer *see* each value being touched m times.
- **Pigeonhole as a one-liner.** "More pigeons than holes — a hole gets two pigeons." Don't say the word; use the picture.
- **Spearman ρ as ranks.** "List values biggest-to-smallest; list τ's biggest-to-smallest. Do they appear in opposite orders? Most of the time, yes — perfectly opposite."
- **HCN as 'champion divisor counts.'** Show the staircase of record-holders: 1, 2, 4, 6, 12, 24, 36, 48, 60, 120, 240, 360, ...

## Critical artifacts to crib from

- `analysis/explore.ipynb` — 9 plot cells, fully executable. Sections §3, §4, §7, §8 can use these directly as Manim references.
- `analysis/cycle_value_tau_structure.md` — Spearman histograms, conservation-law verification (numbers for §4, §5).
- `analysis/fixed_points.md`, `analysis/fixed_points.csv` — the 8 odd primes for §6, hitting times.
- `analysis/sustained_ceiling.md`, `analysis/sustained_ceiling.csv` — M*(m) numbers for §7.
- `analysis/random_seed_basin.csv` — basin probe for §6 and §8.
- `analysis/cycle_signatures/<m>.csv` — per-m cycle data for live cycle visualizations (especially §4, §5).
- `analysis/system_limits.md` — clean statement of the bounded-orbits proof for §2.
- `tests/reference.rs` — small-m sequences for §1 hand-walks.

## Production sketch

- **Tooling.** Manim (community edition); Python data pipeline reading the CSVs above; a thin `data/` folder of pre-generated frame sequences for the long log-log plots.
- **Order of operations.** (1) Lock script for §§1–4 first — these are the load-bearing math. (2) Build the §4 conservation animation; everything later leans on it. (3) Storyboard §§6–8 last; they reuse most assets from §§1–5.
- **Sanity-check pass.** Once a draft script exists, run all the numerical claims back through the project: spot-check `cycle_max(m=1549)`, `M*(1549)`, the 8 primes, the conservation law on m=24, against the live `results_new.csv` and signatures. The CLAUDE.md `m=560..=572` diff is a good cheap correctness probe.

## Verification

- Each section's data references are reproducible from the existing CSVs without rerunning Rust scans.
- Gap-fill items §D.0 (m=1,350..1,399) and §E.6 K=200 are gated by Rust runs; they're nice-to-have, not blockers — the script can ship without them, with phrasing hedged accordingly.
- The conservation law (the §4 centerpiece) holds bit-exactly on all 1,449 cycles per `analysis/cycle_value_tau_structure.md`; no further verification needed for the math, only for the animation's correctness.

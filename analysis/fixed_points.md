# Fixed-point families (ROADMAP §C.1)

Source: results_new.csv, results_new_4.csv.
Observed n = 7 fixed-point m's (cycle_length == 1).

Each fixed point satisfies `d(x) = x/m`, equivalently
`τ(x) = q` where `q = x/m`.  By multiplicativity of τ, the
structural condition `τ(q·m) = q` constrains both q and the
prime-factor shape of m.

## Observed table

| m | prime | x | q=x/m | m fac | x fac | repeat_after |
|---:|:---:|---:|---:|:---|:---|---:|
| 1 | N | 1 | 1 | `1` | `1` | 2 |
| 127 | Y | 1016 | 8 | `127` | `2^3·127` | 18,958 |
| 167 | Y | 1336 | 8 | `167` | `2^3·167` | 34,532 |
| 211 | Y | 1688 | 8 | `211` | `2^3·211` | 979,783 |
| 613 | Y | 4904 | 8 | `613` | `2^3·613` | 14,143,541 |
| 733 | Y | 5864 | 8 | `733` | `2^3·733` | 52,900,083 |
| 1291 | Y | 10328 | 8 | `1291` | `2^3·1291` | 4,180,785,143 |

## Per-quotient algebraic condition

For each quotient `q`, the necessary condition is `τ(q·m) = q`.
Below: structural specialisations and whether the family is
observed in current data.

### q = 1  (observed, n=1)

τ(x) = q = 1 requires τ(1·m) = 1 where 1 = 1.

Observed m: [1].

### q = 3  (not observed, n=0)

τ(3m)=3 forces 3m to be a prime square (only τ(p²)=3). So 3m = p² ⇒ p=3 and m=3, giving x=9. **m=3 is the unique candidate**, and it is *not* observed (m=3 has cycle_length=4 in our data — the seed-1 trajectory misses x=9).

### q = 8  (observed, n=6)

8 = 2³ requires τ(8m)=8. For m = odd prime p: 8m = 2³·p, τ = 4·2 = 8. ✓  For m even or m = p·q (distinct odd primes), τ ≠ 8. So the family is: m an odd prime.

Observed m: [127, 167, 211, 613, 733, 1291].

### q = 12  (not observed, n=0)

12 = 2²·3 requires τ(12m)=12. For m = prime p > 3: 12m = 2²·3·p, τ = 3·2·2 = 12. ✓  Family: m a prime > 3. Not observed in current data — these primes apparently fall into another attractor first.

### q = 16  (not observed, n=0)

16 = 2⁴ requires τ(16m)=16. For m = odd prime p: 16m = 2⁴·p, τ = 5·2 = 10 ≠ 16. For m = p·q (distinct odd primes): 16m = 2⁴·p·q, τ = 5·2·2 = 20 ≠ 16. For m = p² (odd prime): 16m = 2⁴·p², τ = 5·3 = 15 ≠ 16. **No small-structure m supports the 16m family.**

### q = 24  (not observed, n=0)

24 = 2³·3 requires τ(24m)=24. For m = prime p > 3: 24m = 2³·3·p, τ = 4·2·2 = 16 ≠ 24. For m = p² (odd, p≠3): 24m = 2³·3·p², τ = 4·2·3 = 24. ✓  Family: m = p² for odd prime p ≠ 3. Smallest example: m=25 → x=600 (not observed: m=25 falls into a multi-element cycle in our data).

## Findings

1. **All non-trivial observed fixed points are `x = 8m` with
   `m` odd prime.** This confirms the human-notes hypothesis.
   No composite-m fixed point appears in m ≤ 1349.

2. **The 12m family is mathematically valid for any prime
   `m > 3`** but is empirically empty in our data — those
   primes evidently land in a multi-element attractor before
   reaching `x = 12m`. Worth re-checking in the long-tail
   m > 1500 run.

3. **The 16m family is structurally impossible for any small
   m-shape** (prime, prime², semiprime). So the observation
   in `human_notes.md` flagging 16m as a candidate is
   incorrect — there is no m with `τ(16m) = 16` and m of low
   prime complexity.

4. **The 24m family requires `m = p²` for odd prime `p ≠ 3`.**
   Smallest candidate `m = 25` is in the data but does *not*
   resolve to `x = 24·25 = 600` — it lands in a multi-element
   cycle. This mirrors the 12m absence: structural validity
   does not imply observation; the trajectory has to actually
   reach the fixed point.

## Open question

Per `human_notes.md`: *every* prime m may have a length-1
cycle, with some just getting stuck in a non-trivial loop
first. Confirming this would need basin-of-attraction sampling
(out of scope per ROADMAP), but a partial test is possible: 
for each prime m where the trial resolved to a multi-element
cycle, check whether `8m` lies in one of the catalogued
value-set clusters; if not, 8m is a separate basin the seed=1
trajectory missed.


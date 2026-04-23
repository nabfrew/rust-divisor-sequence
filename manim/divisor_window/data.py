"""Sequence + CSV helpers for the manim scenes.

Pure-Python; no manim imports here so this module can be exercised standalone:

    python -c "from manim.divisor_window.data import generate, find_first_repeat; \\
               print(generate(2, 12)); print(find_first_repeat(2, generate(2, 12)))"

Mirrors the recurrence in ``tests/reference.rs::generate_n``: window of m ints,
next term = sum of tau over the window, seed = ``[1] * m``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_CSV = REPO_ROOT / "results_new.csv"
GAPS_CSV = REPO_ROOT / "gaps.csv"


def tau(n: int) -> int:
    """Number of positive divisors of n. Trial division — fine for the scene-scale numbers (max ~43)."""
    if n < 1:
        raise ValueError(f"tau undefined for n={n}")
    count = 0
    i = 1
    while i * i <= n:
        if n % i == 0:
            count += 2 if i * i != n else 1
        i += 1
    return count


def divisors(n: int) -> list[int]:
    """Sorted list of positive divisors of n."""
    if n < 1:
        raise ValueError(f"divisors undefined for n={n}")
    small = []
    large = []
    i = 1
    while i * i <= n:
        if n % i == 0:
            small.append(i)
            if i * i != n:
                large.append(n // i)
        i += 1
    return small + large[::-1]


def generate(m: int, n_terms: int, seed: Optional[list[int]] = None) -> list[int]:
    """Generate the first ``n_terms`` of the sequence (including the seed).

    Default seed is ``[1] * m``. ``n_terms`` includes the m seed terms, so the
    returned list has length exactly ``n_terms`` (>= m).
    """
    if m < 1:
        raise ValueError(f"m must be >= 1, got {m}")
    if seed is None:
        seed = [1] * m
    if len(seed) != m:
        raise ValueError(f"seed length {len(seed)} != m {m}")
    if n_terms < m:
        raise ValueError(f"n_terms {n_terms} < m {m}")

    seq = list(seed)
    rolling_sum = sum(tau(v) for v in seed)
    while len(seq) < n_terms:
        next_val = rolling_sum
        seq.append(next_val)
        # Rolling update: subtract tau of the value leaving the window, add tau of the new term.
        leaving = seq[len(seq) - m - 1]
        rolling_sum += tau(next_val) - tau(leaving)
    return seq


@dataclass(frozen=True)
class Repeat:
    """A first window-repetition detected in a sequence.

    ``seq[mu : mu + m] == seq[k : k + m]``. The cycle is ``seq[m + mu : m + k]``
    (length ``lam``). ``repeat_after = k + m`` matches ``r()``'s convention.
    """

    mu: int
    k: int
    lam: int
    m: int

    @property
    def repeat_after(self) -> int:
        return self.k + self.m

    def cycle(self, seq: list[int]) -> list[int]:
        return list(seq[self.m + self.mu : self.m + self.k])


def find_first_repeat(m: int, seq: list[int]) -> Optional[Repeat]:
    """Return the first window repetition in ``seq``, or ``None`` if none exists.

    Mirrors ``tests/reference.rs::reference``: walk k from m upward, compare
    ``seq[k..k+m]`` against every earlier window.
    """
    if m < 1 or len(seq) < 2 * m:
        return None
    for k in range(m, len(seq) - m + 1):
        cur = seq[k : k + m]
        for j in range(k):
            if seq[j : j + m] == cur:
                return Repeat(mu=j, k=k, lam=k - j, m=m)
    return None


def load_results():
    """Return the merged ``results_new.csv`` + ``gaps.csv`` as a pandas DataFrame.

    Mirrors the merge in ``analysis/_build_explore_nb.py``. Imported lazily so
    that this module is usable without pandas (only the cold open touches it).
    """
    import pandas as pd

    results = pd.read_csv(RESULTS_CSV, skipinitialspace=True)
    results = results.rename(columns={"most common tail value": "most_common_tail_value"})
    if GAPS_CSV.exists():
        gaps = pd.read_csv(GAPS_CSV, skipinitialspace=True)
        combined = (
            pd.concat([results, gaps], ignore_index=True)
            .drop_duplicates(subset="m", keep="last")
            .sort_values("m")
            .reset_index(drop=True)
        )
    else:
        combined = results.sort_values("m").reset_index(drop=True)
    combined["m"] = combined["m"].astype(int)
    return combined


# ---------------------------------------------------------------------------
# Self-asserts: any sequence-generator drift fails fast, before manim launches.
# Numbers from tests/reference.rs::crosscheck_results_csv_small_m.

_SMALL_M_GROUND_TRUTH = [
    # (m, repeat_after, max_value)
    (1, 2, 1),
    (2, 9, 5),
    (3, 24, 14),
    (5, 35, 19),
    (8, 114, 43),
]


def _self_check() -> None:
    for m, expected_repeat, expected_max in _SMALL_M_GROUND_TRUTH:
        seq = generate(m, expected_repeat + 4 * m + 16)
        rep = find_first_repeat(m, seq)
        assert rep is not None, f"m={m}: no repeat found in {len(seq)} terms"
        assert rep.repeat_after == expected_repeat, (
            f"m={m}: repeat_after {rep.repeat_after} != expected {expected_repeat}"
        )
        observed_max = max(seq[: rep.repeat_after])
        assert observed_max == expected_max, (
            f"m={m}: max_value {observed_max} != expected {expected_max}"
        )


_self_check()

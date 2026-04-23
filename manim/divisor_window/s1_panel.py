"""Section 1, Shot 3 — small-multiples panel.

A 2x2 grid runs m ∈ {2, 3, 5, 8} simultaneously. Each panel steps in lockstep
with the others until its window-state first repeats; halted panels freeze
while the rest continue. Final frame: each panel's max value and the step at
which it cycled.

Render: manim -pqh manim/divisor_window/s1_panel.py S1Panel

Numbers are cross-checked against tests/reference.rs::crosscheck_results_csv_small_m
via the self-asserts in data.py — m ∈ {2, 3, 5, 8} → repeat_after ∈ {9, 24, 35, 114},
max_value ∈ {5, 14, 19, 43}.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from manim import (
    DOWN,
    FadeIn,
    Indicate,
    LEFT,
    RIGHT,
    Scene,
    Text,
    Transform,
    UP,
    VGroup,
    smooth,
)

if __package__ != "divisor_window":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "divisor_window"

from .data import find_first_repeat, generate
from .style import (
    ACCENT,
    EMITTED_TEXT,
    LOOP_HIGHLIGHT,
    TAU_BADGE,
    window_cell,
)


M_VALUES = [2, 3, 5, 8]
PANEL_GRID = [(0, 0), (0, 1), (1, 0), (1, 1)]  # row, col for each m
PANEL_W = 6.4
PANEL_H = 3.2
PANEL_CENTERS = {
    (0, 0): LEFT * (PANEL_W / 2 + 0.2) + UP * (PANEL_H / 2 + 0.2),
    (0, 1): RIGHT * (PANEL_W / 2 + 0.2) + UP * (PANEL_H / 2 + 0.2),
    (1, 0): LEFT * (PANEL_W / 2 + 0.2) + DOWN * (PANEL_H / 2 + 0.2),
    (1, 1): RIGHT * (PANEL_W / 2 + 0.2) + DOWN * (PANEL_H / 2 + 0.2),
}
PANEL_CELL_SIZE = 0.42

# Stepping pace. Lockstep across panels; m=8 needs 106 steps so we ramp.
INITIAL_PACE_STEPS = 6     # first N steps at human speed
INITIAL_PACE_RT = 0.55     # seconds per step early on
TIME_LAPSE_RT = 0.13       # seconds per step thereafter


@dataclass
class Panel:
    m: int
    seq: list[int]
    halt_step: int               # k from find_first_repeat: emissions to detect
    cells: VGroup = field(default_factory=VGroup)
    stats: Optional[Text] = None
    title: Optional[Text] = None
    halted: bool = False
    max_so_far: int = 1


class S1Panel(Scene):
    def construct(self) -> None:
        panels = self._build_panels()

        # Intro: all panels fade in; viewer reads the headers.
        self.play(
            *[FadeIn(p.title) for p in panels],
            *[FadeIn(p.cells, lag_ratio=0.05) for p in panels],
            *[FadeIn(p.stats) for p in panels],
            run_time=1.6,
        )
        self.wait(0.6)

        # Lockstep stepping. Track which panels still alive.
        max_halt = max(p.halt_step for p in panels)
        for t in range(1, max_halt + 1):
            anims = []
            halted_now: list[Panel] = []
            for p in panels:
                if p.halted:
                    continue
                anims.extend(self._step_panel(p, t))
                if t == p.halt_step:
                    p.halted = True
                    halted_now.append(p)
            run_time = INITIAL_PACE_RT if t <= INITIAL_PACE_STEPS else TIME_LAPSE_RT
            if anims:
                self.play(*anims, run_time=run_time, rate_func=smooth)
            for p in halted_now:
                self.play(Indicate(p.cells, color=LOOP_HIGHLIGHT, scale_factor=1.08), run_time=0.35)

        # Final beat — pulse every panel once more and lock the stats label in red.
        self.wait(0.4)
        for p in panels:
            final_stats = Text(
                f"m={p.m}: max {max(p.seq[: p.halt_step + p.m])}, repeated after {p.halt_step + p.m} terms",
                color=LOOP_HIGHLIGHT,
                weight="BOLD",
            ).scale(0.36)
            final_stats.move_to(p.stats.get_center()).align_to(p.stats, LEFT)
            self.play(Transform(p.stats, final_stats), run_time=0.4)
        self.wait(2.0)

    # ---- panel construction ------------------------------------------------

    def _build_panels(self) -> list[Panel]:
        panels: list[Panel] = []
        for m, (r, c) in zip(M_VALUES, PANEL_GRID):
            seq = generate(m, m + max(120, m * 4))
            rep = find_first_repeat(m, seq)
            assert rep is not None, f"m={m}: no repeat in {len(seq)} terms"
            halt_step = rep.k

            center = PANEL_CENTERS[(r, c)]

            title = Text(f"m = {m}", color=ACCENT, weight="BOLD").scale(0.55)
            title.move_to(center + UP * (PANEL_H / 2 - 0.4))

            row = VGroup(*[window_cell(v, size=PANEL_CELL_SIZE) for v in seq[:m]]).arrange(
                RIGHT, buff=0.0
            )
            row.move_to(center)

            stats = Text(
                f"max 1   step 0 / {halt_step}",
                color=EMITTED_TEXT,
            ).scale(0.36)
            stats.move_to(center + DOWN * (PANEL_H / 2 - 0.4))

            panels.append(
                Panel(
                    m=m,
                    seq=seq,
                    halt_step=halt_step,
                    cells=row,
                    stats=stats,
                    title=title,
                    max_so_far=max(seq[:m]),
                )
            )
        return panels

    # ---- per-step animation builders --------------------------------------

    def _step_panel(self, p: Panel, t: int) -> list:
        """Return the animations for advancing panel `p` by one step."""
        new_window = p.seq[t : t + p.m]
        new_cells = VGroup(*[window_cell(v, size=PANEL_CELL_SIZE) for v in new_window]).arrange(
            RIGHT, buff=0.0
        )
        new_cells.move_to(p.cells.get_center())

        p.max_so_far = max(p.max_so_far, *new_window)
        new_stats = Text(
            f"max {p.max_so_far}   step {t} / {p.halt_step}",
            color=EMITTED_TEXT if t < p.halt_step else TAU_BADGE,
        ).scale(0.36)
        new_stats.move_to(p.stats.get_center()).align_to(p.stats, LEFT)

        return [
            Transform(p.cells, new_cells),
            Transform(p.stats, new_stats),
        ]

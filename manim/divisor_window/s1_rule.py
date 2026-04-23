"""Section 1, Shot 1 — τ from divisors.

Renders ~45 s. A row of integers 1..15; for each focus integer n, the divisors
of n light up with a tick underneath, a counter increments, and the running
total τ(n) is displayed. Ends on a single-line definition.

Render: manim -pqh manim/divisor_window/s1_rule.py S1Rule
"""

from __future__ import annotations

from manim import (
    DOWN,
    FadeIn,
    FadeOut,
    Indicate,
    Line,
    LEFT,
    ORIGIN,
    RIGHT,
    Scene,
    Text,
    UP,
    VGroup,
    Write,
)

if __package__ != "divisor_window":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "divisor_window"

from .data import divisors
from .style import (
    ACCENT,
    DIVISOR_TICK,
    EMITTED_TEXT,
    TAU_BADGE,
    window_cell,
)


N_RANGE = range(1, 16)
EXAMPLES = [12, 7, 16, 1]
CELL = 0.55


class S1Rule(Scene):
    def construct(self) -> None:
        title = Text("How many divisors does a number have?", color=EMITTED_TEXT).scale(0.55)
        title.to_edge(UP, buff=0.5)
        self.play(FadeIn(title, shift=DOWN * 0.2))

        cells = VGroup(*[window_cell(n, size=CELL) for n in N_RANGE]).arrange(RIGHT, buff=0.07)
        cells.move_to(ORIGIN).shift(UP * 0.4)
        cell_by_n = {n: cells[i] for i, n in enumerate(N_RANGE)}
        self.play(FadeIn(cells, lag_ratio=0.05, run_time=1.5))

        for example in EXAMPLES:
            self._sweep_example(example, cell_by_n)

        self.wait(0.4)
        definition = Text(
            "τ(n) = how many positive integers divide n.",
            color=ACCENT,
            weight="BOLD",
        ).scale(0.6)
        definition.to_edge(DOWN, buff=0.8)
        self.play(Write(definition))
        self.wait(2.0)

    def _sweep_example(self, n: int, cell_by_n: dict[int, VGroup]) -> None:
        target_cell = cell_by_n[n]

        marker = Text(f"n = {n}", color=ACCENT).scale(0.45)
        marker.next_to(target_cell, UP, buff=0.4)
        self.play(FadeIn(marker, shift=DOWN * 0.1), Indicate(target_cell, color=ACCENT))

        counter = Text("τ = 0", color=TAU_BADGE).scale(0.55)
        counter.next_to(cell_by_n[max(N_RANGE)], RIGHT, buff=0.6)
        self.play(FadeIn(counter, shift=LEFT * 0.1))

        ticks = []
        divs = [d for d in divisors(n) if d in cell_by_n]
        for k, d in enumerate(divs, start=1):
            cell = cell_by_n[d]
            tick_top = cell.get_bottom()
            tick = Line(
                tick_top + DOWN * 0.05,
                tick_top + DOWN * 0.30,
                color=DIVISOR_TICK,
                stroke_width=4,
            )
            new_counter = Text(f"τ = {k}", color=TAU_BADGE).scale(0.55)
            new_counter.move_to(counter.get_center()).align_to(counter, LEFT)
            self.play(
                Indicate(cell, color=DIVISOR_TICK, scale_factor=1.18),
                FadeIn(tick, shift=DOWN * 0.1),
                counter.animate.become(new_counter),
                run_time=0.45,
            )
            ticks.append(tick)

        # Pause on the final tally before moving on.
        self.wait(0.6)

        # Tear-down for next example.
        self.play(
            FadeOut(marker),
            *[FadeOut(t) for t in ticks],
            FadeOut(counter),
            run_time=0.5,
        )

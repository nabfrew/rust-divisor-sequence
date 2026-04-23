"""Section 1, Shot 2 — m=2 hand-walk.

A two-cell window starts at [1, 1]; each step shows τ on each cell, the sum
formula, drops the new value onto the tape, and slides the window. Runs until
the cycle (5, 5, 4) is visibly settled.

Render: manim -pqh manim/divisor_window/s1_handwalk.py S1Handwalk

Note: VIDEO_ESSAY_PLAN.md's prose lists the m=2 sequence as
"...→ 4 → 3 → 4 → 4 →" which is incorrect. The actual sequence with
seed [1, 1] under R(n,m) = Σ τ is 1,1,2,3,4,5,5,4,5,5,4,... with cycle (5,5,4).
This scene drives off data.generate(2, ...), the single source of truth.
"""

from __future__ import annotations

from manim import (
    DOWN,
    FadeIn,
    FadeOut,
    Indicate,
    LEFT,
    ORIGIN,
    RIGHT,
    Scene,
    Text,
    Transform,
    UP,
    VGroup,
    Write,
    smooth,
)

if __package__ != "divisor_window":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "divisor_window"

from .data import generate, tau
from .style import (
    ACCENT,
    EMITTED_TEXT,
    LOOP_HIGHLIGHT,
    TAU_BADGE,
    emitted_tape_cell,
    window_cell,
)


M = 2
N_EMISSIONS = 10  # produces seq of length 12: 1,1,2,3,4,5,5,4,5,5,4,5


class S1Handwalk(Scene):
    def construct(self) -> None:
        seq = generate(M, M + N_EMISSIONS)

        title = Text(f"m = {M}: a window of two", color=EMITTED_TEXT).scale(0.55)
        title.to_edge(UP, buff=0.4)
        self.play(FadeIn(title, shift=DOWN * 0.1))

        # Window: two cells side-by-side, anchored above the tape.
        cells = VGroup(window_cell(seq[0]), window_cell(seq[1])).arrange(RIGHT, buff=0.0)
        cells.move_to(ORIGIN).shift(UP * 1.2)
        self.play(FadeIn(cells, scale=0.9))

        rule_label = Text(
            "Next term = τ(left) + τ(right)",
            color=ACCENT,
        ).scale(0.4)
        rule_label.next_to(cells, UP, buff=0.4)
        self.play(FadeIn(rule_label))

        # Tape lives below the window; cells appended left-to-right.
        tape_origin = ORIGIN + DOWN * 1.6
        tape = VGroup()
        tape.move_to(tape_origin)

        # Lay down the seed values onto the tape so the viewer sees the full history.
        for v in seq[:M]:
            seeded = emitted_tape_cell(v)
            seeded.move_to(self._next_tape_position(tape, tape_origin))
            tape.add(seeded)
            self.play(FadeIn(seeded, shift=UP * 0.15), run_time=0.35)

        for step in range(N_EMISSIONS):
            left_val = seq[step]
            right_val = seq[step + 1]
            new_val = seq[step + M]

            tau_l = tau(left_val)
            tau_r = tau(right_val)

            tau_left_lbl = Text(f"τ={tau_l}", color=TAU_BADGE).scale(0.4)
            tau_right_lbl = Text(f"τ={tau_r}", color=TAU_BADGE).scale(0.4)
            tau_left_lbl.next_to(cells[0], UP, buff=0.15)
            tau_right_lbl.next_to(cells[1], UP, buff=0.15)

            self.play(
                Indicate(cells[0], color=TAU_BADGE, scale_factor=1.1),
                Indicate(cells[1], color=TAU_BADGE, scale_factor=1.1),
                FadeIn(tau_left_lbl, shift=DOWN * 0.1),
                FadeIn(tau_right_lbl, shift=DOWN * 0.1),
                run_time=0.5,
            )

            formula = Text(
                f"τ({left_val}) + τ({right_val}) = {tau_l} + {tau_r} = {new_val}",
                color=ACCENT,
            ).scale(0.45)
            formula.next_to(cells, RIGHT, buff=0.6)
            self.play(Write(formula), run_time=0.6)
            self.wait(0.3)

            # Drop the new value onto the tape.
            new_cell = emitted_tape_cell(new_val)
            new_cell.move_to(self._next_tape_position(tape, tape_origin))
            self.play(
                FadeIn(new_cell, shift=UP * 0.4, rate_func=smooth),
                FadeOut(formula),
                FadeOut(tau_left_lbl),
                FadeOut(tau_right_lbl),
                run_time=0.4,
            )
            tape.add(new_cell)

            # Slide the window: left cell takes right cell's value, right cell takes new value.
            new_left = window_cell(right_val).move_to(cells[0].get_center())
            new_right = window_cell(new_val).move_to(cells[1].get_center())
            self.play(
                Transform(cells[0], new_left),
                Transform(cells[1], new_right),
                run_time=0.45,
            )

        # Highlight the cycle (5, 5, 4) repeating in the tape.
        cycle_start_in_seq = 4  # index of the first '4' that begins the matched window
        # The cycle values (5,5,4) appear at seq[6..9] then seq[9..12]. Highlight both runs.
        for start in (6, 9):
            highlight = VGroup(*tape[start : start + 3]).copy()
            highlight.set_stroke(LOOP_HIGHLIGHT, width=4, opacity=1.0)
            self.play(FadeIn(highlight, scale=1.05), run_time=0.4)
            self.wait(0.4)
            self.play(FadeOut(highlight), run_time=0.3)

        cycle_caption = Text(
            "The same three values keep cycling: 5, 5, 4.",
            color=LOOP_HIGHLIGHT,
        ).scale(0.5)
        cycle_caption.to_edge(DOWN, buff=0.4)
        self.play(Write(cycle_caption))
        self.wait(2.0)

    def _next_tape_position(self, tape: VGroup, origin) -> object:
        if len(tape) == 0:
            # First cell sits left of origin so future cells extend to the right and stay centered-ish.
            return origin + LEFT * 4.0
        last = tape[-1]
        return last.get_center() + RIGHT * (last.width + 0.08)

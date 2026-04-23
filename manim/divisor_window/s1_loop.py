"""Section 1, Shot 4 — the loop-detected flash.

Runs m=3 from seed until the first window-repeat. The detected matched window
is pulsed, an arc connects it back to its earlier twin, and a closing caption
foreshadows Section 2 ("…but how big could it have gotten first?").

m=3 is chosen over m=2 because its cycle (14, 12, 14, 14, length 4) is more
visually distinctive than m=2's (5, 5, 4).

Render: manim -pqh manim/divisor_window/s1_loop.py S1Loop
"""

from __future__ import annotations

from manim import (
    DOWN,
    CurvedArrow,
    FadeIn,
    FadeOut,
    Indicate,
    LEFT,
    ORIGIN,
    PI,
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

from .data import find_first_repeat, generate
from .style import (
    ACCENT,
    EMITTED_TEXT,
    LOOP_HIGHLIGHT,
    emitted_tape_cell,
    window_cell,
)


M = 3
TAPE_CELL = 0.42
WINDOW_CELL = 0.65
INITIAL_PACE_RT = 0.6
TIME_LAPSE_RT = 0.18
INITIAL_PACE_STEPS = 5


class S1Loop(Scene):
    def construct(self) -> None:
        seq = generate(M, M + 60)
        rep = find_first_repeat(M, seq)
        assert rep is not None and rep.m == M
        total_terms = rep.k + rep.m  # = repeat_after

        title = Text(
            f"m = {M}: when does the window come back to itself?",
            color=EMITTED_TEXT,
        ).scale(0.5)
        title.to_edge(UP, buff=0.4)
        self.play(FadeIn(title, shift=DOWN * 0.1))

        # Window cells live high; tape cells fill from the left edge.
        window = VGroup(*[window_cell(v, size=WINDOW_CELL) for v in seq[:M]]).arrange(
            RIGHT, buff=0.0
        )
        window.move_to(ORIGIN).shift(UP * 1.4)
        self.play(FadeIn(window, scale=0.9))

        # Pre-build the full tape and place each cell at its final position; we'll
        # FadeIn one at a time as the simulation progresses.
        tape_cells: list[VGroup] = []
        tape_origin = LEFT * 5.5 + DOWN * 1.0
        for i, v in enumerate(seq[:total_terms]):
            cell = emitted_tape_cell(v, size=TAPE_CELL)
            cell.move_to(tape_origin + RIGHT * i * (TAPE_CELL + 0.04))
            tape_cells.append(cell)

        # Drop the seed cells onto the tape immediately.
        self.play(
            *[FadeIn(c, shift=UP * 0.1) for c in tape_cells[:M]],
            run_time=0.6,
            lag_ratio=0.1,
        )

        # Step through every emission; pace fast after the first few.
        for t in range(1, rep.k + 1):
            new_window_vals = seq[t : t + M]
            new_window = VGroup(
                *[window_cell(v, size=WINDOW_CELL) for v in new_window_vals]
            ).arrange(RIGHT, buff=0.0)
            new_window.move_to(window.get_center())

            new_tape_idx = t + M - 1
            run_time = INITIAL_PACE_RT if t <= INITIAL_PACE_STEPS else TIME_LAPSE_RT
            self.play(
                Transform(window, new_window),
                FadeIn(tape_cells[new_tape_idx], shift=UP * 0.15),
                run_time=run_time,
                rate_func=smooth,
            )

        # Cycle detected — pulse both the matched-earlier window and the current window.
        earlier = VGroup(*tape_cells[rep.mu : rep.mu + M])
        current = VGroup(*tape_cells[rep.k : rep.k + M])

        for grp in (earlier, current):
            grp.set_stroke(LOOP_HIGHLIGHT, width=4, opacity=1.0)

        self.play(
            Indicate(earlier, color=LOOP_HIGHLIGHT, scale_factor=1.15),
            Indicate(current, color=LOOP_HIGHLIGHT, scale_factor=1.15),
            run_time=0.7,
        )

        # Connecting arc: earlier-window center → current-window center, drawn beneath the tape.
        arc = CurvedArrow(
            earlier.get_bottom() + DOWN * 0.05,
            current.get_bottom() + DOWN * 0.05,
            color=LOOP_HIGHLIGHT,
            angle=-PI / 2.5,
        )
        arc.set_stroke(width=4)
        self.play(FadeIn(arc, shift=DOWN * 0.05), run_time=0.8)

        caption = Text(
            "Same three numbers, in the same order — everything from here on is a repeat.",
            color=LOOP_HIGHLIGHT,
        ).scale(0.42)
        caption.next_to(arc, DOWN, buff=0.4)
        self.play(Write(caption), run_time=1.1)
        self.wait(1.5)

        # Foreshadow §2.
        followup = Text(
            "…but how big could it have gotten first?",
            color=ACCENT,
        ).scale(0.5)
        followup.to_edge(DOWN, buff=0.4)
        self.play(
            FadeOut(caption, shift=DOWN * 0.2),
            FadeIn(followup, shift=UP * 0.1),
        )
        self.wait(2.0)

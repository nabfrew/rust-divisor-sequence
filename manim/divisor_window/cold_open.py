"""Cold open — 40 s.

Beats:
  0:00–0:04   Big "1" → ten small window cells (m = 10).
  0:04–0:14   Window slides; first 14 emissions at human pace.
  0:14–0:28   Time-lapse to step 231; the matched window flickers back.
  0:28–0:33   Voice-over text.
  0:33–0:40   Log-log scatter of repeat_after(m); title card.

Render: manim -pqh manim/divisor_window/cold_open.py ColdOpen

m = 10 reference numbers (verified live):
  first emissions: 10, 13, 14, 17, 18, 23, 24, 31, 32, 37, 38, 38, 40, 44, …
  first repeat:    mu = 46, k = 231, repeat_after = 241
  matched window:  [70, 66, 68, 70, 74, 70, 70, 70, 74, 70]
"""

from __future__ import annotations

import math

from manim import (
    Axes,
    CurvedArrow,
    DOWN,
    Dot,
    FadeIn,
    FadeOut,
    Indicate,
    LaggedStart,
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

from .data import find_first_repeat, generate, load_results
from .style import (
    ACCENT,
    EMITTED_TEXT,
    LOOP_HIGHLIGHT,
    WINDOW_TEXT,
    window_cell,
)


M = 10
WINDOW_CELL_SIZE = 0.55
HUMAN_PACE_STEPS = 14
TIME_LAPSE_END_STEP = 231  # = rep.k for m=10


class ColdOpen(Scene):
    def construct(self) -> None:
        seq = generate(M, M + TIME_LAPSE_END_STEP + 1)
        rep = find_first_repeat(M, seq)
        assert rep is not None, "m=10 must produce a repeat in 240 emissions"
        assert (rep.mu, rep.k) == (46, 231), (
            f"sanity: expected (mu, k) = (46, 231) for m=10, got {(rep.mu, rep.k)}"
        )

        self._beat_one_to_window(seq)
        window = self._fade_in_initial_window(seq)
        self._beat_human_pace(window, seq)
        self._beat_time_lapse_and_match(window, seq, rep)
        self._beat_voiceover()
        self._beat_scatter_and_title()

    # --- 0:00–0:04 ----------------------------------------------------------

    def _beat_one_to_window(self, seq: list[int]) -> None:
        big_one = Text("1", color=WINDOW_TEXT, weight="BOLD").scale(4.0)
        big_one.move_to(ORIGIN)
        self.play(FadeIn(big_one, scale=0.7), run_time=1.2)
        self.wait(0.4)

        # Transform the single "1" into a row of m=10 cells, all containing 1.
        target_row = VGroup(*[window_cell(1, size=WINDOW_CELL_SIZE) for _ in range(M)])
        target_row.arrange(RIGHT, buff=0.0)
        target_row.move_to(ORIGIN)
        self.play(Transform(big_one, target_row), run_time=1.6)
        # After Transform, `big_one` carries `target_row`'s submobject structure;
        # treat it as the window going forward.
        self._window = big_one

    def _fade_in_initial_window(self, seq: list[int]) -> VGroup:
        return self._window

    # --- 0:04–0:14 ----------------------------------------------------------

    def _beat_human_pace(self, window: VGroup, seq: list[int]) -> None:
        step_counter = Text("step 0", color=EMITTED_TEXT).scale(0.45)
        step_counter.to_edge(DOWN, buff=0.6)
        self.play(FadeIn(step_counter))

        for t in range(1, HUMAN_PACE_STEPS + 1):
            new_vals = seq[t : t + M]
            new_window = VGroup(
                *[window_cell(v, size=WINDOW_CELL_SIZE) for v in new_vals]
            ).arrange(RIGHT, buff=0.0)
            new_window.move_to(window.get_center())

            new_counter = Text(f"step {t}", color=EMITTED_TEXT).scale(0.45)
            new_counter.move_to(step_counter.get_center())

            self.play(
                Transform(window, new_window),
                Transform(step_counter, new_counter),
                run_time=0.65,
                rate_func=smooth,
            )
        self._step_counter = step_counter

    # --- 0:14–0:28 ----------------------------------------------------------

    def _beat_time_lapse_and_match(self, window: VGroup, seq: list[int], rep) -> None:
        """Jump from step ~14 to step 231 with a brief flicker, then reveal the matched window."""

        # Quick flicker: render every 8th step at very fast pace, conveying the passage of time.
        flicker_steps = list(range(HUMAN_PACE_STEPS + 1, TIME_LAPSE_END_STEP + 1, 8))
        for t in flicker_steps:
            new_vals = seq[t : t + M]
            new_window = VGroup(
                *[window_cell(v, size=WINDOW_CELL_SIZE) for v in new_vals]
            ).arrange(RIGHT, buff=0.0)
            new_window.move_to(window.get_center())

            new_counter = Text(f"step {t}", color=EMITTED_TEXT).scale(0.45)
            new_counter.move_to(self._step_counter.get_center())

            self.play(
                Transform(window, new_window),
                Transform(self._step_counter, new_counter),
                run_time=0.13,
            )

        # Ensure the final window equals seq[k..k+m] (the matched current window).
        final_vals = seq[rep.k : rep.k + rep.m]
        final_window = VGroup(
            *[window_cell(v, size=WINDOW_CELL_SIZE) for v in final_vals]
        ).arrange(RIGHT, buff=0.0)
        final_window.move_to(window.get_center())
        final_counter = Text(f"step {rep.k}", color=EMITTED_TEXT).scale(0.45)
        final_counter.move_to(self._step_counter.get_center())
        self.play(
            Transform(window, final_window),
            Transform(self._step_counter, final_counter),
            run_time=0.4,
        )
        self.wait(0.3)

        # Show the earlier-matched window above the current one and pulse both.
        earlier_label = Text(f"step {rep.mu}", color=LOOP_HIGHLIGHT).scale(0.4)
        earlier_label.next_to(window, UP, buff=1.4).align_to(window, LEFT)
        earlier_window = VGroup(
            *[window_cell(v, size=WINDOW_CELL_SIZE) for v in seq[rep.mu : rep.mu + rep.m]]
        ).arrange(RIGHT, buff=0.0)
        earlier_window.next_to(earlier_label, RIGHT, buff=0.4)

        self.play(
            FadeIn(earlier_label, shift=DOWN * 0.1),
            FadeIn(earlier_window, shift=DOWN * 0.1),
            run_time=0.7,
        )

        arc = CurvedArrow(
            earlier_window.get_bottom() + DOWN * 0.05,
            window.get_top() + UP * 0.05,
            color=LOOP_HIGHLIGHT,
            angle=-PI / 4,
        )
        arc.set_stroke(width=4)

        self.play(
            Indicate(earlier_window, color=LOOP_HIGHLIGHT, scale_factor=1.1),
            Indicate(window, color=LOOP_HIGHLIGHT, scale_factor=1.1),
            FadeIn(arc, shift=DOWN * 0.05),
            run_time=1.0,
        )
        self.wait(0.6)

        # Tear everything down for the next beat.
        self.play(
            FadeOut(earlier_label),
            FadeOut(earlier_window),
            FadeOut(arc),
            FadeOut(window),
            FadeOut(self._step_counter),
            run_time=0.6,
        )

    # --- 0:28–0:33 ----------------------------------------------------------

    def _beat_voiceover(self) -> None:
        line1 = Text("Sliding windows of integers.", color=WINDOW_TEXT).scale(0.7)
        line2 = Text("Counting divisors.", color=ACCENT).scale(0.7)
        line3 = Text("A rule a child could simulate.", color=EMITTED_TEXT).scale(0.6)
        lines = VGroup(line1, line2, line3).arrange(DOWN, buff=0.4)
        lines.move_to(ORIGIN)
        self.play(Write(line1), run_time=0.7)
        self.play(Write(line2), run_time=0.7)
        self.play(Write(line3), run_time=0.7)
        self.wait(1.2)
        self.play(FadeOut(lines), run_time=0.5)

    # --- 0:33–0:40 ----------------------------------------------------------

    def _beat_scatter_and_title(self) -> None:
        df = load_results()
        df = df.dropna(subset=["repeat_after"]).copy()
        df["log_m"] = df["m"].apply(lambda v: math.log10(max(v, 1)))
        df["log_r"] = df["repeat_after"].apply(lambda v: math.log10(max(v, 1)))

        max_log_m = max(3.3, df["log_m"].max() + 0.2)
        max_log_r = max(10.5, df["log_r"].max() + 0.5)

        ax = Axes(
            x_range=[0, max_log_m, 1],
            y_range=[0, max_log_r, 2],
            x_length=10,
            y_length=4.5,
            axis_config={"include_tip": False, "stroke_color": EMITTED_TEXT},
        )
        ax.move_to(ORIGIN).shift(DOWN * 0.4)

        x_label = Text("log₁₀ m", color=EMITTED_TEXT).scale(0.45)
        y_label = Text("log₁₀ steps to repeat", color=EMITTED_TEXT).scale(0.45)
        x_label.next_to(ax.x_axis, DOWN, buff=0.3)
        y_label.next_to(ax.y_axis, LEFT, buff=0.3).rotate(PI / 2)

        self.play(FadeIn(ax), FadeIn(x_label), FadeIn(y_label), run_time=0.8)

        dots = VGroup()
        for _, row in df.iterrows():
            dot = Dot(
                ax.coords_to_point(row["log_m"], row["log_r"]),
                radius=0.025,
                color=ACCENT,
            )
            dots.add(dot)

        # LaggedStart over the whole population for a build-on effect.
        self.play(
            LaggedStart(*[FadeIn(d, scale=0.4) for d in dots], lag_ratio=0.0015),
            run_time=3.0,
        )

        title = Text("The Divisor Window", color=WINDOW_TEXT, weight="BOLD").scale(1.1)
        title.move_to(ORIGIN).shift(UP * 0.2)

        self.play(
            ax.animate.set_opacity(0.25),
            x_label.animate.set_opacity(0.25),
            y_label.animate.set_opacity(0.25),
            dots.animate.set_opacity(0.25),
            FadeIn(title, scale=0.95),
            run_time=1.0,
        )
        self.wait(1.5)

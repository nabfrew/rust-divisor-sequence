"""Shared colors + reusable mobjects for the Divisor Window scenes."""

from __future__ import annotations

from manim import (
    BLACK,
    RIGHT,
    WHITE,
    Mobject,
    RoundedRectangle,
    Text,
    VGroup,
)


WINDOW_FILL = "#1f3a5f"
WINDOW_STROKE = "#7fb0e6"
WINDOW_TEXT = WHITE

EMITTED_FILL = "#2c2c2c"
EMITTED_STROKE = "#666666"
EMITTED_TEXT = "#cccccc"

TAU_BADGE = "#ffd166"
TAU_BADGE_BG = "#33270d"

LOOP_HIGHLIGHT = "#ef476f"
ACCENT = "#06d6a0"
DIVISOR_TICK = "#06d6a0"

CELL_SIZE = 0.9
CELL_CORNER_RADIUS = 0.12


def window_cell(value: int, size: float = CELL_SIZE) -> VGroup:
    """A rounded-square window cell containing an integer."""
    box = RoundedRectangle(
        corner_radius=CELL_CORNER_RADIUS,
        width=size,
        height=size,
        stroke_color=WINDOW_STROKE,
        stroke_width=2.5,
        fill_color=WINDOW_FILL,
        fill_opacity=1.0,
    )
    label = Text(str(value), color=WINDOW_TEXT, weight="BOLD").scale(0.45 * size)
    label.move_to(box.get_center())
    return VGroup(box, label)


def emitted_tape_cell(value: int, size: float = CELL_SIZE * 0.7) -> VGroup:
    """A smaller, dimmer cell for the emitted-values tape."""
    box = RoundedRectangle(
        corner_radius=CELL_CORNER_RADIUS * 0.7,
        width=size,
        height=size,
        stroke_color=EMITTED_STROKE,
        stroke_width=1.5,
        fill_color=EMITTED_FILL,
        fill_opacity=0.7,
    )
    label = Text(str(value), color=EMITTED_TEXT).scale(0.4 * size)
    label.move_to(box.get_center())
    return VGroup(box, label)


def tau_badge(value: int, size: float = 0.45) -> VGroup:
    """Small badge displaying τ=<count> — pinned above a window cell."""
    text = Text(f"τ={value}", color=TAU_BADGE).scale(size)
    bg = RoundedRectangle(
        corner_radius=0.08,
        width=text.width + 0.2,
        height=text.height + 0.12,
        stroke_width=0,
        fill_color=TAU_BADGE_BG,
        fill_opacity=0.85,
    )
    bg.move_to(text.get_center())
    return VGroup(bg, text)


def window_row(values: list[int], size: float = CELL_SIZE, gap: float = 0.0) -> VGroup:
    """Horizontal row of window cells, no buffer by default (cells touching)."""
    cells = [window_cell(v, size=size) for v in values]
    row = VGroup(*cells)
    row.arrange(RIGHT, buff=gap)
    return row


def tape_row(values: list[int], size: float = CELL_SIZE * 0.7, gap: float = 0.05) -> VGroup:
    """Horizontal tape of emitted-value cells."""
    if not values:
        return VGroup()
    cells = [emitted_tape_cell(v, size=size) for v in values]
    row = VGroup(*cells)
    row.arrange(RIGHT, buff=gap)
    return row


def fade_to_white(mob: Mobject, opacity: float = 0.4) -> Mobject:
    """Visual flag for transient emphasis — return mob with overlay color."""
    mob.set_color(WHITE)
    mob.set_fill(opacity=opacity)
    return mob


__all__ = [
    "WINDOW_FILL",
    "WINDOW_STROKE",
    "WINDOW_TEXT",
    "EMITTED_FILL",
    "EMITTED_STROKE",
    "EMITTED_TEXT",
    "TAU_BADGE",
    "TAU_BADGE_BG",
    "LOOP_HIGHLIGHT",
    "ACCENT",
    "DIVISOR_TICK",
    "CELL_SIZE",
    "CELL_CORNER_RADIUS",
    "BLACK",
    "WHITE",
    "window_cell",
    "emitted_tape_cell",
    "tau_badge",
    "window_row",
    "tape_row",
    "fade_to_white",
]

# Manim animations — *The Divisor Window*

Manim Community Edition scenes for the cold open and Section 1 of the video
essay. See `../VIDEO_ESSAY_PLAN.md` for the script.

## Install

```bash
python -m pip install -r manim/requirements.txt
```

Manim CE additionally needs system-level **ffmpeg** and (only if you render
`Tex`/`MathTex` mobjects) a TeX distribution. On Windows: install ffmpeg via
`winget install Gyan.FFmpeg`, and MikTeX from <https://miktex.org/download> if
you hit a TeX-related render error. The scenes here lean on `Text` for
captions to keep the LaTeX dependency optional, but the τ formula in the
hand-walk uses `MathTex`.

## Render a scene

From the repo root:

```bash
manim -pqh manim/divisor_window/cold_open.py ColdOpen
manim -pqh manim/divisor_window/s1_rule.py S1Rule
manim -pqh manim/divisor_window/s1_handwalk.py S1Handwalk
manim -pqh manim/divisor_window/s1_panel.py S1Panel
manim -pqh manim/divisor_window/s1_loop.py S1Loop
```

Quality flags:

| Flag | Resolution | Use for |
| --- | --- | --- |
| `-ql` | 480p15 | iteration / preview |
| `-pqh` | 1080p60 | final delivery |
| `-qk` | 4K60 | archival master |

`-p` opens the result in your default video player when rendering finishes.
Add `--disable_caching` while iterating on a scene if cache invalidation
misbehaves.

Outputs land in `manim/media/` (gitignored).

## Data sources

`divisor_window/data.py` reads:

- `results_new.csv` and `gaps.csv` (cold-open log-log scatter)

If you move those files, update the `RESULTS_CSV` / `GAPS_CSV` paths at the
top of `data.py`. Sequence terms for the small-m hand-walks are computed in
Python; nothing else is read from disk.

## Layout

```
manim/divisor_window/
  data.py        — sequence generator + CSV loader, with self-asserts
  style.py       — colors and reusable mobjects (window cell, τ badge, tape)
  cold_open.py   — ColdOpen
  s1_rule.py     — S1Rule (τ from divisors)
  s1_handwalk.py — S1Handwalk (m=2 step-by-step)
  s1_panel.py    — S1Panel (m∈{2,3,5,8} grid)
  s1_loop.py     — S1Loop (cycle-detected flash)
```

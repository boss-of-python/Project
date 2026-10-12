"""THANS UI toolkit (tkinter) — theme, animation helpers and custom widgets.

The desktop UI is built from these pieces so the whole look (colours, radii,
motion, typography) is defined in exactly one place:

    theme.py    design tokens + colour maths + font/symbol resolution
    logic.py    pure-Python UI logic (easing, layout, suggestions) — no tkinter
    widgets.py  canvas-drawn widgets (rounded bubbles, switches, toasts…)
"""
from . import logic, theme  # noqa: F401

__all__ = ["logic", "theme"]

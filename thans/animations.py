"""Animation math, easing functions, color interpolation, and sonic wave geometry.

Pure-Python, zero GUI dependencies — shared by both the Desktop (tkinter)
and Android (Kivy) front-ends, and 100% unit-testable headlessly.
"""
from __future__ import annotations

import math
from typing import Any

# --------------------------------------------------------------------------
# Curated Minimalistic Design System (Dark & Light Themes)
# --------------------------------------------------------------------------

THEMES: dict[str, dict[str, str]] = {
    "dark": {
        "bg": "#0d0f14",           # Deep obsidian canvas
        "panel": "#13161f",        # Primary surface card
        "panel2": "#1a1e2b",       # Elevated control / input surface
        "panel_hover": "#232838",  # Hover / active surface
        "border": "#222736",       # Subtle hairline border
        "fg": "#eef0f6",           # Crisp primary text
        "fg_secondary": "#b4bcd0", # Secondary body text
        "dim": "#6e778c",          # Muted labels & hints
        "accent": "#5b8af5",       # Electric indigo accent
        "accent_hover": "#4776e6", # Accent active state
        "accent_soft": "#19233d",  # Soft accent pill background
        "ok": "#10b981",           # Emerald green
        "ok_soft": "#112a24",      # Emerald highlight surface
        "warn": "#f59e0b",         # Amber warning
        "warn_soft": "#2d2212",    # Amber soft surface
        "err": "#f43f5e",          # Coral rose alert
        "err_soft": "#311620",     # Coral soft surface
        "user_msg": "#7aa2ff",     # User chat accent
        "asst_msg": "#c3ccff",     # Assistant chat accent
        "cmd_pill": "#8b95b0",     # Command trace pill
    },
    "light": {
        "bg": "#f4f6fb",           # Crisp alabaster canvas
        "panel": "#ffffff",        # Pure white card surface
        "panel2": "#edf0f7",       # Subtle control / input surface
        "panel_hover": "#e2e7f2",  # Hover / active surface
        "border": "#d8dfec",       # Hairline border
        "fg": "#141824",           # Deep ink primary text
        "fg_secondary": "#3b4254", # Secondary body text
        "dim": "#6c7489",          # Muted labels & hints
        "accent": "#3b6ff5",       # Vibrant cobalt accent
        "accent_hover": "#295be0", # Accent active state
        "accent_soft": "#e6eeff",  # Soft accent pill background
        "ok": "#059669",           # Emerald green
        "ok_soft": "#d1fae5",      # Emerald highlight surface
        "warn": "#d97706",         # Amber warning
        "warn_soft": "#fef3c7",    # Amber soft surface
        "err": "#e11d48",          # Rose alert
        "err_soft": "#ffe4e6",     # Rose soft surface
        "user_msg": "#2557d6",     # User chat accent
        "asst_msg": "#343d52",     # Assistant chat accent
        "cmd_pill": "#5a637a",     # Command trace pill
    },
}

STATE_COLORS: dict[str, tuple[str, str, str]] = {
    # state -> (primary_hex, secondary_hex, tertiary_hex)
    "idle": ("#5b8af5", "#818cf8", "#38bdf8"),
    "listening": ("#f43f5e", "#fb7185", "#06b6d4"),
    "thinking": ("#a855f7", "#6366f1", "#ec4899"),
    "speaking": ("#06b6d4", "#3b82f6", "#34d399"),
    "success": ("#10b981", "#34d399", "#3b82f6"),
    "error": ("#f43f5e", "#f97316", "#ef4444"),
}


def get_theme(name: str = "dark") -> dict[str, str]:
    """Return theme dictionary for 'dark' or 'light'."""
    return dict(THEMES.get(name, THEMES["dark"]))


# --------------------------------------------------------------------------
# Color conversion & interpolation
# --------------------------------------------------------------------------

def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert '#rrggbb' or '#rgb' to (r, g, b) ints in 0..255."""
    h = (hex_color or "#000000").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return (0, 0, 0)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return (0, 0, 0)


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Convert (r, g, b) ints in 0..255 to '#rrggbb'."""
    r = max(0, min(255, int(round(r))))
    g = max(0, min(255, int(round(g))))
    b = max(0, min(255, int(round(b))))
    return f"#{r:02x}{g:02x}{b:02x}"


def hex_to_rgba(hex_color: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    """Convert '#rrggbb' to Kivy-ready normalized (r, g, b, a) floats in 0..1."""
    r, g, b = hex_to_rgb(hex_color)
    a = max(0.0, min(1.0, float(alpha)))
    return (round(r / 255.0, 4), round(g / 255.0, 4), round(b / 255.0, 4), a)


def lerp_color(hex_a: str, hex_b: str, t: float) -> str:
    """Linearly interpolate between two hex colors at t in [0.0, 1.0]."""
    t = max(0.0, min(1.0, float(t)))
    r1, g1, b1 = hex_to_rgb(hex_a)
    r2, g2, b2 = hex_to_rgb(hex_b)
    return rgb_to_hex(
        int(r1 + (r2 - r1) * t),
        int(g1 + (g2 - g1) * t),
        int(b1 + (b2 - b1) * t),
    )


def lerp_rgba(
    c1: tuple[float, float, float, float],
    c2: tuple[float, float, float, float],
    t: float,
) -> tuple[float, float, float, float]:
    """Linearly interpolate between two Kivy RGBA tuples at t in [0.0, 1.0]."""
    t = max(0.0, min(1.0, float(t)))
    return (
        round(c1[0] + (c2[0] - c1[0]) * t, 4),
        round(c1[1] + (c2[1] - c1[1]) * t, 4),
        round(c1[2] + (c2[2] - c1[2]) * t, 4),
        round(c1[3] + (c2[3] - c1[3]) * t, 4),
    )


# --------------------------------------------------------------------------
# Easing & Pulse Curves
# --------------------------------------------------------------------------

def ease_out_cubic(t: float) -> float:
    """Smooth deceleration curve for slide-in and reveal transitions."""
    t = max(0.0, min(1.0, float(t)))
    return 1.0 - pow(1.0 - t, 3)


def ease_in_out_sine(t: float) -> float:
    """Symmetric sinusoidal easing for breathing and theme cross-fades."""
    t = max(0.0, min(1.0, float(t)))
    return -(math.cos(math.pi * t) - 1.0) / 2.0


def pulse_intensity(step: int, total_steps: int = 20) -> float:
    """Compute highlight intensity [0.0..1.0] that quickly rises then smoothly decays."""
    if total_steps <= 0 or step < 0 or step >= total_steps:
        return 0.0
    progress = step / float(total_steps)
    if progress < 0.15:
        return ease_out_cubic(progress / 0.15)
    decay = (progress - 0.15) / 0.85
    return max(0.0, math.cos(decay * math.pi * 0.5) ** 1.6)


# --------------------------------------------------------------------------
# 60fps Sonic Orb & Multi-Ribbon Waveform Generator
# --------------------------------------------------------------------------

def compute_sonic_waves(
    width: float,
    height: float,
    phase: float,
    state: str = "idle",
    level: float = 0.0,
    num_ribbons: int = 3,
    points: int = 44,
) -> dict[str, Any]:
    """Generate smooth multi-ribbon sine wave coordinates and glowing orb geometry.

    Returns a dict with:
      * ``ribbons``: list of ``{"coords": [x0, y0, x1, y1, ...], "color": "#...", "width": float}``
      * ``orb``: ``{"cx": float, "cy": float, "r": float, "glow_r": float, "color": "#..."}``
      * ``state_colors``: ``(c1, c2, c3)``
    """
    w = max(40.0, float(width))
    h = max(16.0, float(height))
    cy = h / 2.0
    lvl = max(0.0, min(1.0, float(level)))
    colors = STATE_COLORS.get(state, STATE_COLORS["idle"])

    # State-dependent wave energy & speed multiplier
    if state == "listening":
        base_amp = h * (0.24 + 0.22 * lvl)
        freq_mul = 1.4
    elif state == "thinking":
        base_amp = h * 0.28
        freq_mul = 2.0
    elif state == "speaking":
        base_amp = h * (0.22 + 0.14 * abs(math.sin(phase * 1.7)))
        freq_mul = 1.5
    elif state in ("success", "error"):
        base_amp = h * 0.20 * (0.6 + 0.4 * math.sin(phase * 2.0))
        freq_mul = 1.2
    else:  # idle gentle breathing
        base_amp = h * 0.10 * (0.75 + 0.25 * math.sin(phase * 0.6))
        freq_mul = 0.85

    ribbons: list[dict[str, Any]] = []
    n_pts = max(8, int(points))
    pad_x = 10.0
    usable_w = max(20.0, w - 2.0 * pad_x)

    for r_idx in range(max(1, min(3, num_ribbons))):
        coords: list[float] = []
        layer_scale = 1.0 - r_idx * 0.26
        layer_phase = phase * (1.0 + r_idx * 0.35) + r_idx * 1.15
        layer_freq = (2.2 + r_idx * 0.7) * freq_mul

        for i in range(n_pts):
            u = i / float(n_pts - 1)  # 0..1 across width
            x = pad_x + u * usable_w
            # Hanning window tapers wave smoothly to 0 at left and right edges
            envelope = 0.5 * (1.0 - math.cos(2.0 * math.pi * u))
            wave = (
                math.sin(u * math.pi * layer_freq + layer_phase) * 0.70
                + math.sin(u * math.pi * (layer_freq * 1.8) - layer_phase * 0.7) * 0.30
            )
            y = cy + wave * base_amp * layer_scale * envelope
            coords.extend((round(x, 2), round(y, 2)))

        ribbons.append({
            "coords": coords,
            "color": colors[r_idx % len(colors)],
            "width": 2.2 if r_idx == 0 else (1.5 if r_idx == 1 else 1.0),
        })

    # Central or left-aligned sonic orb pulse
    pulse = 0.5 + 0.5 * math.sin(phase * (2.4 if state != "idle" else 0.9))
    base_r = min(h * 0.24, 7.0)
    orb_r = base_r * (1.0 + 0.28 * pulse + 0.35 * lvl)
    glow_r = orb_r * (1.65 + 0.35 * pulse)

    return {
        "ribbons": ribbons,
        "orb": {
            "cx": round(w * 0.5, 2),
            "cy": round(cy, 2),
            "r": round(orb_r, 2),
            "glow_r": round(glow_r, 2),
            "color": colors[0],
        },
        "state_colors": colors,
    }


def compute_equalizer_bars(
    num_bars: int = 12,
    phase: float = 0.0,
    state: str = "idle",
    level: float = 0.0,
) -> list[float]:
    """Compute normalized bar heights [0.12 .. 1.0] for sonic bar visualizers."""
    n = max(1, int(num_bars))
    lvl = max(0.0, min(1.0, float(level)))
    bars: list[float] = []
    for i in range(n):
        u = i / float(max(1, n - 1))
        center_weight = 1.0 - 0.55 * abs(2.0 * u - 1.0)
        if state == "idle":
            val = 0.16 + 0.10 * center_weight * (0.5 + 0.5 * math.sin(phase * 0.9 + i * 0.55))
        elif state == "listening":
            wave = 0.5 + 0.5 * math.sin(phase * 2.8 + i * 0.75)
            val = 0.22 + (0.45 + 0.33 * lvl) * center_weight * wave
        elif state in ("thinking", "speaking"):
            wave = 0.5 + 0.5 * math.sin(phase * 2.4 - i * 0.65)
            val = 0.20 + 0.62 * center_weight * wave
        else:
            wave = 0.5 + 0.5 * math.sin(phase * 1.8 + i * 0.5)
            val = 0.18 + 0.45 * center_weight * wave
        bars.append(round(max(0.12, min(1.0, val)), 3))
    return bars


# --------------------------------------------------------------------------
# Progressive Text Reveal Chunker
# --------------------------------------------------------------------------

def stream_chunks(text: str, max_steps: int = 14) -> list[str]:
    """Split text into progressive chunks for smooth typewriter reveal animation."""
    if not text:
        return []
    n = len(text)
    if n <= 24 or max_steps <= 1:
        return [text]
    step_size = max(4, math.ceil(n / float(max_steps)))
    return [text[i : i + step_size] for i in range(0, n, step_size)]

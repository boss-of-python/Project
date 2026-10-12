"""Android theme — the *same* design tokens as the desktop app.

Rather than keeping two palettes in sync by hand, this module converts the
desktop tokens (``thans.ui.theme``) into the RGBA tuples Kivy wants, so both
apps are always the same product: one accent ramp, one type scale, one motion
language. Sizes are in ``dp`` so the phone layout scales with density.
"""
from __future__ import annotations

from thans.ui import theme as dt

# --------------------------------------------------------------------------
# colour
# --------------------------------------------------------------------------

def rgba(hexcolor: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    """``#5b8cff`` → ``(0.36, 0.55, 1.0, 1.0)`` (Kivy wants 0…1 floats)."""
    r, g, b = dt.hex2rgb(hexcolor)
    return (r / 255.0, g / 255.0, b / 255.0, float(alpha))


RGBA = tuple[float, float, float, float]


def _as_rgba(value) -> RGBA:
    """Accept either a hex string or an already-converted RGBA tuple."""
    return rgba(value) if isinstance(value, str) else tuple(value)


def mix(a, b, t: float) -> RGBA:
    """Blend two colours (hex string or RGBA tuple) — used by every widget."""
    ca, cb = _as_rgba(a), _as_rgba(b)
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    return tuple(ca[i] + (cb[i] - ca[i]) * t for i in range(4))


def fade(color, alpha: float) -> RGBA:
    c = _as_rgba(color)
    return (c[0], c[1], c[2], float(alpha))


BG = rgba(dt.BG)
BG_RAISED = rgba(dt.BG_RAISED)
SURFACE = rgba(dt.SURFACE)
SURFACE_HI = rgba(dt.SURFACE_HI)
BORDER = rgba(dt.BORDER)
BORDER_HI = rgba(dt.BORDER_HI)
FG = rgba(dt.FG)
FG_DIM = rgba(dt.FG_DIM)
FG_FAINT = rgba(dt.FG_FAINT)
ACCENT = rgba(dt.ACCENT)
ACCENT_HI = rgba(dt.ACCENT_HI)
ACCENT_LO = rgba(dt.ACCENT_LO)
ACCENT2 = rgba(dt.ACCENT2)
OK = rgba(dt.OK)
WARN = rgba(dt.WARN)
ERR = rgba(dt.ERR)
USER_BG = rgba(dt.USER_BG)
USER_FG = rgba(dt.USER_FG)
SYS_BG = rgba(dt.SYS_BG)
SYS_FG = rgba(dt.SYS_FG)
SCRIM = rgba(dt.SCRIM, 0.72)
WHITE = (1, 1, 1, 1)
TRANSPARENT = (0, 0, 0, 0)

RADIUS = float(dt.RADIUS_LG)
RADIUS_SM = float(dt.RADIUS_SM)

# --------------------------------------------------------------------------
# motion (seconds, Kivy style) — mirrors the desktop durations
# --------------------------------------------------------------------------
D_FAST = dt.D_FAST / 1000.0
D_BASE = dt.D_BASE / 1000.0
D_SLOW = dt.D_SLOW / 1000.0


def motion_enabled(flag: bool = True) -> float:
    """Return the duration to use: 0 when the user turned animations off."""
    return 1.0 if flag else 0.0


# --------------------------------------------------------------------------
# typography (sp)
# --------------------------------------------------------------------------
SIZE_TITLE = 22
SIZE_H2 = 16
SIZE_BODY = 15
SIZE_SMALL = 13
SIZE_TINY = 11

#: Kivy's stock font renders these fine; ASCII set matches the desktop Linux set.
from thans.ui.theme import symbols  # noqa: E402

SYM = symbols(emoji=False)

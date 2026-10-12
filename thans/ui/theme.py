"""Design tokens for the THANS desktop UI.

One palette, one motion language, one type scale — shared by every widget so
the app feels like a single, calm surface instead of a pile of controls.
The same tokens are mirrored for Kivy in ``android/thans_android/theme.py``.

Colour maths is plain Python (no tkinter import) so it is unit-testable and
reusable: ``thans/ui/logic.py`` and the tests import from here freely.
"""
from __future__ import annotations

import sys

# --------------------------------------------------------------------------
# palette  (dark, minimal, one accent ramp)
# --------------------------------------------------------------------------
BG = "#0b0d12"          # window
BG_RAISED = "#101319"   # toolbar / input rows
SURFACE = "#161a22"     # cards, assistant bubbles
SURFACE_HI = "#1d2330"  # hover / pressed
BORDER = "#242a36"
BORDER_HI = "#303849"

FG = "#e9edf7"          # primary text
FG_DIM = "#8b93a7"      # secondary text
FG_FAINT = "#5c6376"    # hints, timestamps

ACCENT = "#5b8cff"      # primary accent
ACCENT_HI = "#7aa2ff"
ACCENT_LO = "#3f6ede"
ACCENT2 = "#a06bff"     # gradient partner (accent → accent2)
OK = "#3ddc84"
WARN = "#ffc857"
ERR = "#ff6b6b"

USER_BG = "#1c2647"     # user bubble fill
USER_BORDER = "#2c3d70"
USER_FG = "#dce7ff"
SYS_BG = "#14171e"      # system chip fill
SYS_FG = "#9aa3b6"

SCRIM = "#04060a"       # dim layer behind slide-in panels

#: Ramp used by progress bars / mic ring / boot sweep.
GRADIENT = (ACCENT, ACCENT2)

# --------------------------------------------------------------------------
# metrics (pixels; the Kivy side uses dp() of the same numbers)
# --------------------------------------------------------------------------
RADIUS_LG = 16
RADIUS = 12
RADIUS_SM = 8
PAD = 14
PAD_S = 8
GAP = 10

BUBBLE_MAX_W = 620      # bubbles never get wider than this
BUBBLE_RADIUS = 14
CHAT_PAD = 18

HIT = 38                # comfortable minimum hit target

#: Animation durations in ms (0 disables motion — see ``motion_enabled``).
D_FAST = 120
D_BASE = 220
D_SLOW = 420
TICK_MS = 16            # ~60 fps

# --------------------------------------------------------------------------
# typography
# --------------------------------------------------------------------------
#: Preference lists — the first family actually installed wins.
UI_FAMILIES = (
    "Segoe UI Variable Text", "Segoe UI", "Inter", "SF Pro Text", "Helvetica Neue",
    "Ubuntu", "Cantarell", "Noto Sans", "Open Sans", "Liberation Sans", "DejaVu Sans",
    "TkDefaultFont",
)
MONO_FAMILIES = (
    "Cascadia Mono", "Cascadia Code", "Consolas", "JetBrains Mono", "SF Mono",
    "Menlo", "Ubuntu Mono", "Noto Sans Mono", "Liberation Mono", "DejaVu Sans Mono",
    "TkFixedFont",
)

SIZE_TITLE = 17
SIZE_BODY = 11
SIZE_SMALL = 10
SIZE_TINY = 9


def resolve_family(available, prefs):
    """Pick the first installed family from ``prefs``.

    ``available`` is a sequence of installed family names (case-insensitive
    match). Returns the preference string itself when nothing matches, so the
    caller can fall back to a Tk named font.
    """
    have = {a.casefold(): a for a in available}
    for pref in prefs:
        if pref.casefold() in have:
            return have[pref.casefold()]
    return prefs[-1]


# --------------------------------------------------------------------------
# icons
# --------------------------------------------------------------------------
#: Text glyphs. Emoji look great on Windows/macOS but DejaVu (typical Linux
#: default) renders them as tofu boxes, so Linux gets geometric symbols.
_EMOJI = sys.platform in ("win32", "darwin")

_SYM_EMOJI = {
    "folder": "📂", "mic": "🎤", "stop": "⏹", "send": "➤", "settings": "⚙",
    "models": "⬇", "sparkle": "✦", "check": "✓", "cross": "✕", "warn": "⚠",
    "undo": "↺", "search": "🔎", "doc": "📄", "list": "☰", "wand": "✨",
    "keyboard": "⌨", "home": "🏠", "moon": "◐", "play": "▶", "up": "▲", "down": "▼",
}
_SYM_ASCII = {
    "folder": "▣", "mic": "◉", "stop": "■", "send": "→", "settings": "≡",
    "models": "↓", "sparkle": "✦", "check": "✓", "cross": "✕", "warn": "!",
    "undo": "↺", "search": "⊙", "doc": "▤", "list": "☰", "wand": "✦",
    "keyboard": "⌨", "home": "⌂", "moon": "◐", "play": "▶", "up": "▲", "down": "▼",
}


def symbols(emoji: bool | None = None) -> dict[str, str]:
    """Glyph table; ``emoji=None`` picks the best set for this platform."""
    return _SYM_EMOJI if (_EMOJI if emoji is None else emoji) else _SYM_ASCII


SYM = symbols()

#: Emoji → equivalent glyph, for text that must render on a console font.
_EMOJI_DOWNGRADE = {v: _SYM_ASCII[k] for k, v in _SYM_EMOJI.items()
                    if k in _SYM_ASCII and v != _SYM_ASCII[k]}
_EMOJI_DOWNGRADE.update({"📄": "▤", "📁": "▣", "🗑": "✕", "🔍": "⊙", "⭐": "✦",
                         "★": "✦", "💡": "✦", "➡": "→"})


def plain(text: str) -> str:
    """Swap pictographs for glyphs that every bundled font can render.

    Used before putting text on a *monospace* surface (chat cards, file
    listings) where DejaVu Sans Mono has no emoji coverage — otherwise Linux
    users see tofu boxes where Windows/macOS users see icons.
    """
    if _EMOJI:
        return text
    out = text or ""
    for emoji, glyph in _EMOJI_DOWNGRADE.items():
        out = out.replace(emoji, glyph)
    return out


# --------------------------------------------------------------------------
# colour maths (pure — used by the animation engine on every frame)
# --------------------------------------------------------------------------

def hex2rgb(value: str) -> tuple[int, int, int]:
    v = value.lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def rgb2hex(rgb) -> str:
    r, g, b = (max(0, min(255, int(round(c)))) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def mix(c1: str, c2: str, t: float) -> str:
    """Blend two hex colours; ``t=0`` → c1, ``t=1`` → c2."""
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    r1, g1, b1 = hex2rgb(c1)
    r2, g2, b2 = hex2rgb(c2)
    return rgb2hex((lerp(r1, r2, t), lerp(g1, g2, t), lerp(b1, b2, t)))


def fade_in(color: str, bg: str, t: float) -> str:
    """Simulate alpha in a world without alpha: blend ``color`` over ``bg``."""
    return mix(bg, color, t)


def darken(color: str, t: float = 0.18) -> str:
    return mix(color, "#000000", t)


def lighten(color: str, t: float = 0.18) -> str:
    return mix(color, "#ffffff", t)


def ramp(a: str, b: str, steps: int) -> list[str]:
    """``steps`` colours from ``a`` to ``b`` (for gradient bars/sweeps)."""
    steps = max(2, int(steps))
    return [mix(a, b, i / (steps - 1)) for i in range(steps)]


def status_color(kind: str) -> str:
    """Map a state name to its indicator colour."""
    return {
        "ready": OK, "ok": OK, "on": OK,
        "busy": ACCENT, "working": ACCENT, "listening": ACCENT2, "info": ACCENT,
        "warn": WARN, "missing": WARN, "off": FG_FAINT,
        "error": ERR, "fail": ERR,
    }.get(kind, FG_FAINT)


def motion_enabled(cfg: dict | None = None) -> bool:
    """Respect an explicit ``motion`` setting (default: on)."""
    if not cfg:
        return True
    return bool(cfg.get("motion", True))

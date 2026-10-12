#!/usr/bin/env python3
"""Render a design preview of the THANS UI — desktop *and* phone — to a PNG.

Nothing here is hand-drawn art: the panels are composed from the app's own
design system and copy —

* colours / themes      → ``thans.animations.THEMES``
* sonic waves + orb     → ``thans.animations.compute_sonic_waves``
* intent preview pill   → ``thans.ui_helpers.preview_intent``
* quick chips           → ``thans.ui_helpers.QUICK_CHIPS``
* file icons + sizes    → ``thans.ui_helpers.file_icon`` / ``format_size``
* version / tagline     → ``thans``

so the picture in the README cannot drift from what the apps render.

    python scripts/render_ui_preview.py                      # → docs/ui-preview.png
    python scripts/render_ui_preview.py --out shot.png --scale 2

Requires Pillow (preview only — the apps themselves need no image library).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from thans import APP_NAME, __version__  # noqa: E402
from thans import animations as A  # noqa: E402
from thans import ui_helpers as U  # noqa: E402

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
UI, UI_B, MONO = "DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSansMono.ttf"
SCALE = 2                      # supersample so rounded corners stay crisp

#: The preview font has no colour emoji, so pictographs are drawn with the
#: closest geometric glyph. Purely cosmetic — the apps use the system emoji
#: font on Windows/macOS.
PICTO = {
    "📁": "▣", "📂": "▣", "📝": "▤", "📄": "▤", "📕": "▤", "📊": "▤", "💻": "▤",
    "📦": "▣", "🖼": "▣", "🐍": "§", "🎵": "♪", "🎬": "▶", "💬": "▤", "💡": "✦",
    "✨": "✦", "🔍": "⊙", "↩": "↺", "❓": "?", "♻️": "♻", "♻": "♻", "☀️": "☀",
    "🌙": "☾", "🎤": "◉", "⬇": "↓", "⚙": "⚙", "⬆": "↑", "↻": "↻", "↗": "↗",
    "✏️": "✎", "⚡": "⚡", "🖥": "▣", "⏎": "⏎", "🗑": "♻",
}


def txt(s: str) -> str:
    """Swap emoji for shape-compatible glyphs (preview font has no emoji)."""
    for emoji, glyph in PICTO.items():
        s = s.replace(emoji, glyph)
    return s


def font(size: int, bold: bool = False, mono: bool = False):
    path = FONT_DIR / (MONO if mono else (UI_B if bold else UI))
    if not path.exists():
        return ImageFont.load_default()
    return ImageFont.truetype(str(path), size * SCALE)


class Canvas:
    """Minimal drawing surface with the app's colour vocabulary."""

    def __init__(self, size, pal):
        self.w, self.h = size
        self.pal = pal
        self.img = Image.new("RGB", (self.w * SCALE, self.h * SCALE), pal["bg"])
        self.d = ImageDraw.Draw(self.img)

    # ---------------------------------------------------------------- shapes
    def rect(self, box, fill=None, radius=0, outline=None, width=1):
        x0, y0, x1, y1 = (v * SCALE for v in box)
        fill = self._c(fill)
        outline = self._c(outline)
        if radius > 0:
            self.d.rounded_rectangle([x0, y0, x1, y1], radius=radius * SCALE, fill=fill,
                                     outline=outline, width=max(1, int(width * SCALE)))
        else:
            self.d.rectangle([x0, y0, x1, y1], fill=fill, outline=outline,
                             width=max(1, int(width * SCALE)))

    def _c(self, colour):
        if colour is None or isinstance(colour, str):
            return colour
        return ""

    def line(self, xy, fill, width=1):
        self.d.line([(x * SCALE, y * SCALE) for x, y in xy], fill=fill,
                    width=max(1, int(width * SCALE)), joint="curve")

    def dot(self, cx, cy, r, fill):
        self.d.ellipse([(cx - r) * SCALE, (cy - r) * SCALE,
                        (cx + r) * SCALE, (cy + r) * SCALE], fill=fill)

    def glow(self, cx, cy, r, fill):
        self.d.ellipse([(cx - r) * SCALE, (cy - r) * SCALE,
                        (cx + r) * SCALE, (cy + r) * SCALE], fill=fill)

    def text(self, xy, s, size=10, color=None, bold=False, mono=False, anchor="la"):
        x, y = xy
        self.d.text((x * SCALE, y * SCALE), txt(str(s)), font=font(size, bold, mono),
                    fill=color or self.pal["fg"], anchor=anchor)

    def tw(self, s, size=10, bold=False, mono=False) -> float:
        return self.d.textlength(txt(str(s)), font=font(size, bold, mono)) / SCALE

    def paste(self, other: "Canvas", xy):
        self.img.paste(other.img, (int(xy[0] * SCALE), int(xy[1] * SCALE)))

    def save(self, path: Path):
        out = self.img.resize((self.w, self.h), Image.LANCZOS)
        path.parent.mkdir(parents=True, exist_ok=True)
        out.save(path)

    # ------------------------------------------------------------- composites
    def sonic(self, box, state="idle", phase=0.0, level=0.35, radius=6):
        """Draw `thans.animations.compute_sonic_waves` verbatim."""
        x0, y0, x1, y1 = box
        self.rect(box, self.pal["panel"], radius=radius, outline=self.pal["border"])
        w, h = int(x1 - x0 - 12), int(y1 - y0 - 2)
        geom = A.compute_sonic_waves(w, h, phase=phase, state=state, level=level)
        ox, oy = x0 + 6, y0 + 1
        for rib in geom["ribbons"]:
            coords = rib["coords"]
            pts = [(ox + coords[i], oy + coords[i + 1])
                   for i in range(0, len(coords) - 1, 2)]
            if len(pts) > 1:
                self.line(pts, rib["color"], rib["width"])
        orb = geom["orb"]
        cx, cy = ox + orb["cx"], oy + orb["cy"]
        r, gr = orb["r"], orb["glow_r"]
        self.glow(cx, cy, gr, A.lerp_color(self.pal["panel"], orb["color"], 0.32))
        self.dot(cx, cy, r, orb["color"])

    def eq_bars(self, box, state="idle", phase=2.0, count=9, level=0.4):
        """Draw `compute_equalizer_bars` verbatim (phone header indicator)."""
        x0, y0, x1, y1 = box
        w, h = max(1, int(x1 - x0)), max(1, int(y1 - y0))
        bars = A.compute_equalizer_bars(count, phase=phase, state=state, level=level)
        colours = A.STATE_COLORS.get(state, A.STATE_COLORS["idle"])
        gap = w / (count + 0.6)
        for i, frac in enumerate(bars):
            bh = max(2, frac * (h - 2))
            bx = x0 + gap * (i + 0.8)
            self.rect((bx - 1.2, y0 + (h - bh) / 2, bx + 1.2, y0 + (h + bh) / 2),
                      colours[i % len(colours)], radius=1)

    def ramp_bar(self, box, c1, c2, radius, frac=1.0):
        """A gradient pill (progress / accent ramp)."""
        x0, y0, x1, y1 = box
        width = int((x1 - x0) * SCALE * frac)
        if width < 2:
            return
        strip = Image.new("RGB", (width, max(1, int((y1 - y0) * SCALE))))
        sd = ImageDraw.Draw(strip)
        total = max(1, int((x1 - x0) * SCALE))
        for i in range(width):
            sd.line([(i, 0), (i, strip.height)], fill=A.lerp_color(c1, c2, i / total))
        mask = Image.new("L", strip.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, strip.size[0] - 1, strip.size[1] - 1],
                                              radius=radius * SCALE, fill=255)
        self.img.paste(strip, (int(x0 * SCALE), int(y0 * SCALE)), mask)


# ---------------------------------------------------------------------------
# desktop window (mirrors thans/app.py's _build order and copy)
# ---------------------------------------------------------------------------

def draw_desktop(size=(1120, 700), theme="dark") -> Canvas:
    pal = A.get_theme(theme)
    c = Canvas(size, pal)
    W, H = size

    # ---------------- 1. header bar
    c.text((16, 20), APP_NAME, size=15, bold=True)
    c.text((16 + c.tw(APP_NAME, 15, True) + 8, 24), f"offline assistant · v{__version__}",
           size=9, color=pal["dim"])
    c.sonic((196, 12, 396, 42), state="idle", phase=1.1, level=0.0)

    chips = [("📂 ~/work", pal["dim"]), ("STT ✓", pal["ok"]), ("TTS ✓", pal["ok"]),
             ("LLM off", pal["warn"]), ("♻️ 3", pal["dim"])]
    x = W - 16
    for label, fg in reversed(chips):
        w = c.tw(label, 8, True) + 18
        x -= w + 4
        c.rect((x, 13, x + w, 41), pal["panel"], radius=6)
        c.text((x + w / 2, 27), label, size=8, color=fg, bold=True, anchor="mm")
    c.rect((x - 34, 13, x - 6, 41), pal["panel2"], radius=6)
    c.text((x - 20, 27), "☀️", size=10, color=pal["fg"], anchor="mm")
    c.rect((x - 106, 13, x - 38, 41), pal["accent_soft"], radius=6)
    c.text((x - 72, 27), "◫ Files", size=8, color=pal["accent"], bold=True, anchor="mm")

    # ---------------- 2. breadcrumb bar
    c.rect((16, 50, W - 16, 80), pal["panel"], radius=8, outline=pal["border"])
    c.rect((24, 56, 74, 74), pal["panel2"], radius=5)
    c.text((49, 65), "⬆ Up", size=8, color=pal["fg"], bold=True, anchor="mm")
    bx = 84
    for i, (label, active) in enumerate((("🏠 root", False), ("work", False),
                                         ("reports", True))):
        if i:
            c.text((bx + 2, 65), "›", size=9, color=pal["dim"], anchor="mm")
            bx += 12
        w = c.tw(label, 9, active) + 12
        if active:
            c.rect((bx, 56, bx + w, 74), pal["accent_soft"], radius=5)
        c.text((bx + 6, 65), label, size=9, bold=active, anchor="lm",
               color=pal["accent"] if active else pal["fg_secondary"])
        bx += w + 4
    c.text((W - 24, 65), "4 folders · 12 files", size=9, color=pal["dim"], anchor="rm")

    # ---------------- 3. split body: chat pane + live workspace sidebar
    chat = (16, 86, W - 16 - 285 - 10, H - 214)
    c.rect(chat, pal["panel"], radius=8, outline=pal["border"])
    c.rect((chat[0], chat[1], chat[2], chat[1] + 26), pal["accent_soft"], radius=8)
    c.text((chat[0] + 12, chat[1] + 13), "📂 Working folder is ~/work — THANS stays inside it",
           size=9, color=pal["accent"], bold=True, anchor="lm")

    y = chat[1] + 40
    lines = [
        ("sys", "14:02 · Welcome to THANS — type or speak a file command, or click any quick "
                "chip below."),
        ("you", "14:03 · You › organize downloads by date"),
        ("thans", "14:03 · THANS › Moved 23 files into 4 folders in 'downloads'."),
        ("cmd", "      ⌘ parsed with rules ⚡ · no model needed"),
        ("you", "14:04 · You › how many files in work/reports"),
        ("thans", "14:04 · THANS › 12 files and 4 folders."),
    ]
    for kind, line in lines:
        colour = {"sys": pal["dim"], "you": pal["user_msg"], "thans": pal["asst_msg"],
                  "cmd": pal["cmd_pill"]}.get(kind, pal["fg"])
        bold = kind in ("you", "thans")
        c.text((chat[0] + 16, y), line, size=9.5, mono=True, color=colour, bold=bold)
        y += 20
    c.text((chat[0] + 16, y + 2), "▏", size=10, mono=True, color=pal["ok"])
    c.text((chat[0] + 24, y + 2), "streaming reply…", size=8, color=pal["dim"])

    # sidebar
    sx0, sx1 = chat[2] + 10, W - 16
    c.rect((sx0, chat[1], sx1, chat[3]), pal["panel"], radius=8, outline=pal["border"])
    c.text((sx0 + 12, chat[1] + 16), "LIVE WORKSPACE", size=8, bold=True,
           color=pal["dim"], anchor="lm")
    c.text((sx1 - 16, chat[1] + 16), "↻", size=12, color=pal["dim"], anchor="mm")
    c.rect((sx0 + 10, chat[1] + 28, sx1 - 10, chat[1] + 50), pal["panel2"], radius=5)
    c.text((sx0 + 18, chat[1] + 39), "filter files…", size=9, mono=True,
           color=pal["dim"], anchor="lm")

    rows = [("▣", "downloads", "23 files", True, False), ("▤", "notes.md", "4.1 KB", False, False),
            ("▤", "report.pdf", "1.2 MB", False, True), ("§", "tidy.py", "7.8 KB", False, False),
            ("▣", "work", "4 folders", False, False), ("▤", "todo.txt", "612 B", False, False)]
    ry = chat[1] + 58
    for glyph, name, size_label, selected, changed in rows:
        if selected:
            c.rect((sx0 + 8, ry, sx1 - 8, ry + 24), pal["accent_soft"], radius=5)
        elif changed:
            c.rect((sx0 + 8, ry, sx1 - 8, ry + 24), pal["ok_soft"], radius=5)
        glyph_colour = pal["accent"] if selected else (pal["ok"] if changed else pal["fg"])
        c.text((sx0 + 18, ry + 12), glyph, size=10, color=glyph_colour, anchor="lm")
        c.text((sx0 + 34, ry + 12), name, size=9.5, mono=True,
               color=pal["accent"] if selected else pal["fg"], anchor="lm")
        c.text((sx1 - 16, ry + 12), size_label, size=8.5, mono=True, color=pal["dim"],
               anchor="rm")
        ry += 26
    if changed := [(g, n, s) for g, n, s, _sel, ch in rows if ch]:
        c.text((sx0 + 12, ry + 4), "emerald pulse = just changed", size=8, color=pal["ok"])
    ab = chat[3] - 34
    c.rect((sx0 + 8, ab, sx1 - 8, chat[3] - 8), pal["panel2"], radius=6)
    for i, label in enumerate(("↗ Open", "✎ Rename", "✦ Organize", "♻ Trash")):
        seg = (sx1 - sx0 - 16) / 4
        col = pal["warn"] if "Trash" in label else pal["fg_secondary"]
        c.text((sx0 + 8 + seg * i + seg / 2, (ab + chat[3] - 8) / 2), label, size=8,
               color=col, anchor="mm")

    # ---------------- 4. live intent preview + quick chips
    py0 = H - 206
    c.rect((16, py0, W - 16, py0 + 30), pal["panel"], radius=8, outline=pal["border"])
    prev = U.preview_intent("create folder work")
    c.text((28, py0 + 15), prev.icon, size=10, color=pal["accent"], anchor="lm")
    c.text((48, py0 + 15), prev.title, size=9.5, color=pal["fg"], bold=True, anchor="lm")
    c.text((48 + c.tw(prev.title, 9.5, True) + 10, py0 + 15),
           f"· {prev.subtitle}", size=9, color=pal["dim"], anchor="lm")

    cx = 16
    for qc in U.QUICK_CHIPS:
        w = c.tw(qc.label, 8, True) + 18
        c.rect((cx, py0 + 36, cx + w, py0 + 58), pal["panel2"], radius=6)
        c.text((cx + w / 2, py0 + 47), qc.label, size=8, color=pal["fg_secondary"],
               anchor="mm")
        cx += w + 5

    # ---------------- 5. input dock
    iy0 = py0 + 66
    c.rect((16, iy0, 16 + 460, iy0 + 38), pal["panel2"], radius=6, outline=pal["accent"])
    c.text((28, iy0 + 19), "organize downloads by date", size=11, mono=True, anchor="lm")
    c.text((28 + c.tw("organize downloads by date", 11, mono=True) + 2, iy0 + 19), "▏",
           size=11, mono=True, color=pal["fg"], anchor="lm")
    bx = 16 + 470
    for label, style in (("Send ⏎", "accent"), ("🎤", "plain"), ("📂 Root", "plain"),
                         ("⬇ Models", "plain"), ("⚙ Settings", "plain")):
        w = max(c.tw(label, 9, style == "accent") + 22, 34)
        if style == "accent":
            c.rect((bx, iy0, bx + w, iy0 + 38), pal["accent"], radius=6)
            c.text((bx + w / 2, iy0 + 19), label, size=9, color="#ffffff", bold=True,
                   anchor="mm")
        else:
            c.rect((bx, iy0, bx + w, iy0 + 38), pal["panel2"], radius=6)
            c.text((bx + w / 2, iy0 + 19), label, size=9, color=pal["fg"], anchor="mm")
        bx += w + 6

    # ---------------- 6. status bar
    sy = H - 26
    c.rect((0, sy - 6, W, H), pal["panel"])
    c.text((16, sy + 4), "ready · in ~/work/reports · Tab=complete · Ctrl+Z=undo", size=8.5,
           color=pal["dim"], anchor="lm")
    c.text((W - 16, sy + 4),
           f"{APP_NAME} v{__version__} · 100% offline · Tab=complete · Ctrl+Z=undo",
           size=8.5, color=pal["dim"], anchor="rm")
    return c


# ---------------------------------------------------------------------------
# phone screens (mirror android/thans.kv)
# ---------------------------------------------------------------------------

def _phone_shell(W, H, pal, tab, content, theme_icon="☀️"):
    """Header + breadcrumb/tab bar + content card + preview + chips + dock."""
    c = Canvas((W, H), pal)
    pad = 10

    # ---- header
    c.rect((pad, 8, W - pad, 52), pal["panel"], radius=12)
    c.text((pad + 12, 20), APP_NAME, size=13, bold=True)
    c.text((pad + 12, 38), "● offline ready", size=8.5, color=pal["dim"])
    bx = W - pad - 10
    for label, w, bg, fg in (("↩", 30, pal["panel2"], pal["fg"]),
                             (theme_icon, 30, pal["panel2"], pal["fg"]),
                             ("SPEAK: OFF", 84, pal["panel2"], pal["dim"])):
        bx -= w
        c.rect((bx, 15, bx + w, 45), bg, radius=8)
        c.text((bx + w / 2, 30), label, size=9 if w > 40 else 12, color=fg, anchor="mm")
        bx -= 5

    # ---- breadcrumb / tabs row
    c.rect((pad, 58, W - pad, 94), pal["panel"], radius=10)
    c.rect((pad + 6, 64, pad + 60, 88), pal["panel2"], radius=6)
    c.text((pad + 33, 76), "⬆ Up", size=8.5, color=pal["fg"], bold=True, anchor="mm")
    crumb = "🏠 root › work" if tab == "files" else "🏠 root"
    c.text((pad + 70, 76), crumb, size=9, color=pal["accent"], bold=True, anchor="lm")
    c.eq_bars((W - pad - 210, 64, W - pad - 148, 88), state="idle", phase=2.0)
    for label, active, w in (("💬 Chat", tab == "chat", 62), ("📁 Files", tab == "files", 68)):
        bx = (W - pad - 62 - 68 - 4) if label.startswith("💬") else (W - pad - 68)
        c.rect((bx, 64, bx + w, 88), pal["accent"] if active else pal["panel2"], radius=6)
        c.text((bx + w / 2, 76), label, size=8.5,
               color="#ffffff" if active else pal["fg_secondary"], anchor="mm")

    # ---- content card
    card = (pad, 100, W - pad, 100 + 396)
    c.rect(card, pal["panel"], radius=14)
    if content:
        content(c, card)

    # ---- live intent pill
    prev = U.preview_intent("organize downloads by date" if tab == "chat" else "")
    c.rect((pad, 506, W - pad, 538), pal["panel"], radius=10)
    c.text((pad + 12, 522), f"{prev.icon} {prev.title} · {prev.subtitle}", size=8.5,
           color=pal["fg_secondary"], anchor="lm")

    # ---- quick chips
    cx = pad
    for qc in list(U.QUICK_CHIPS) + [U.QuickChip("⚡ Complete", "", False)]:
        label = qc.label
        w = c.tw(label, 8.5) + 16
        if cx + w > W - pad:
            break
        c.rect((cx, 546, cx + w, 572), pal["panel2"], radius=7)
        c.text((cx + w / 2, 559), label, size=8.5, color=pal["fg_secondary"], anchor="mm")
        cx += w + 5

    # ---- input dock
    c.rect((pad, 580, W - pad - 62, 616), pal["panel2"], radius=8)
    c.text((pad + 12, 598), "Command, e.g. 'create folder work'", size=9,
           color=pal["dim"], anchor="lm")
    c.rect((W - pad - 58, 580, W - pad, 616), pal["accent"], radius=8)
    c.text((W - pad - 29, 598), "SEND", size=9, color="#ffffff", bold=True, anchor="mm")
    c.rect((pad, 622, W / 2 - 4, 660), pal["panel2"], radius=8)
    c.text((pad + (W / 2 - pad - 4) / 2, 641), "🎤 MIC", size=9.5, color=pal["fg"],
           anchor="mm")
    c.rect((W / 2 + 4, 622, W - pad, 660), pal["panel2"], radius=8)
    c.text(((W / 2 + 4 + W - pad) / 2, 641), "❓ HELP", size=9.5, color=pal["fg"],
           anchor="mm")
    return c


def phone_chat(size=(360, 672), theme="dark") -> Canvas:
    pal = A.get_theme(theme)

    def content(c, card):
        (x0, y0, x1, _) = card
        y = y0 + 14
        for who, kind, text_lines in (
            ("THANS", "asst_msg", ["Welcome to THANS — type or speak a file command,",
                                   "or tap any chip below."]),
            ("You", "user_msg", ["organize downloads by date"]),
            ("THANS", "asst_msg", ["Moved 23 files into 4 folders in 'downloads'."]),
            ("⚡ rules", "cmd_pill", ["parsed instantly · no model needed"]),
        ):
            colour = pal[kind]
            c.text((x0 + 14, y), who, size=9, bold=True, color=colour)
            y += 15
            for line in text_lines:
                c.text((x0 + 14, y), line, size=9.5, mono=True, color=pal["fg"])
                y += 16
            y += 8
        c.text((x0 + 14, y), "▏", size=10, mono=True, color=pal["ok"])
        c.text((x0 + 22, y), "streaming…", size=8.5, color=pal["dim"])
        # toast
        c.rect((x0 + 12, y + 20, x1 - 12, y + 50), pal["ok_soft"], radius=10)
        c.text((x0 + 24, y + 35), "✓ 23 files tidied · 4 folders created", size=9,
               color=pal["ok"], anchor="lm")

    return _phone_shell(*size, pal=pal, tab="chat", content=content)


def phone_files(size=(360, 672), theme="light") -> Canvas:
    pal = A.get_theme(theme)
    rows = [("📁", "downloads", "23 files", False, True), ("📄", "notes.md", "4.1 KB", False, False),
            ("📕", "report.pdf", "1.2 MB", False, False), ("🐍", "tidy.py", "7.8 KB", False, False),
            ("📁", "work", "4 folders", True, False), ("📝", "todo.txt", "612 B", False, False),
            ("🖼", "cover.png", "318 KB", False, False), ("📦", "backup.zip", "12.4 MB", False, False)]

    def content(c, card):
        (x0, y0, x1, y1) = card
        c.text((x0 + 14, y0 + 20), "LIVE WORKSPACE", size=8, bold=True, color=pal["dim"],
               anchor="lm")
        c.text((x1 - 20, y0 + 20), "↻", size=12, color=pal["dim"], anchor="mm")
        c.rect((x0 + 12, y0 + 32, x1 - 12, y0 + 58), pal["panel2"], radius=6)
        c.text((x0 + 22, y0 + 45), "filter files…", size=9, color=pal["dim"], anchor="lm")
        y = y0 + 66
        for glyph, name, size_label, selected, changed in rows:
            bg = pal["accent_soft"] if selected else (pal["ok_soft"] if changed else pal["panel2"])
            c.rect((x0 + 12, y, x1 - 12, y + 34), bg, radius=8)
            c.text((x0 + 24, y + 17), f"{glyph}  {name}   ({size_label})", size=9.5,
                   color=pal["accent"] if selected else pal["fg"], anchor="lm")
            c.rect((x1 - 52, y + 3, x1 - 18, y + 31), pal["panel"], radius=6)
            c.text((x1 - 35, y + 17), "♻️", size=10, color=pal["warn"], anchor="mm")
            y += 38
        c.text((x0 + 14, y + 2), "tap a folder to enter · tap a file to rename",
               size=8, color=pal["dim"])

    return _phone_shell(*size, pal=pal, tab="files", content=content)


def draw_icon(size=84, caption="app icon · android · windows · linux") -> Canvas:
    pal = A.get_theme("dark")
    box = Canvas((size, size + 22), pal)
    for i in range(size):                       # accent ramp tile
        box.rect((i, 0, i + 1, size), A.lerp_color("#6f9cff", pal["accent"], i / (size - 1)))
    box.d.rounded_rectangle([0, 0, size * SCALE - 1, size * SCALE - 1],
                            radius=int(size * 0.22 * SCALE), outline=pal["bg"],
                            width=4 * SCALE)
    box.text((size / 2, size / 2 + 1), "✦", size=int(size * 0.46), color="#ffffff",
             anchor="mm")
    box.text((size / 2, size + 12), caption, size=8.5, color=pal["dim"], anchor="mm")
    return box


# ---------------------------------------------------------------------------
# composition
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Render the THANS UI design preview")
    ap.add_argument("--out", default=str(ROOT / "docs" / "ui-preview.png"))
    a = ap.parse_args(argv)

    pad, top = 26, 62
    desktop = draw_desktop((1120, 700), "dark")
    phone_dark = phone_chat((360, 672), "dark")
    phone_light = phone_files((360, 672), "light")
    icon = draw_icon(84)

    W = 1120 + pad * 3 + 360 * 2 + 20
    H = top + 700 + 92
    sheet = Canvas((W, H), A.get_theme("dark"))
    pal = sheet.pal
    sheet.text((pad, 20), f"{APP_NAME} — one design language, two apps", size=13, bold=True)
    sheet.text((pad + sheet.tw(f"{APP_NAME} — one design language, two apps", 13, True) + 10,
                24),
               "tokens, sonic-wave geometry and copy rendered live from "
               "thans/animations.py + thans/ui_helpers.py",
               size=8.5, color=pal["dim"])
    sheet.text((W - pad, 24), f"v{__version__} · 100% offline", size=8.5,
               color=pal["dim"], anchor="rm")

    sheet.paste(desktop, (pad, top))
    px = pad * 2 + 1120
    sheet.paste(phone_dark, (px, top))
    sheet.paste(phone_light, (px + 360 + 20, top))
    caption_y = top + 672 + 18
    sheet.text((px + 180, caption_y), "android · chat (dark)", size=8.5, color=pal["dim"],
               anchor="mm")
    sheet.text((px + 360 + 20 + 180, caption_y), "android · files (light theme)", size=8.5,
               color=pal["dim"], anchor="mm")
    fy = top + 700 + 12
    sheet.paste(icon, (pad, fy))
    legend = [
        "60fps sonic visualizer that reacts to idle / listening / thinking / speaking",
        "live intent preview + Tab autocomplete · quick-action chips · breadcrumb navigation",
        "live workspace inspector with emerald change pulses · toasts · dark & light themes",
    ]
    for i, line in enumerate(legend):
        sheet.text((pad + 84 + 16, fy + 12 + i * 17), line, size=9, color=pal["fg_secondary"],
                   anchor="lm")

    out = Path(a.out)
    sheet.save(out)
    print(f"wrote {out}  ({out.stat().st_size // 1024} KB, {W}x{H})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

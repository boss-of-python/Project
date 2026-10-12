#!/usr/bin/env python3
"""Render a design preview of the THANS UI — desktop *and* phone — to a PNG.

The mock-up is drawn from the **real** design tokens (``thans.ui.theme``) and
the real copy (``thans.ui.logic`` starters, templates, key hints), so the
preview can never drift from the app: change the palette or a hint and the
preview changes with it.

    python scripts/render_ui_preview.py                # → docs/ui-preview.png
    python scripts/render_ui_preview.py --out shot.png

Requires Pillow (preview only — the app itself needs no image library).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from thans.ui import logic, theme as T  # noqa: E402

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
UI, UI_B, MONO = "DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSansMono.ttf"
SCALE = 2                      # supersample for crisp rounded corners


def font(size: int, bold: bool = False, mono: bool = False) -> ImageFont.FreeTypeFont:
    name = MONO if mono else (UI_B if bold else UI)
    path = FONT_DIR / name
    if not path.exists():      # fall back to Pillow's bundled font
        return ImageFont.load_default()
    return ImageFont.truetype(str(path), size * SCALE)


class Canvas:
    """Tiny helper: hex colours, rounded rects, text with tokens."""

    def __init__(self, size):
        self.img = Image.new("RGB", (size[0] * SCALE, size[1] * SCALE), T.BG)
        self.d = ImageDraw.Draw(self.img)
        self.w, self.h = size

    def rect(self, box, fill, radius=0, outline=None, width=1):
        x0, y0, x1, y1 = [v * SCALE for v in box]
        r = radius * SCALE
        if r > 0:
            self.d.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=fill,
                                     outline=outline, width=max(1, width * SCALE))
        else:
            self.d.rectangle([x0, y0, x1, y1], fill=fill, outline=outline,
                             width=max(1, width * SCALE))

    def gradient_bar(self, box, c1, c2, radius):
        x0, y0, x1, y1 = box
        width = int((x1 - x0) * SCALE)
        strip = Image.new("RGB", (max(1, width), max(1, (y1 - y0) * SCALE)))
        sd = ImageDraw.Draw(strip)
        for i in range(max(1, width)):
            sd.line([(i, 0), (i, strip.height)], fill=T.mix(c1, c2, i / max(1, width - 1)))
        mask = Image.new("L", (max(1, width), max(1, (y1 - y0) * SCALE)), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, width - 1, strip.height - 1],
                                              radius=radius * SCALE, fill=255)
        self.img.paste(strip, (int(x0 * SCALE), int(y0 * SCALE)), mask)

    def text(self, xy, s, size=11, color=T.FG, bold=False, mono=False, anchor="la"):
        x, y = xy
        self.d.text((x * SCALE, y * SCALE), s, font=font(size, bold, mono),
                    fill=color, anchor=anchor)

    def tw(self, s, size=11, bold=False, mono=False) -> float:
        return self.d.textlength(s, font=font(size, bold, mono)) / SCALE

    def paste(self, other: "Canvas", xy):
        self.img.paste(other.img, (int(xy[0] * SCALE), int(xy[1] * SCALE)))

    def save(self, path: Path):
        out = self.img.resize((self.w, self.h), Image.LANCZOS)
        path.parent.mkdir(parents=True, exist_ok=True)
        out.save(path)


# --------------------------------------------------------------------------
# desktop window
# --------------------------------------------------------------------------

def draw_desktop(win=(1040, 660)) -> Canvas:
    c = Canvas(win)
    W, H = win
    c.rect((0, 0, W, H), T.BG)

    # window chrome
    c.rect((0, 0, W, H), T.BG)
    c.rect((0, 0, W, 1), T.BORDER)

    # ---- header
    c.rect((6, 14, 36, 44), T.mix(T.ACCENT, T.ACCENT2, 0.5), radius=9)
    c.text((21, 29), T.SYM["sparkle"], size=15, color="#ffffff", anchor="mm")
    c.text((44, 22), "THANS", size=15, bold=True)
    c.text((44 + c.tw("THANS", 15, True) + 8, 25), "v0.2.0", size=9, color=T.FG_FAINT)

    chips = [("working folder", T.OK), ("voice ready", T.OK), ("llm none", T.FG_FAINT)]
    x = W - 16
    for label, color in reversed(chips):
        w = c.tw(label, 10) + 30
        x -= w + 6
        c.rect((x, 16, x + w, 40), T.SURFACE, radius=12, outline=T.BORDER, width=1)
        c.d.ellipse([(x + 11) * SCALE, 24 * SCALE, (x + 18) * SCALE, 31 * SCALE], fill=color)
        c.text((x + 24, 28), label, size=10, color=T.FG_DIM, anchor="lm")
    icons_x = W - 16 - 3 * 40
    for i, glyph in enumerate((T.SYM["undo"], T.SYM["models"], T.SYM["settings"])):
        bx = icons_x + i * 40
        c.rect((bx, 14, bx + 32, 46), T.SURFACE, radius=16, outline=T.BORDER, width=1)
        c.text((bx + 16, 30), glyph, size=12, color=T.FG_DIM, anchor="mm")
    c.rect((0, 56, W, 57), T.BORDER)

    # ---- chat card
    cx0, cy0, cx1, cy1 = 14, 66, W - 288, H - 116
    c.rect((cx0, cy0, cx1, cy1), T.BG, radius=16, outline=T.BORDER, width=1)

    # message: THANS
    y = cy0 + 18
    c.text((cx0 + 18, y), "THANS ▎", size=10, bold=True, color=T.ACCENT_HI)
    y += 18
    c.text((cx0 + 18, y), "welcome · 09:41", size=9, color=T.FG_FAINT)
    y += 18
    for line in ("Good morning! I manage files & folders inside your working folder —",
                 "by the sound of your voice or by typing. Say 'help' any time (F1),",
                 "or press the mic (F2) and just talk."):
        c.text((cx0 + 18, y), line, size=11)
        y += 19

    # message: You (right aligned bubble)
    y += 14
    bubble = "organize downloads by date"
    bw = c.tw(bubble, 11) + 28
    bx = cx1 - 18 - bw
    c.rect((bx, y, cx1 - 18, y + 34), T.USER_BG, radius=14)
    c.text((bx + 14, y + 17), bubble, size=11, color=T.USER_FG, anchor="lm")
    c.text((cx1 - 18, y + 38), "You ▎  09:41", size=9, color=T.FG_FAINT, anchor="ra")

    # message: THANS reply (streamed, caret visible)
    y += 66
    c.text((cx0 + 18, y), "THANS ▎", size=10, bold=True, color=T.ACCENT_HI)
    y += 20
    c.text((cx0 + 18, y), "rules · 09:41", size=9, color=T.FG_FAINT)
    y += 18
    c.text((cx0 + 18, y), "Moved 23 files in 'downloads' → 2026-08/ (9), 2026-09/ (11), 2026-10/ (3).",
           size=11)
    c.text((cx0 + 18, y + 19), "▍", size=11, color=T.ACCENT_HI)

    # ---- dashboard column
    dx0, dx1 = W - 274, W - 14
    y = 66
    c.rect((dx0, y, dx1, y + 152), T.SURFACE, radius=16, outline=T.BORDER, width=1)
    c.text((dx0 + 14, y + 14), "WORKING FOLDER", size=9, bold=True, color=T.FG_FAINT)
    c.text((dx1 - 14, y + 24), T.SYM["folder"] + " Open", size=10, color=T.FG_DIM, anchor="rm")
    c.text((dx0 + 14, y + 36), "~/Documents/thans-demo", size=10, bold=True)
    for i, (val, label) in enumerate((("1,284", "files"), ("37", "folders"),
                                      ("2.4 GB", "total size"))):
        col = dx0 + 16 + i * 86
        c.text((col, y + 60), val, size=16, bold=True)
        c.text((col, y + 84), label, size=9, color=T.FG_FAINT)
    c.rect((dx0 + 14, y + 104, dx1 - 14, y + 110), T.mix(T.SURFACE_HI, T.BG, 0.35), radius=3)
    c.gradient_bar((dx0 + 14, y + 104, dx0 + 14 + (dx1 - dx0 - 28) * 0.46, y + 110),
                   T.ACCENT, T.ACCENT2, radius=3)
    c.text((dx0 + 14, y + 118), "742 GB free of 1.4 TB · healthy", size=9, color=T.FG_DIM)
    c.text((dx0 + 14, y + 132), "scanned just now", size=9, color=T.FG_FAINT)

    y += 164
    c.rect((dx0, y, dx1, y + 118), T.SURFACE, radius=16, outline=T.BORDER, width=1)
    c.text((dx0 + 14, y + 14), "QUICK ACTIONS", size=9, bold=True, color=T.FG_FAINT)
    actions = [(T.SYM["wand"], "Organize"), (T.SYM["undo"], "Undo"),
               (T.SYM["search"], "Find"), (T.SYM["list"], "Count")]
    for i, (glyph, label) in enumerate(actions):
        bx = dx0 + 14 + (i % 2) * 126
        by = y + 32 + (i // 2) * 40
        c.rect((bx, by, bx + 118, by + 34), T.SURFACE_HI, radius=8)
        c.text((bx + 14, by + 17), f"{glyph}  {label}", size=10, color=T.FG, anchor="lm")

    y += 130
    c.rect((dx0, y, dx1, y + 104), T.SURFACE, radius=16, outline=T.BORDER, width=1)
    c.text((dx0 + 14, y + 14), "VOICE", size=9, bold=True, color=T.FG_FAINT)
    bars = [3, 8, 14, 20, 14, 9, 4]
    for i, bh in enumerate(bars):
        bx = dx0 + 18 + i * 7
        c.rect((bx, y + 52 - bh / 2, bx + 4, y + 52 + bh / 2), T.ACCENT2, radius=2)
    c.text((dx0 + 74, y + 44), "listening…", size=10, color=T.ACCENT_HI)
    c.text((dx0 + 74, y + 58), "speak your command", size=9, color=T.FG_FAINT)
    c.text((dx0 + 14, y + 78), "Speak replies", size=10)
    c.rect((dx1 - 58, y + 74, dx1 - 14, y + 96), T.ACCENT, radius=11)
    c.d.ellipse([(dx1 - 34) * SCALE, (y + 77) * SCALE, (dx1 - 17) * SCALE, (y + 93) * SCALE],
                fill="#ffffff")

    # ---- suggestion pills + composer
    sy = H - 108
    pills = [(logic.truncate(t, 26), 96) for t in logic.suggest("org", limit=3)]
    x = 16
    for label, _ in pills:
        w = c.tw(label, 9) + 22
        c.rect((x, sy, x + w, sy + 24), T.SURFACE_HI, radius=12, outline=T.BORDER, width=1)
        c.text((x + 11, sy + 12), label, size=9, color=T.FG_DIM, anchor="lm")
        x += w + 6
    if not pills:
        for label in ("organize <folder> by date", "organize <folder>"):
            w = c.tw(label, 9) + 22
            c.rect((x, sy, x + w, sy + 24), T.SURFACE_HI, radius=12, outline=T.BORDER, width=1)
            c.text((x + 11, sy + 12), label, size=9, color=T.FG_DIM, anchor="lm")
            x += w + 6

    iy0 = H - 76
    c.rect((14, iy0, W - 14, iy0 + 58), T.BG_RAISED, radius=16, outline=T.BORDER_HI, width=1)
    c.text((32, iy0 + 29), "organize downloads by date▍", size=13, color=T.FG, anchor="lm")
    # send + mic
    c.rect((W - 96, iy0 + 11, W - 26, iy0 + 47), T.mix(T.ACCENT, T.ACCENT2, 0.35), radius=10)
    c.text((W - 61, iy0 + 29), "Send " + T.SYM["send"], size=11, color="#ffffff", anchor="mm")
    c.rect((W - 148, iy0 + 12, W - 114, iy0 + 46), T.BG_RAISED, radius=17,
           outline=T.BORDER, width=1)
    c.text((W - 131, iy0 + 29), T.SYM["mic"], size=13, color=T.FG_DIM, anchor="mm")

    # ---- status bar
    c.text((16, H - 20), "in downloads  ·  root ~/Documents/thans-demo", size=9,
           color=T.FG_DIM, anchor="lm")
    c.text((W - 16, H - 20), logic.keys_hint(short=True), size=9, color=T.FG_FAINT,
           anchor="rm")

    return c


# --------------------------------------------------------------------------
# phone (Android) screen
# --------------------------------------------------------------------------

def draw_phone(size=(360, 596)) -> Canvas:
    W, H = size
    c = Canvas(size)
    c.rect((0, 0, W, H), T.BG, radius=22)

    # status bar hint
    c.text((14, 8), "09:41", size=9, color=T.FG_FAINT)

    # header
    c.rect((14, 22, 36, 44), T.mix(T.ACCENT, T.ACCENT2, 0.5), radius=7)
    c.text((25, 33), T.SYM["sparkle"], size=10, color="#ffffff", anchor="mm")
    c.text((42, 33), "THANS", size=13, bold=True, anchor="lm")
    for i, (label, color) in enumerate((("SPEAK: ON", T.OK), ("rule parser", T.OK))):
        w = c.tw(label, 9) + 26
        bx = W - 14 - w
        if i == 0:
            first_bx = bx
        bx = first_bx - (i) * 0 - i * 0
    # chips right-aligned
    labels = [("SPEAK: ON", T.OK), ("rule parser", T.OK)]
    bx = W - 14
    for label, color in reversed(labels):
        w = c.tw(label, 9) + 26
        bx -= w + 5
        c.rect((bx, 20, bx + w, 44), T.SURFACE, radius=12, outline=T.BORDER, width=1)
        c.d.ellipse([(bx + 9) * SCALE, 29 * SCALE, (bx + 16) * SCALE, 36 * SCALE], fill=color)
        c.text((bx + 21, 32), label, size=9, color=T.FG_DIM, anchor="lm")

    # status + thinking dots
    c.text((14, 54), "thinking…", size=9, color=T.FG_DIM)
    for i, r in enumerate((2.0, 2.8, 3.6)):
        cx = W - 40 + i * 11
        c.d.ellipse([(cx - r) * SCALE, (61 - r) * SCALE, (cx + r) * SCALE, (61 + r) * SCALE],
                    fill=T.mix(T.ACCENT, T.BG, 0.45 - i * 0.15))
    # busy sweep
    c.rect((14, 70, W - 14, 73), T.mix(T.SURFACE_HI, T.BG, 0.35), radius=2)
    c.gradient_bar((14 + (W - 28) * 0.45, 70, 14 + (W - 28) * 0.45 + 90, 73),
                   T.ACCENT, T.ACCENT2, radius=2)

    # bubbles (newest on top)
    y = 84

    def bubble(y, who, lines, kind, fill, fg, rail):
        h = 22 + 17 * len(lines)
        c.rect((14, y, W - 14, y + h), fill, radius=14)
        c.text((26, y + 12), f"{who} ▎", size=9, bold=True, color=rail, anchor="lm")
        yy = y + 26
        for line in lines:
            c.text((26, yy), line, size=11, color=fg)
            yy += 17
        return y + h + 8

    y = bubble(y, "THANS", ["Good morning! Tap the mic and talk, or",
                            "type. Try 'create folder notes'."],
               "thans", T.SURFACE, T.FG, T.ACCENT_HI)
    y = bubble(y, "THANS", ["No speech service on this device, so voice is",
                            "off — typing works exactly the same."],
               "system", T.SYS_BG, T.SYS_FG, T.FG_DIM)
    y = bubble(y, "You", ["create folder notes"], "you", T.USER_BG, T.USER_FG, T.USER_FG)
    y = bubble(y, "THANS · rules", ["Created folder 'notes'."], "thans",
               T.SURFACE, T.FG, T.ACCENT_HI)

    # toast
    c.rect((24, y + 4, W - 24, y + 42), T.mix(T.SURFACE, T.BG, 0.25), radius=19,
           outline=T.mix(T.BORDER, T.OK, 0.6), width=1)
    c.d.ellipse([(38) * SCALE, (y + 19) * SCALE, (44) * SCALE, (y + 25) * SCALE], fill=T.OK)
    c.text((52, y + 23), "Nice — that's tidier now", size=10, color=T.FG, anchor="lm")

    # suggestion pills
    sy = H - 146
    pills = [t for t in logic.suggest("cre", limit=2)]
    x = 14
    for label in pills:
        w = c.tw(label, 9) + 20
        c.rect((x, sy, x + w, sy + 26), T.SURFACE_HI, radius=13,
               outline=T.BORDER, width=1)
        c.text((x + 10, sy + 13), logic.truncate(label, 22), size=9, color=T.FG_DIM,
               anchor="lm")
        x += w + 6

    # quick actions row
    qy = H - 108
    labels = [T.SYM["wand"] + " Organize", T.SYM["undo"] + " Undo",
              T.SYM["list"] + " Count", T.SYM["keyboard"] + " Help"]
    x = 14
    for label in labels:
        w = c.tw(label, 9) + 18
        c.rect((x, qy, x + w, qy + 30), T.SURFACE_HI, radius=9)
        c.text((x + 9, qy + 15), label, size=9, color=T.FG_DIM, anchor="lm")
        x += w + 5

    # composer: input | mic | send
    cy = H - 68
    c.rect((14, cy, W - 126, cy + 50), T.BG_RAISED, radius=14,
           outline=T.BORDER_HI, width=1)
    c.text((28, cy + 25), "type a command…", size=11, color=T.FG_FAINT, anchor="lm")
    c.rect((W - 116, cy, W - 68, cy + 50), T.BG_RAISED, radius=25,
           outline=T.ACCENT, width=2)
    c.text((W - 92, cy + 25), T.SYM["mic"], size=15, color=T.ACCENT2, anchor="mm")
    c.rect((W - 60, cy, W - 12, cy + 50), T.mix(T.ACCENT, T.ACCENT2, 0.35), radius=25)
    c.text((W - 36, cy + 25), T.SYM["send"], size=15, color="#ffffff", anchor="mm")
    return c


def draw_icon(size=84, caption="app icon · android / windows / linux") -> Canvas:
    """The launcher icon, drawn with the same accent ramp as the UI."""
    box = Canvas((size, size + 22))
    for i in range(size):                     # diagonal accent → violet ramp
        box.rect((i, 0, i + 1, size), T.mix("#6f9cff", T.ACCENT2, i / (size - 1)))
    # knock the corners back out to the page colour → rounded squircle
    box.d.rounded_rectangle([0, 0, size * SCALE - 1, size * SCALE - 1],
                            radius=int(size * 0.22 * SCALE), outline=T.BG,
                            width=int(4 * SCALE))
    box.text((size / 2, size / 2 + 1), T.SYM["sparkle"], size=int(size * 0.46),
             color="#ffffff", anchor="mm")
    box.text((size / 2, size + 12), caption, size=9, color=T.FG_FAINT, anchor="mm")
    return box


# --------------------------------------------------------------------------
# composition
# --------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Render the THANS UI design preview")
    ap.add_argument("--out", default=str(ROOT / "docs" / "ui-preview.png"))
    a = ap.parse_args(argv)

    pad = 26
    desktop = draw_desktop((1040, 660))
    phone = draw_phone((360, 596))
    icon = draw_icon(84)

    W = 1040 + pad * 3 + 360
    H = 660 + pad * 2 + 54
    sheet = Canvas((W, H))
    sheet.rect((0, 0, W, H), T.BG)
    sheet.text((pad, 14), "THANS — one design language, two apps", size=13, bold=True)
    sheet.text((pad + sheet.tw("THANS — one design language, two apps", 13, True) + 10, 17),
               "tokens from thans/ui/theme.py · same palette, type scale and motion on desktop and Android",
               size=9, color=T.FG_FAINT)
    px = pad * 2 + 1040
    sheet.paste(desktop, (pad, 44))
    sheet.paste(phone, (px, 44))
    sheet.paste(icon, (px + (360 - 84) / 2, 44 + 596 + 14))

    out = Path(a.out)
    sheet.save(out)
    print(f"wrote {out}  ({out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

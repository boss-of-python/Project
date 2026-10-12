"""Canvas-drawn tkinter widgets: rounded cards, buttons, switches, chips…

tkinter has no rounded corners or gradients, so every piece here paints itself
on a ``tk.Canvas``. Each widget takes the app's :class:`~thans.ui.logic.Animator`
so *all* motion is driven by the single 60 fps loop in ``app.py`` — no widget
spins up its own loop, and turning ``motion`` off in Settings makes every
widget snap instantly instead of animating.
"""
from __future__ import annotations

import math
import tkinter as tk
from tkinter import font as tkfont
from typing import Callable, Optional

from . import logic, theme as T


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def widget_bg(w, default: str = T.BG) -> str:
    """Best-effort background colour of a widget (ttk widgets have none)."""
    try:
        c = w.cget("bg") or w.cget("background")
        return str(c) or default
    except Exception:
        return default


def round_rect_points(x0: float, y0: float, x1: float, y1: float, r: float) -> list[float]:
    """Point list for a rounded rectangle (draw with ``smooth=True``)."""
    r = max(0.0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    return [
        x0 + r, y0, x1 - r, y0, x1, y0,
        x1, y0 + r, x1, y1 - r, x1, y1,
        x1 - r, y1, x0 + r, y1, x0, y1,
        x0, y1 - r, x0, y0 + r, x0, y0,
    ]


def draw_round_rect(canvas: tk.Canvas, x0, y0, x1, y1, r, fill, outline="", width=1, tags=()):
    pts = round_rect_points(x0, y0, x1, y1, r)
    return canvas.create_polygon(*pts, smooth=True, splinesteps=18, fill=fill,
                                 outline=outline, width=width, tags=tags)


def draw_capsule(canvas: tk.Canvas, x0, y0, x1, y1, fill, tags=()):
    """A perfect pill — used for progress bars and chips' dots."""
    h = y1 - y0
    r = h / 2 if h < (x1 - x0) else (x1 - x0) / 2
    return draw_round_rect(canvas, x0, y0, x1, y1, r, fill, tags=tags)


def draw_gradient_capsule(canvas: tk.Canvas, x0, y0, x1, y1, color_a, color_b,
                          strips: int = 48, tags=()):
    """Capsule filled with a horizontal gradient, faked with thin strips."""
    if x1 - x0 < 1:
        return
    n = max(2, min(strips, int(x1 - x0)))
    w = (x1 - x0) / n
    for i in range(n):
        t = i / (n - 1)
        col = T.mix(color_a, color_b, t)
        sx0, sx1 = x0 + i * w, x0 + (i + 1) * w + 1
        # rounded caps on the first/last strip
        if i == 0 or i == n - 1:
            draw_round_rect(canvas, sx0, y0, sx1, y1, (y1 - y0) / 2, col, tags=tags)
        else:
            canvas.create_rectangle(sx0, y0, sx1, y1, fill=col, outline=col, tags=tags)


class CanvasWidget(tk.Canvas):
    """Base: transparent-ish canvas whose background matches its parent."""

    def __init__(self, master, animator: Optional[logic.Animator] = None,
                 width=10, height=10, bg=None, **kw):
        kw.pop("highlightthickness", None)
        kw.pop("bd", None)
        super().__init__(master, width=width, height=height,
                         bg=bg or widget_bg(master, T.BG), highlightthickness=0, bd=0, **kw)
        self.anim = animator
        self._animated: list[logic.Tween] = []

    # ---- animation plumbing
    def anim_to(self, attr_setter: Callable[[float], None], duration: float = T.D_BASE / 1000,
                easing=logic.out_cubic, **tween_kw):
        """Animate a value on the shared loop (or snap when motion is off)."""
        if self.anim is None or duration <= 0:
            attr_setter(1.0)
            return None
        tw = logic.Tween(duration, easing=easing, on_update=attr_setter, **tween_kw)
        self.anim.add(tw)
        return tw

    def motion(self, on: bool) -> None:
        self.anim = self.anim if on else None


# --------------------------------------------------------------------------
# card / panel
# --------------------------------------------------------------------------

class Card(CanvasWidget):
    """Rounded panel that hosts real widgets in ``.body``.

    ``hug=True`` (default) sizes itself to its content; ``hug=False`` fills the
    space its geometry manager gives it (used for the chat log).
    """

    def __init__(self, master, animator=None, radius=T.RADIUS_LG, fill=T.SURFACE,
                 border=T.BORDER, padding=T.PAD, hug=True, bg=None, **kw):
        super().__init__(master, bg=bg or widget_bg(master), highlightthickness=0,
                         bd=0, **kw)
        self.anim = animator
        self.radius, self.fill, self.border, self.padding, self.hug = \
            radius, fill, border, padding, hug
        self._glow = 0.0
        self._pulse_tw = None
        self.body = tk.Frame(self, bg=fill)
        self._win = self.create_window(padding, padding, anchor="nw", window=self.body)
        self._sizing = False
        self.bind("<Configure>", self._on_configure)
        self.body.bind("<Configure>", self._on_body)

    # ------------------------------------------------------------------
    def _redraw(self) -> None:
        self.delete("bgshape")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 2 or h < 2:
            return
        outline = T.mix(self.border, T.ACCENT, self._glow * 0.85)
        draw_round_rect(self, 1, 1, w - 1, h - 1, self.radius, self.fill,
                        outline=outline, width=1.4, tags="bgshape")
        self.tag_lower("bgshape")

    def _on_configure(self, _e=None) -> None:
        w, h = self.winfo_width(), self.winfo_height()
        inner_w = max(1, w - 2 * self.padding)
        inner_h = max(1, h - 2 * self.padding)
        self.coords(self._win, self.padding, self.padding)
        if self.hug:
            self.itemconfigure(self._win, width=inner_w)
        else:
            self.itemconfigure(self._win, width=inner_w, height=inner_h)
        self._redraw()

    def _on_body(self, _e=None) -> None:
        """Hug mode: keep the card exactly as big as its content."""
        if not self.hug or self._sizing:
            return
        need_w = self.body.winfo_reqwidth() + 2 * self.padding
        need_h = self.body.winfo_reqheight() + 2 * self.padding
        if abs(need_h - int(self["height"])) > 1 or abs(need_w - int(self["width"])) > 1:
            self._sizing = True
            try:
                self.configure(width=need_w, height=need_h)
            finally:
                self._sizing = False

    # ------------------------------------------------------------------
    def set_fill(self, color: str) -> None:
        self.fill = color
        self.body.configure(bg=color)
        self._redraw()

    def glow(self, t: float) -> None:
        """0 → idle border, 1 → accent border (used to highlight busy cards)."""
        self._glow = t
        self._redraw()

    def pulse_glow(self, on: bool = True) -> None:
        """Breathing border while THANS is working."""
        if self.anim is None:
            return
        if self._pulse_tw is not None:
            if self.anim is not None:
                self.anim.stop(self._pulse_tw)
            else:
                self._pulse_tw.stop()
            self._pulse_tw = None
        if not on:
            self.glow(0.0)
            return
        self._pulse_tw = logic.pulse(1.6, on_update=self.glow)
        self.anim.add(self._pulse_tw)


# --------------------------------------------------------------------------
# buttons
# --------------------------------------------------------------------------

class RoundedButton(CanvasWidget):
    """Flat rounded button with animated hover/press and optional gradient."""

    def __init__(self, master, text="", command=None, animator=None,
                 glyph="", primary=False, radius=T.RADIUS_SM, pad_x=14, pad_y=8,
                 font=None, bg=None, width=None, subtle=False):
        self._font = font or ("TkDefaultFont", T.SIZE_BODY)
        super().__init__(master, bg=bg or widget_bg(master), highlightthickness=0, bd=0,
                         cursor="hand2")
        self.anim = animator
        self.command = command
        self.primary = primary
        self.subtle = subtle
        self.radius = radius
        self._text = text
        self._glyph = glyph
        self._hover = 0.0
        self._press = 0.0
        self._pressed = False
        self._enabled = True
        self._bg_color = bg or widget_bg(master)

        # measure
        f = tkfont.Font(font=self._font)
        label = (f"{glyph}  {text}" if glyph and text else (glyph or text))
        tw = f.measure(label)
        th = f.metrics("linespace")
        self._w = width or (tw + 2 * pad_x)
        self._h = th + 2 * pad_y
        self.configure(width=self._w, height=self._h)
        self._draw()

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    # ---- look
    def _palette(self) -> tuple[str, str]:
        """(fill, fg) for the current interaction state."""
        if not self._enabled:
            return T.mix(T.SURFACE, T.BG, 0.35), T.FG_FAINT
        if self.primary:
            base, top = T.ACCENT, T.ACCENT2
            fill = T.mix(base, top, 0.35 + 0.25 * self._hover)
            fill = T.mix(fill, "#ffffff", 0.10 * self._press)
            fill = T.mix(fill, T.BG, 0.25 * (1 - self._enabled))
            return fill, "#ffffff"
        base = T.SURFACE_HI if self.subtle else T.SURFACE
        fill = T.mix(base, T.ACCENT, 0.16 * self._hover)
        fill = T.mix(fill, "#000000", 0.12 * self._press)
        fg = T.mix(T.FG_DIM if not self.subtle else T.FG, T.FG, 0.5 + 0.5 * self._hover)
        return fill, fg

    def _draw(self) -> None:
        self.delete("all")
        w, h = self._w, self._h
        fill, fg = self._palette()
        outline = T.mix(T.BORDER, T.ACCENT, 0.5 * self._hover) if not self.primary else ""
        if self.primary and self._press > 0.02:
            # soft "pressed" halo
            draw_round_rect(self, 1, 2, w - 1, h, self.radius + 2,
                            T.mix(T.ACCENT_LO, T.BG, 0.55))
        draw_round_rect(self, 1, 1, w - 1, h - 1, self.radius, fill,
                        outline=outline or "", width=1.2)
        label = (f"{self._glyph}  {self._text}" if self._glyph and self._text
                 else (self._glyph or self._text))
        self.create_text(w / 2 + (1 if self._press > 0.4 else 0), h / 2 + (1 if self._press > 0.4 else 0),
                         text=label, fill=fg, font=self._font)

    def configure_text(self, text: str) -> None:
        self._text = text
        self._draw()

    def configure_glyph(self, glyph: str) -> None:
        self._glyph = glyph
        self._draw()

    def set_enabled(self, on: bool) -> None:
        self._enabled = bool(on)
        self.configure(cursor="hand2" if on else "arrow")
        self._draw()

    # ---- interaction
    def _on_enter(self, _e=None):
        if not self._enabled:
            return
        start = self._hover
        self.anim_to(lambda v: self._set_hover(logic.lerp(start, 1.0, v)), 0.12)

    def _on_leave(self, _e=None):
        start = self._hover
        self.anim_to(lambda v: self._set_hover(logic.lerp(start, 0.0, v)), 0.16)

    def _set_hover(self, v):
        self._hover = v
        self._draw()

    def _on_press(self, _e=None):
        if not self._enabled:
            return
        self._pressed = True                     # state, not the tween value:
        self.anim_to(lambda v: self._set_press(v), 0.09)   # fast clicks still count

    def _on_release(self, _e=None):
        if not self._enabled:
            self._pressed = False
            return
        start = self._press
        self.anim_to(lambda v: self._set_press(logic.lerp(start, 0.0, v)), 0.12)
        if self._pressed and self.command:
            self._pressed = False
            self.command()
        self._pressed = False

    def _set_press(self, v):
        self._press = v
        self._draw()


class IconButton(RoundedButton):
    """Round icon-only button (mic, settings, undo…)."""

    def __init__(self, master, glyph="", command=None, animator=None, size=T.HIT,
                 primary=False, ring=False, **kw):
        self.ring = ring
        super().__init__(master, text="", glyph=glyph, command=command, animator=animator,
                         primary=primary, radius=size // 2, pad_x=0, pad_y=0,
                         width=size, **kw)
        f = tkfont.Font(font=self._font)
        label = glyph or " "
        tw = f.measure(label)
        self._w = max(size, tw + 18)
        self._h = size
        self.configure(width=self._w, height=self._h)
        self._draw()

    def _draw(self):
        super()._draw()
        if self.ring:
            w, h = self._w, self._h
            col = T.mix(T.ACCENT, T.ACCENT2, self._hover)
            self.create_oval(2, 2, w - 2, h - 2, outline=col, width=1.6,
                             dash=(3, 3))


# --------------------------------------------------------------------------
# chip (status pill) + dot
# --------------------------------------------------------------------------

class Chip(CanvasWidget):
    """Status pill: coloured dot + label, animated on state change, clickable."""

    def __init__(self, master, text="", state="off", animator=None, command=None,
                 font=None, bg=None, dot_r=3.5):
        self._font = font or ("TkDefaultFont", T.SIZE_SMALL)
        super().__init__(master, bg=bg or widget_bg(master), highlightthickness=0, bd=0,
                         cursor="hand2" if command else "arrow")
        self.anim = animator
        self.command = command
        self.state = state
        self._text = text
        self._dot_r = dot_r
        self._t = 1.0              # animation progress of the current colour
        self._from = T.status_color(state)
        self._hover = 0.0
        self._measure()
        self._draw()
        self.bind("<Button-1>", lambda e: self.command() if self.command else None)
        self.bind("<Enter>", lambda e: self._set_hover(1))
        self.bind("<Leave>", lambda e: self._set_hover(0))

    def _measure(self):
        f = tkfont.Font(font=self._font)
        self._w = f.measure(self._text) + 30
        self._h = f.metrics("linespace") + 12
        self.configure(width=self._w, height=self._h)

    def _set_hover(self, v):
        self._hover = v
        self._draw()

    def set(self, text: str | None = None, state: str | None = None) -> None:
        if text is not None and text != self._text:
            self._text = text
            self._measure()
        if state is not None and state != self.state:
            self._from = T.mix(self._from, T.status_color(self.state), self._t) \
                if self._t < 1 else T.status_color(self.state)
            self.state = state
            self._t = 0.0
            self.anim_to(lambda v: self._dot_progress(v), 0.28)
        self._draw()

    def _dot_progress(self, v):
        self._t = v
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = self._w, self._h
        target = T.status_color(self.state)
        dot = T.mix(self._from, target, self._t)
        fill = T.mix(T.SURFACE, T.SURFACE_HI, self._hover)
        draw_round_rect(self, 1, 1, w - 1, h - 1, h / 2, fill,
                        outline=T.mix(T.BORDER, T.ACCENT, 0.4 * self._hover), width=1)
        cy = h / 2
        if self.state in ("listening", "busy", "working"):
            # breathing halo behind the dot
            self.create_oval(10 - self._dot_r * 1.9, cy - self._dot_r * 1.9,
                             10 + self._dot_r * 1.9, cy + self._dot_r * 1.9,
                             outline=T.mix(fill, dot, 0.65), width=1.2)
        self.create_oval(10 - self._dot_r, cy - self._dot_r, 10 + self._dot_r,
                         cy + self._dot_r, fill=dot, outline="")
        self.create_text(21, cy, anchor="w", text=self._text,
                         fill=T.mix(T.FG_DIM, T.FG, 0.3 + 0.7 * self._hover),
                         font=self._font)


# --------------------------------------------------------------------------
# switch
# --------------------------------------------------------------------------

class Switch(CanvasWidget):
    """iOS-style toggle with an animated knob."""

    W, H = 44, 24

    def __init__(self, master, value=False, command=None, animator=None, bg=None):
        super().__init__(master, width=self.W, height=self.H, bg=bg or widget_bg(master),
                         highlightthickness=0, bd=0, cursor="hand2")
        self.anim = animator
        self.command = command
        self.value = bool(value)
        self._t = 1.0 if value else 0.0
        self._draw()
        self.bind("<Button-1>", self._toggle)

    def _toggle(self, _e=None):
        self.set(not self.value, notify=True)

    def set(self, value: bool, notify: bool = False) -> None:
        value = bool(value)
        target = 1.0 if value else 0.0
        start = self._t
        self.value = value
        self.anim_to(lambda v: self._progress(logic.lerp(start, target, v)), 0.18)
        if notify and self.command:
            self.command(value)

    def _progress(self, v):
        self._t = v
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = self.W, self.H
        track = T.mix(T.mix(T.SURFACE_HI, T.BG, 0.2), T.ACCENT, self._t)
        draw_round_rect(self, 1, 1, w - 1, h - 1, h / 2, track,
                        outline=T.mix(T.BORDER, T.ACCENT, self._t), width=1)
        r = h / 2 - 3
        cx = T.lerp(3 + r, w - 3 - r, self._t)
        cy = h / 2
        self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=T.FG,
                         outline=T.mix(T.FG, "#000000", 0.15))


# --------------------------------------------------------------------------
# progress
# --------------------------------------------------------------------------

class ProgressBar(CanvasWidget):
    """Rounded gradient bar: determinate (0…1) or indeterminate sweep."""

    def __init__(self, master, animator=None, width=220, height=8, bg=None,
                 color_a=T.ACCENT, color_b=T.ACCENT2, track=None):
        super().__init__(master, width=width, height=height, bg=bg or widget_bg(master),
                         highlightthickness=0, bd=0)
        self.anim = animator
        self.color_a, self.color_b = color_a, color_b
        self.track = track or T.mix(T.SURFACE_HI, T.BG, 0.35)
        self._value = 0.0
        self._shown = 0.0
        self._sweep = 0.6
        self._indeterminate = False
        self._sweep_tween = None
        self.bind("<Configure>", lambda e: self._draw())
        self.after(10, self._draw)

    # ---- api
    def set(self, value: float, animate: bool = True) -> None:
        """Set determinate progress (0…1); stops any indeterminate sweep."""
        self.stop_indeterminate()
        target = logic.clamp01(value)
        if not animate or self.anim is None:
            self._value = self._shown = target
            self._draw()
            return
        start = self._shown
        self._value = target
        self.anim_to(lambda v: self._set_shown(logic.lerp(start, target, v)), 0.28)

    def _set_shown(self, v):
        self._shown = v
        self._draw()

    def start_indeterminate(self, period: float = 1.6) -> None:
        """Endless back-and-forth sweep for unknown durations."""
        if self._indeterminate:
            return
        self._indeterminate = True
        if self.anim is None:
            self._draw()
            return
        self._sweep_tween = logic.sweep(period, on_update=self._set_sweep)
        self.anim.add(self._sweep_tween)

    def stop_indeterminate(self) -> None:
        self._indeterminate = False
        if self._sweep_tween is not None:
            if self.anim is not None:
                self.anim.stop(self._sweep_tween)
            else:
                self._sweep_tween.stop()
            self._sweep_tween = None
        self._draw()

    def _set_sweep(self, v):
        self._sweep = v
        self._draw()

    # ---- paint
    def _draw(self):
        if not self.winfo_exists():
            return
        self.delete("all")
        w = max(4, self.winfo_width())
        h = max(4, self.winfo_height())
        draw_capsule(self, 0, 0, w, h, self.track)
        if self._indeterminate:
            span = 0.36
            head = 0.08 + self._sweep * (0.92 - span) + span      # 0.08 → 0.92 smoothly
            x0 = w * max(0.02, head - span)
            x1 = w * min(1.0, head)
            draw_gradient_capsule(self, x0, 0, x1, h, self.color_a, self.color_b)
            return
        if self._shown <= 0.001:
            return
        draw_gradient_capsule(self, 0, 0, max(h, w * self._shown), h,
                              self.color_a, self.color_b)


# --------------------------------------------------------------------------
# thinking dots + listening waveform
# --------------------------------------------------------------------------

class Dots(CanvasWidget):
    """Three dots that breathe in sequence (THANS is thinking)."""

    def __init__(self, master, animator=None, bg=None, color=T.ACCENT, size=22):
        super().__init__(master, width=size, height=size, bg=bg or widget_bg(master),
                         highlightthickness=0, bd=0)
        self.anim = animator
        self.color = color
        self._t = 0.0
        self._running = False
        self._tw = None
        self.bind("<Configure>", lambda e: self._draw())
        self._draw()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        if self.anim is None:
            self._draw()
            return
        self._tw = logic.sweep(1.1, on_update=self._tick)
        self.anim.add(self._tw)

    def stop(self) -> None:
        self._running = False
        if self._tw is not None:
            if self.anim is not None:
                self.anim.stop(self._tw)
            else:
                self._tw.stop()
            self._tw = None
        self._draw()

    def _tick(self, v):
        self._t = v
        self._draw()

    def _draw(self):
        if not self.winfo_exists():
            return
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4:
            return
        n = 3
        r = min(h, w) / 12
        gap = (w - 2 * r) / (n + 1)
        for i in range(n):
            phase = (self._t * 2 - i * 0.22) % 1.0
            k = 0.5 - 0.5 * math.cos(phase * 2 * math.pi)
            cx = gap * (i + 1) + r * (2 * i)
            cy = h / 2
            rr = r * (0.7 + 0.55 * k)
            col = T.mix(T.mix(self.color, T.BG, 0.65), self.color, k)
            self.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, fill=col, outline="")


class Waveform(CanvasWidget):
    """Mic level bars — idle: calm sine; listening: follows the real level."""

    BARS = 9

    def __init__(self, master, animator=None, bg=None, color=T.ACCENT2, width=70, height=22):
        super().__init__(master, width=width, height=height, bg=bg or widget_bg(master),
                         highlightthickness=0, bd=0)
        self.anim = animator
        self.color = color
        self._level = 0.0
        self._t = 0.0
        self._active = False
        self._tw = None
        self._draw()

    def start(self) -> None:
        if self._active:
            return
        self._active = True
        if self.anim is not None:
            self._tw = logic.sweep(1.8, on_update=self._tick)
            self.anim.add(self._tw)
        self._draw()

    def stop(self) -> None:
        self._active = False
        self._level = 0.0
        if self._tw is not None:
            if self.anim is not None:
                self.anim.stop(self._tw)
            else:
                self._tw.stop()
            self._tw = None
        self._draw()

    def set_level(self, level: float) -> None:
        self._level = logic.clamp01(level)
        self._draw()

    def _tick(self, v):
        self._t = v
        self._draw()

    def _draw(self):
        if not self.winfo_exists():
            return
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 6:
            return
        n = self.BARS
        bw = max(2.0, w / (n * 2.1))
        space = (w - n * bw) / (n + 1)
        for i in range(n):
            if self._active:
                wave = 0.5 + 0.5 * math.sin((i / n) * 3.1 + self._t * 6.28)
                amp = 0.22 + 0.78 * self._level * wave
            else:
                amp = 0.12
            bh = max(2.0, h * amp)
            x = space * (i + 1) + bw * i
            col = T.mix(T.mix(self.color, T.BG, 0.6), self.color, amp)
            draw_capsule(self, x, (h - bh) / 2, x + bw, (h + bh) / 2, col)


# --------------------------------------------------------------------------
# toasts
# --------------------------------------------------------------------------

class Toaster:
    """Stacking, self-dismissing toasts pinned to the bottom of ``host``."""

    def __init__(self, host: tk.Misc, animator: logic.Animator,
                 font=None, offset_y: int = 58):
        self.host = host
        self.anim = animator
        self.font = font or ("TkDefaultFont", T.SIZE_SMALL)
        self.offset_y = offset_y
        self._live: list[tk.Canvas] = []

    def show(self, text: str, kind: str = "info", ms: int = 2600) -> None:
        f = tkfont.Font(font=self.font)
        tw = f.measure(text)
        th = f.metrics("linespace")
        w, h = tw + 46, th + 18
        color = {"ok": T.OK, "warn": T.WARN, "error": T.ERR}.get(kind, T.ACCENT)
        c = tk.Canvas(self.host, width=w, height=h, bg=widget_bg(self.host, T.BG_RAISED),
                      highlightthickness=0, bd=0)
        fill = T.mix(T.SURFACE, T.BG, 0.25)
        draw_round_rect(c, 1, 1, w - 1, h - 1, h / 2, fill, outline=T.mix(T.BORDER, color, 0.6),
                        width=1.2)
        c.create_oval(14, h / 2 - 3, 20, h / 2 + 3, fill=color, outline="")
        c.create_text(28, h / 2, anchor="w", text=text, fill=T.FG, font=self.font)

        index = len(self._live)
        self._live.append(c)
        c.place(relx=0.5, y=T.PAD + index * (h + 6), anchor="n")
        start_y = -h
        end_y = T.PAD + index * (h + 6)
        c.place_configure(y=start_y)
        self.anim.add(logic.Tween(0.26, easing=logic.out_cubic,
                                  on_update=lambda v, cc=c, a=start_y, b=end_y:
                                  self._slide(cc, a, b, v)))
        c.after(ms, lambda cc=c: self._dismiss(cc))

    def _slide(self, c, a, b, v):
        if not c.winfo_exists():
            return
        c.place_configure(y=logic.lerp(a, b, v))

    def _dismiss(self, c) -> None:
        if not c.winfo_exists():
            self._forget(c)
            return
        y0 = c.winfo_y()
        self.anim.add(logic.Tween(0.22, on_update=lambda v, cc=c, a=y0: self._slide(cc, a, -cc.winfo_height(), v),
                                  on_done=lambda cc=c: self._forget(cc)))

    def _forget(self, c) -> None:
        if c in self._live:
            self._live.remove(c)
        try:
            c.destroy()
        except Exception:
            pass
        self._restack()

    def _restack(self) -> None:
        """Keep the remaining toasts tidy after one leaves."""
        for i, c in enumerate(self._live):
            if not c.winfo_exists():
                continue
            target = T.PAD + i * (int(c["height"]) + 6)
            y0 = c.winfo_y()
            self.anim.add(logic.Tween(0.18, on_update=lambda v, cc=c, a=y0, b=target:
                                      self._slide(cc, a, b, v)))


# --------------------------------------------------------------------------
# slide-in settings panel with scrim
# --------------------------------------------------------------------------

class SlidePanel(tk.Frame):
    """Right-edge panel that slides in over the content (with a dim scrim)."""

    def __init__(self, host: tk.Frame, width: int = 340, animator=None, bg=T.BG_RAISED):
        self.host = host
        self.anim = animator
        self.width = width
        self.scrim = tk.Frame(host, bg=T.SCRIM)
        super().__init__(host, bg=bg, width=width)
        self._open = False
        self._start_x = 0

    def open(self, focus: Optional[tk.Widget] = None) -> None:
        if self._open:
            return
        self._open = True
        h = self.host.winfo_height() or 600
        self.scrim.place(x=0, y=0, relwidth=1, relheight=1)
        self.scrim.lift()
        self.scrim.configure(bg=T.mix(T.BG, T.SCRIM, 0.55))
        self.scrim.bind("<Button-1>", lambda e: self.close())
        self.place(x=self.host.winfo_width(), y=0, width=self.width, height=h)
        self.lift()
        if self.anim is not None:
            self.anim.add(logic.Tween(T.D_BASE / 1000, easing=logic.out_quart,
                                      on_update=self._slide_x))
        else:
            self.place_configure(x=self.host.winfo_width() - self.width)
        if focus is not None:
            self.after(260, lambda: focus.focus_set() if focus.winfo_exists() else None)

    def _slide_x(self, v):
        if not self.winfo_exists():
            return
        w = self.host.winfo_width()
        x = logic.lerp(w, w - self.width, v)
        self.place_configure(x=x)

    def close(self) -> None:
        if not self._open:
            return
        self._open = False
        if self.anim is not None:
            self.anim.add(logic.Tween(T.D_BASE / 1000, easing=logic.out_quart,
                                      on_update=lambda v: self._slide_out(v)))
        else:
            self._slide_out(1.0)

    def _slide_out(self, v):
        if not self.winfo_exists():
            return
        w = self.host.winfo_width()
        self.place_configure(x=logic.lerp(w - self.width, w, v))
        if v >= 1.0:
            self.place_forget()
            self.scrim.place_forget()
            try:
                self.scrim.configure(bg=T.BG)
            except Exception:
                pass

    @property
    def is_open(self) -> bool:
        return self._open


# --------------------------------------------------------------------------
# tooltip
# --------------------------------------------------------------------------

class Tooltip:
    """Small delay-then-appear hint (one instance per widget)."""

    def __init__(self, widget: tk.Widget, text: str, delay: int = 420, font=None):
        self.widget, self.text, self.delay = widget, text, delay
        self.font = font or ("TkDefaultFont", T.SIZE_TINY)
        self._after_id = None
        self._tip: Optional[tk.Toplevel] = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<Button-1>", self._hide, add="+")

    def _schedule(self, _e=None):
        self._after_id = self.widget.after(self.delay, self._show)

    def _show(self):
        if self._tip is not None or not self.widget.winfo_exists():
            return
        try:
            x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        except Exception:
            return
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        tip.configure(bg=T.BORDER_HI)
        lbl = tk.Label(tip, text=self.text, bg=T.SURFACE_HI, fg=T.FG,
                       font=self.font, padx=8, pady=4)
        lbl.pack(padx=1, pady=1)
        tip.update_idletasks()
        w = tip.winfo_reqwidth()
        tip.wm_geometry(f"+{max(4, x - w // 2)}+{y}")
        self._tip = tip

    def _hide(self, _e=None):
        if self._after_id:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        if self._tip is not None:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None


# --------------------------------------------------------------------------
# particle burst (small celebration when a big job lands)
# --------------------------------------------------------------------------

class Burst(CanvasWidget):
    """One-shot confetti-ish burst overlay; removes itself when finished."""

    def __init__(self, host: tk.Misc, animator: logic.Animator, size=(360, 160),
                 colors=(T.ACCENT, T.ACCENT2, T.OK, T.WARN)):
        super().__init__(host, width=size[0], height=size[1],
                         bg=widget_bg(host, T.BG), highlightthickness=0, bd=0)
        self.anim = animator
        self.w, self.h = size
        self.colors = colors
        self._parts: list[dict] = []
        self._t = 0.0
        import random
        cx, cy = self.w / 2, self.h * 0.62
        for i in range(22):
            ang = random.uniform(-2.5, -0.65)
            spd = random.uniform(120, 320)
            self._parts.append({
                "x": cx, "y": cy,
                "vx": spd * math.cos(ang),
                "vy": spd * math.sin(ang),
                "r": random.uniform(1.6, 3.4),
                "c": random.choice(self.colors),
            })
        self.bind("<Configure>", lambda e: self._draw())
        self._draw()

    def fire(self, duration: float = 1.05) -> None:
        if self.anim is None:
            self.destroy()
            return
        self.anim.add(logic.Tween(duration, easing=logic.linear,
                                  on_update=self._step,
                                  on_done=self._done))

    def _step(self, v):
        dt = 1 / 60.0
        for p in self._parts:
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            p["vy"] += 520 * dt          # gravity
        self._t = v
        self._draw()

    def _draw(self):
        if not self.winfo_exists():
            return
        self.delete("all")
        fade = 1.0 - self._t
        for p in self._parts:
            r = p["r"] * max(0.2, fade)
            col = T.mix(T.BG, p["c"], max(0.0, fade))
            self.create_oval(p["x"] - r, p["y"] - r, p["x"] + r, p["y"] + r,
                             fill=col, outline="")

    def _done(self, _v=None):
        try:
            self.destroy()
        except Exception:
            pass

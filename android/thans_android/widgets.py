"""Kivy widgets for THANS Android: rounded cards, chips, animated buttons,
typing dots, sweep bar, toasts and message bubbles.

Kivy has real alpha, so unlike the desktop (which shades colours to fake
fades) everything here animates ``opacity``/``height``/``font_size`` with the
shared durations from :mod:`theme`. Every animation goes through
:func:`animate`, which is a no-op when the user turns motion off.
"""
from __future__ import annotations

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.graphics import Color, Line, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.properties import (BooleanProperty, ListProperty, NumericProperty,
                             StringProperty)
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import ButtonBehavior
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from . import theme as T


def animate(widget, duration: float, **props) -> Animation:
    """Animate ``props`` (0 duration when motion is disabled)."""
    anim = Animation(duration=max(0.0, duration), t="out_cubic", **props)
    anim.start(widget)
    return anim


def sequence(*anims) -> Animation:
    """Chain animations: ``sequence(a, b, c).start(widget)``."""
    out = anims[0]
    for nxt in anims[1:]:
        out &= nxt
    return out


# --------------------------------------------------------------------------
# surfaces
# --------------------------------------------------------------------------

class Card(BoxLayout):
    """Rounded surface with an optional border — the building block of the UI."""

    fill = ListProperty(list(T.SURFACE))
    border = ListProperty(list(T.BORDER))
    radius = NumericProperty(dp(16))
    border_width = NumericProperty(1.1)

    def __init__(self, **kw):
        super().__init__(**kw)
        with self.canvas.before:
            self._bg_color = Color(*self.fill)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size,
                                        radius=[self.radius])
            self._ln_color = Color(*self.border)
            self._ln = Line(width=self.border_width, rounded_rectangle=(
                self.x, self.y, self.width, self.height, self.radius))
        self.bind(pos=self._sync, size=self._sync,
                  fill=self._sync_fill, border=self._sync_border)

    def _sync(self, *_a):
        self._bg.pos, self._bg.size = self.pos, self.size
        self._bg.radius = [self.radius]
        self._ln.rounded_rectangle = (self.x, self.y, self.width, self.height,
                                      self.radius)

    def _sync_fill(self, *_a):
        self._bg_color.rgba = self.fill

    def _sync_border(self, *_a):
        self._ln_color.rgba = self.border

    def glow(self, on: bool) -> None:
        """Accent border while THANS is working."""
        target = list(T.mix(T.BORDER, T.ACCENT, 0.85) if on else T.BORDER)
        animate(self._ln_color, T.D_BASE, rgba=target)


class Panel(Card):
    """Card used for the dashboard / info blocks (slightly darker fill)."""
    fill = ListProperty(list(T.SURFACE))


# --------------------------------------------------------------------------
# buttons
# --------------------------------------------------------------------------

class RoundedButton(ButtonBehavior, Label):
    """Flat rounded button with press feedback and an optional gradient look."""

    primary = BooleanProperty(False)
    subtle = BooleanProperty(False)
    radius = NumericProperty(dp(12))
    fill = ListProperty(list(T.SURFACE))
    text_color = ListProperty(list(T.FG))
    glyph = StringProperty("")

    def __init__(self, **kw):
        super().__init__(**kw)
        if self.glyph:
            self.text = f"{self.glyph}  {self.text}" if self.text else self.glyph
        self._apply_palette()
        with self.canvas.before:
            self._bg_color = Color(*self.fill)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size,
                                        radius=[self.radius])
        self.bind(pos=self._sync, size=self._sync, state=self._on_state)

    def _apply_palette(self):
        if self.primary:
            self.fill = list(T.mix(T.ACCENT, T.ACCENT2, 0.35))
            self.text_color = list(T.WHITE)
        elif self.subtle:
            self.fill = list(T.SURFACE_HI)
            self.text_color = list(T.FG)
        else:
            self.fill = list(T.SURFACE)
            self.text_color = list(T.FG_DIM)

    def _sync(self, *_a):
        self._bg.pos, self._bg.size = self.pos, self.size
        self._bg.radius = [self.radius]
        self._bg_color.rgba = self.fill

    def _on_state(self, _widget, state):
        target = T.mix(T.ACCENT, T.ACCENT2, 0.45) if (self.primary and state == "down") \
            else T.SURFACE_HI if (state == "down" and not self.primary) else self.fill
        if state == "down":
            self._bg_color.rgba = list(target if self.primary else T.mix(T.SURFACE_HI, T.ACCENT, 0.18))
            animate(self, T.D_FAST, opacity=0.86)
        else:
            self._bg_color.rgba = list(self.fill)
            animate(self, T.D_FAST, opacity=1.0)


class CircleButton(RoundedButton):
    """Round icon button (mic, send) — radius = half the height."""

    def __init__(self, **kw):
        kw.setdefault("radius", dp(26))
        super().__init__(**kw)
        self.bind(size=self._circle)

    def _circle(self, *_a):
        self.radius = min(self.width, self.height) / 2.0
        self._bg.radius = [self.radius]


class MicButton(ButtonBehavior, Widget):
    """Mic button with a live level ring that pulses while listening."""

    listening = BooleanProperty(False)
    level = NumericProperty(0.0)

    def __init__(self, **kw):
        super().__init__(**kw)
        with self.canvas:
            self._glow_color = Color(*T.fade("#5b8cff", 0.0))
            self._glow = Line(width=dp(2), rounded_rectangle=(0, 0, 0, 0, dp(26)))
            self._dot_color = Color(*T.ACCENT)
            self._dot = RoundedRectangle(radius=[dp(26)])
        self.bind(pos=self._sync, size=self._sync)
        Clock.schedule_interval(self._tick, 1 / 30.0)

    def _sync(self, *_a):
        self._dot.pos, self._dot.size = self.pos, self.size
        self._dot.radius = [min(self.width, self.height) / 2]
        pad = dp(3)
        self._glow.rounded_rectangle = (self.x + pad, self.y + pad,
                                        self.width - 2 * pad, self.height - 2 * pad,
                                        (self.width - 2 * pad) / 2)

    def _tick(self, _dt):
        import math
        base = 0.35 if self.listening else 0.0
        wobble = 0.3 * (0.5 + 0.5 * math.sin(Clock.get_boottime() * 4.0)) if self.listening else 0.0
        alpha = min(1.0, base + wobble + self.level * 0.35)
        self._glow_color.a = alpha
        col = T.ACCENT2 if self.listening else T.ACCENT
        self._dot_color.rgba = (col[0], col[1], col[2], 1.0)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            animate(self, T.D_FAST, opacity=0.85)
            return super().on_touch_down(touch)
        return False

    def on_touch_up(self, touch):
        if self.collide_point(*touch.pos):
            animate(self, T.D_FAST, opacity=1.0)
        return super().on_touch_up(touch)


# --------------------------------------------------------------------------
# indicators
# --------------------------------------------------------------------------

class TypingDots(Widget):
    """Three dots that breathe in sequence while THANS is thinking."""

    color = ListProperty(list(T.ACCENT))
    running = BooleanProperty(False)

    def __init__(self, **kw):
        super().__init__(**kw)
        self._colors: list[Color] = []
        self._dots: list[RoundedRectangle] = []
        with self.canvas:
            for _ in range(3):
                self._colors.append(Color(*self.color))
                self._dots.append(RoundedRectangle(radius=[dp(3)]))
        self._ev = None
        self.bind(pos=self._sync, size=self._sync, running=self._on_running)
        self._sync()

    def _on_running(self, _w, value):
        if value and self._ev is None:
            self._ev = Clock.schedule_interval(self._tick, 1 / 30.0)
        elif not value and self._ev is not None:
            self._ev.cancel()
            self._ev = None
            self._sync()

    def _sync(self, *_a):
        r = max(dp(2.5), min(self.height, self.width / 8.0))
        for i, instr in enumerate(self._dots):
            instr.pos = (self.x + i * (2.4 * r), self.center_y - r)
            instr.size = (2 * r, 2 * r)
            instr.radius = [r]

    def _tick(self, _dt):
        import math
        t = Clock.get_boottime()
        for i, color in enumerate(self._colors):
            phase = t * 3.4 - i * 0.5
            k = 0.5 + 0.5 * math.sin(phase) if self.running else 0.25
            color.rgba = (self.color[0], self.color[1], self.color[2],
                          max(0.18, k) if self.running else 0.25)


class SweepBar(Widget):
    """Thin gradient sweep used for busy/loading states and the boot screen."""

    active = BooleanProperty(False)
    color_a = ListProperty(list(T.ACCENT))
    color_b = ListProperty(list(T.ACCENT2))

    def __init__(self, **kw):
        super().__init__(**kw)
        with self.canvas:
            self._track = Color(*T.mix(T.SURFACE_HI, T.BG, 0.25))
            self._track_r = RoundedRectangle(radius=[dp(2)])
            self._fill = Color(*self.color_a)
            self._fill_r = RoundedRectangle(radius=[dp(2)])
        self.bind(pos=self._sync, size=self._sync, active=self._on_active)
        self._t = 0.0
        self._ev = None
        self._sync()

    def _sync(self, *_a):
        self._track_r.pos, self._track_r.size = self.pos, self.size
        self._track_r.radius = [self.height / 2.0]
        self._fill_r.radius = [self.height / 2.0]

    def _on_active(self, _w, value):
        if value and self._ev is None:
            self._ev = Clock.schedule_interval(self._tick, 1 / 60.0)
        elif not value and self._ev is not None:
            self._ev.cancel()
            self._ev = None
            self._fill_color_off()

    def _tick(self, dt):
        if not self.active or self.width <= 0:
            self._fill_color_off()
            return
        self._t = (self._t + dt / 1.5) % 1.0
        span = self.width * 0.34
        x = self.x + self._t * (self.width - span)
        self._fill_r.pos = (x, self.y)
        self._fill_r.size = (span, self.height)
        (r1, g1, b1, _), (r2, g2, b2, _) = self.color_a, self.color_b
        mid = self._t
        self._fill.rgba = (r1 + (r2 - r1) * mid, g1 + (g2 - g1) * mid,
                           b1 + (b2 - b1) * mid, 1.0)

    def _fill_color_off(self):
        self._fill_r.size = (0, self.height)


class Chip(ButtonBehavior, Label):
    """Small status pill: dot + label (tap to act)."""

    dot_color = ListProperty(list(T.FG_FAINT))
    fill = ListProperty(list(T.SURFACE))

    def __init__(self, **kw):
        super().__init__(**kw)
        with self.canvas.before:
            self._bg_color = Color(*self.fill)
            self._bg = RoundedRectangle(radius=[self.height / 2.0])
            self._dot_color = Color(*self.dot_color)
            self._dot = RoundedRectangle(radius=[dp(4)])
        self.bind(pos=self._sync, size=self._sync, dot_color=self._sync_dot)

    def _sync(self, *_a):
        self._bg.pos, self._bg.size = self.pos, self.size
        self._bg.radius = [self.height / 2.0]
        r = dp(3.2)
        self._dot.pos = (self.x + dp(8), self.center_y - r)
        self._dot.size = (2 * r, 2 * r)
        self._dot.radius = [r]

    def _sync_dot(self, *_a):
        self._dot_color.rgba = self.dot_color

    def set_state(self, text: str | None = None, color=None) -> None:
        if text is not None:
            self.text = text
        if color is not None:
            self.dot_color = list(color)


class Toast(Label):
    """Transient notice that slides in from the top and fades away."""

    def __init__(self, text="", kind="info", **kw):
        color = {"ok": T.OK, "warn": T.WARN, "error": T.ERR}.get(kind, T.ACCENT)
        super().__init__(text=text, **kw)
        self.opacity = 0.0
        with self.canvas.before:
            self._bg_color = Color(*T.mix(T.SURFACE, T.BG, 0.25))
            self._bg = RoundedRectangle(radius=[dp(14)])
            self._dot_color = Color(*color)
            self._dot = RoundedRectangle(radius=[dp(3)])
        self.bind(pos=self._sync, size=self._sync)
        self.bind(texture_size=lambda *a: self._sync())

    def _sync(self, *_a):
        self._bg.pos, self._bg.size = self.pos, self.size
        self._bg.radius = [self.height / 2.0]
        self._dot.pos = (self.x + dp(10), self.center_y - dp(3))
        self._dot.size = (dp(6), dp(6))

    def show(self, duration: float = 2.6, on_done=None) -> None:
        animate(self, T.D_BASE, opacity=1.0)
        Clock.schedule_once(lambda _dt: self._hide(on_done), duration)

    def _hide(self, on_done=None) -> None:
        anim = Animation(opacity=0.0, duration=T.D_BASE, t="out_cubic")
        if on_done:
            anim.bind(on_complete=lambda *_: on_done())
        anim.start(self)


# --------------------------------------------------------------------------
# chat bubbles
# --------------------------------------------------------------------------

class Bubble(BoxLayout):
    """One message: sender rail + wrapped text, animates open on arrival."""

    who = StringProperty("THANS")
    body = StringProperty("")
    kind = StringProperty("thans")          # thans | you | system | error
    fill = ListProperty(list(T.SURFACE))
    text_color = ListProperty(list(T.FG))
    rail = ListProperty(list(T.ACCENT))

    def __init__(self, who: str, body: str, kind: str = "thans", **kw):
        kw.setdefault("orientation", "vertical")
        kw.setdefault("size_hint_y", None)
        kw.setdefault("padding", (dp(12), dp(9), dp(12), dp(9)))
        kw.setdefault("spacing", dp(3))
        super().__init__(**kw)
        self.who, self.body, self.kind = who, body, kind
        self._apply_kind()

        header = Label(text=f"[b]{who}[/b]", markup=True, color=self.rail,
                       font_size=sp(T.SIZE_TINY), size_hint_y=None,
                       halign="left", valign="middle")
        header.bind(size=lambda w, *_: setattr(w, "text_size", (w.width, None)))
        header.height = dp(16)

        self._natural = dp(44)          # replaced as soon as the text is laid out
        self.body_label = Label(text=body, markup=False, color=self.text_color,
                                font_size=sp(T.SIZE_BODY), size_hint_y=None,
                                halign="left", valign="top")
        self.body_label.bind(width=lambda w, val: setattr(w, "text_size", (val, None)),
                             texture_size=self._recalc)
        self.add_widget(header)
        self.add_widget(self.body_label)

        with self.canvas.before:
            self._bg_color = Color(*self.fill)
            self._bg = RoundedRectangle(radius=[dp(14)])
        self.bind(pos=self._sync, size=self._sync)
        self.height = self._natural

    def _recalc(self, _label, value) -> None:
        """Chat bubbles size themselves to their text (multi-line safe)."""
        self._natural = value[1] + dp(16) + dp(3) + self.padding[1] + self.padding[3]
        if self.opacity >= 1.0:
            self.height = self._natural

    def _apply_kind(self):
        if self.kind == "you":
            self.fill, self.text_color, self.rail = list(T.USER_BG), list(T.USER_FG), list(T.USER_FG)
        elif self.kind == "error":
            self.fill, self.text_color, self.rail = list(T.SYS_BG), list(T.ERR), list(T.ERR)
        elif self.kind == "system":
            self.fill, self.text_color, self.rail = list(T.SYS_BG), list(T.SYS_FG), list(T.FG_DIM)
        else:
            self.fill, self.text_color, self.rail = list(T.SURFACE), list(T.FG), list(T.ACCENT_HI)

    def _sync(self, *_a):
        self._bg.pos, self._bg.size = self.pos, self.size
        self._bg.radius = [dp(14)]

    def reveal(self) -> None:
        """Grow + fade in when the bubble is added to the transcript."""
        self.opacity = 0.0
        self.height = dp(10)
        Clock.schedule_once(lambda _dt: self._grow(), 0)

    def _grow(self) -> None:
        anim = Animation(opacity=1.0, height=self._natural,
                         duration=T.D_BASE, t="out_cubic")
        anim.start(self)

"""A **test double** for the small slice of Kivy that THANS Android uses.

The sandbox (and most CI runners) cannot create a Kivy window — no GL, no
display — so this module provides faithful-enough stand-ins for widgets,
properties, canvas instructions, the virtual clock and ``Animation``. It lets
the *real* Android app code run headlessly: boot sequence, bubbles, toasts,
suggestions, command flow, mic guards and preferences.

What is real here: the clock, the animation lifecycle (values interpolate and
``on_complete`` fires), property binding/dispatch, widget parenting and the KV
``id`` set (parsed from ``android/thans.kv``). What is fake: pixels, layout
math and the KV interpreter (the tests fill the id tree instead).

Usage::

    from tests import fakekivy
    fakekivy.install()             # before importing thans_android
"""
from __future__ import annotations

import math
import re
import sys
import types
from pathlib import Path
from typing import Any, Callable, Optional

KV_PATH = Path(__file__).resolve().parent.parent / "android" / "thans.kv"


def kv_ids(path: Path | None = None) -> list[str]:
    """Every ``id:`` declared in the KV file (order preserved)."""
    text = (path or KV_PATH).read_text(encoding="utf-8")
    return re.findall(r"^\s+id:\s*([A-Za-z_][A-Za-z0-9_]*)", text, re.M)


# --------------------------------------------------------------------------
# virtual clock
# --------------------------------------------------------------------------

class Clock:
    _now = 0.0
    _jobs: dict[int, dict] = {}
    _seq = 0

    @classmethod
    def get_boottime(cls) -> float:
        return cls._now

    @classmethod
    def schedule_once(cls, callback: Callable, delay: float = 0) -> "ClockEvent":
        return cls._add(callback, delay, None)

    @classmethod
    def schedule_interval(cls, callback: Callable, interval: float,
                          repeat: bool = True) -> "ClockEvent":
        return cls._add(callback, interval, interval if repeat else None)

    @classmethod
    def _add(cls, callback, delay, interval) -> "ClockEvent":
        cls._seq += 1
        ev = ClockEvent(cls._seq, callback, cls._now + max(0.0, delay), interval)
        cls._jobs[ev.uid] = {"event": ev, "callback": callback,
                             "at": cls._now + max(0.0, delay), "interval": interval}
        return ev

    @classmethod
    def unschedule(cls, event) -> None:
        if event is not None:
            cls._jobs.pop(getattr(event, "uid", None), None)

    @classmethod
    def reset(cls) -> None:
        cls._jobs.clear()
        cls._now = 0.0
        cls._seq = 0

    @classmethod
    def tick(cls, dt: float = 0.0) -> None:
        cls._now += dt
        cls._run_due()

    @classmethod
    def advance(cls, seconds: float, step: float = 1 / 60) -> None:
        """Advance the clock in small steps so animations interpolate."""
        remaining = seconds
        while remaining > 0:
            dt = min(step, remaining)
            cls.tick(dt)
            remaining -= dt

    @classmethod
    def _run_due(cls, limit: int = 20000) -> int:
        ran = 0
        while ran < limit:
            due = [(d["at"], uid) for uid, d in cls._jobs.items() if d["at"] <= cls._now]
            if not due:
                break
            due.sort()
            for _, uid in due:
                job = cls._jobs.get(uid)
                if job is None:
                    continue
                if job["interval"] is None:
                    cls._jobs.pop(uid, None)
                else:
                    job["at"] = cls._now + job["interval"]
                job["callback"](min(0.05, job["interval"] or 0.016))
                ran += 1
        return ran

    @classmethod
    def pending(cls) -> int:
        return len(cls._jobs)


class ClockEvent:
    def __init__(self, uid, callback, at, interval):
        self.uid = uid
        self.callback = callback
        self.at = at
        self.interval = interval

    def cancel(self):
        Clock.unschedule(self)

    def loop(self):
        return self


# --------------------------------------------------------------------------
# properties (Kivy-style class descriptors)
# --------------------------------------------------------------------------

class Property:
    """Descriptor that stores a value per instance and notifies binders."""

    def __init__(self, default=None, name: str = ""):
        self.default = default
        self.name = name

    def __set_name__(self, owner, name):
        self.name = name

    def _default_for(self, instance):
        d = self.default
        if isinstance(d, (list, dict)):
            return type(d)(d)
        return d

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        store = instance.__dict__.setdefault("_props", {})
        if self.name not in store:
            store[self.name] = self._default_for(instance)
        return store[self.name]

    def __set__(self, instance, value):
        store = instance.__dict__.setdefault("_props", {})
        old = store.get(self.name, self._default_for(instance))
        store[self.name] = value
        if hasattr(instance, "dispatch"):
            instance.dispatch(self.name, value)   # Kivy passes the new value only


class BooleanProperty(Property):
    def __init__(self, default=False):
        super().__init__(bool(default))


class StringProperty(Property):
    def __init__(self, default=""):
        super().__init__(str(default))


class NumericProperty(Property):
    def __init__(self, default=0):
        super().__init__(float(default))


class ListProperty(Property):
    def __init__(self, default=None):
        super().__init__(list(default or []))


class DictProperty(Property):
    def __init__(self, default=None):
        super().__init__(dict(default or {}))


class ObjectProperty(Property):
    pass


# --------------------------------------------------------------------------
# canvas
# --------------------------------------------------------------------------

class Instruction:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class Color(Instruction):
    def __init__(self, r=1, g=1, b=1, a=1, rgba=None):
        super().__init__(rgba=list(rgba) if rgba else [r, g, b, a], r=r, g=g, b=b, a=a)


class Rectangle(Instruction):
    def __init__(self, pos=(0, 0), size=(0, 0), **kw):
        super().__init__(pos=tuple(pos), size=tuple(size), **kw)


class RoundedRectangle(Rectangle):
    def __init__(self, radius=None, **kw):
        super().__init__(**kw)
        self.radius = list(radius or [0])


class Line(Instruction):
    def __init__(self, width=1.0, rounded_rectangle=None, **kw):
        super().__init__(width=width, rounded_rectangle=rounded_rectangle, **kw)


class CanvasLayer:
    def __init__(self):
        self.children: list = []

    def add(self, instr):
        self.children.append(instr)

    def insert(self, index, instr):
        self.children.insert(index, instr)

    def remove(self, instr):
        if instr in self.children:
            self.children.remove(instr)

    def clear(self):
        self.children.clear()

    def __enter__(self):
        _CANVAS_STACK.append(self)
        return self

    def __exit__(self, *a):
        if _CANVAS_STACK:
            _CANVAS_STACK.pop()
        return False


_CANVAS_STACK: list[CanvasLayer] = []


class Canvas:
    def __init__(self):
        self.before = CanvasLayer()
        self.after = CanvasLayer()
        self._main = CanvasLayer()

    def add(self, instr):
        target = _CANVAS_STACK[-1] if _CANVAS_STACK else self._main
        target.add(instr)

    def insert(self, index, instr):
        ( _CANVAS_STACK[-1] if _CANVAS_STACK else self._main).insert(index, instr)

    def remove(self, instr):
        for layer in (self.before, self._main, self.after):
            layer.remove(instr)

    def clear(self):
        for layer in (self.before, self._main, self.after):
            layer.clear()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


# --------------------------------------------------------------------------
# widgets
# --------------------------------------------------------------------------

class EventDispatcher:
    def __init__(self, **kw):
        self._bindings: dict[str, list] = {}
        for key, value in kw.items():
            setattr(self, key, value)

    def bind(self, **kw):
        for name, cb in kw.items():
            self._bindings.setdefault(name, []).append(cb)
        return self

    def unbind(self, **kw):
        for name in kw:
            self._bindings.pop(name, None)
        return self

    def dispatch(self, name: str, *args) -> None:
        for cb in list(self._bindings.get(name, [])):
            cb(self, *args)

    def events(self):
        return lambda *a: None


class Widget(EventDispatcher):
    pos = Property((0, 0))
    size = Property((100, 100))
    opacity = NumericProperty(1.0)

    def __init__(self, **kw):
        self.canvas = Canvas()
        self.children: list[Widget] = []
        self.parent: Optional[Widget] = None
        self._destroyed = False
        self._props: dict[str, Any] = {}
        super().__init__(**kw)
        for name, value in list(kw.items()):
            setattr(self, name, value)

    # ---- geometry
    @property
    def x(self):
        return self.pos[0]

    @x.setter
    def x(self, value):
        self.pos = (value, self.pos[1])
        self.dispatch("x", value)

    @property
    def y(self):
        return self.pos[1]

    @y.setter
    def y(self, value):
        self.pos = (self.pos[0], value)
        self.dispatch("y", value)

    @property
    def width(self):
        return self.size[0]

    @width.setter
    def width(self, value):
        self.size = (value, self.size[1])
        self.dispatch("width", value)

    @property
    def height(self):
        return self.size[1]

    @height.setter
    def height(self, value):
        self.size = (self.size[0], value)
        self.dispatch("height", value)

    @property
    def center_x(self):
        return self.pos[0] + self.size[0] / 2

    @property
    def center_y(self):
        return self.pos[1] + self.size[1] / 2

    @property
    def texture_size(self):
        return self.size

    def collide_point(self, x, y) -> bool:
        return (self.x <= x <= self.x + self.width
                and self.y <= y <= self.y + self.height)

    # ---- tree
    def add_widget(self, widget, index: int = 0):
        widget.parent = self
        self.children.insert(index, widget)
        self.dispatch("children", self.children)
        return widget

    def remove_widget(self, widget):
        if widget in self.children:
            self.children.remove(widget)
            widget.parent = None

    def clear_widgets(self, *a):
        for child in list(self.children):
            child.parent = None
        self.children.clear()

    def get_root_window(self):
        node = self
        while node.parent is not None:
            node = node.parent
        return node

    # ---- events
    def on_touch_down(self, touch):
        return None

    def on_touch_up(self, touch):
        return None

    def on_touch_move(self, touch):
        return None


class ButtonBehavior:
    state = StringProperty("normal")

    def trigger(self, *a):
        """Test helper: simulate a tap (down then up)."""
        self.state = "down"
        self.dispatch("on_press", self)
        self.dispatch("on_release", self)
        self.state = "normal"

    def on_touch_down(self, touch):
        if self.collide_point(*touch):
            self.state = "down"
            self.dispatch("on_press", self)
            return True
        return False

    def on_touch_up(self, touch):
        if self.state == "down":
            self.state = "normal"
            self.dispatch("on_release", self)
            return True
        return False


class Label(Widget):
    text = StringProperty("")
    markup = BooleanProperty(False)
    color = ListProperty([1, 1, 1, 1])
    font_size = NumericProperty(14)
    halign = StringProperty("left")
    valign = StringProperty("bottom")
    text_size = Property((100, 100))
    bold = BooleanProperty(False)
    shorten = BooleanProperty(False)
    padding = Property((0, 0))

    def __init__(self, **kw):
        super().__init__(**kw)
        # real Kivy re-renders the texture — mirror the event so bindings fire
        for name in ("text", "text_size", "font_size", "width", "size", "padding"):
            self.bind(**{name: self._retexture})

    def bind(self, **kw):
        """Kivy delivers the current texture_size once you bind to it."""
        super().bind(**kw)
        if "texture_size" in kw:
            self.dispatch("texture_size", self.texture_size)
        return self

    def _retexture(self, *_a):
        self.dispatch("texture_size", self.texture_size)

    @property
    def texture_size(self):
        """Approximate Kivy's text layout, including wrapping at ``text_size``."""
        text = str(self.text)
        char_w = max(1.0, self.font_size * 0.55)
        line_h = max(1.0, self.font_size * 1.4)
        wrap_w = None
        try:
            ts = self.text_size
            if ts and ts[0]:
                wrap_w = float(ts[0])
        except Exception:
            wrap_w = None
        paras = text.split("\n")
        widest = max((len(p) for p in paras), default=1) * char_w
        if wrap_w and wrap_w > 0:
            per_line = max(1, int(wrap_w / char_w))
            n_lines = sum(max(1, -(-len(p) // per_line)) for p in paras)
            return (max(1.0, min(wrap_w, widest)), max(1.0, line_h * n_lines))
        return (max(1.0, widest), max(1.0, line_h * len(paras)))


class Button(ButtonBehavior, Label):
    pass


class BoxLayout(Widget):
    orientation = StringProperty("horizontal")
    spacing = NumericProperty(0)
    padding = Property((0, 0, 0, 0))

    @property
    def minimum_height(self):
        if self.orientation == "vertical":
            return sum(getattr(c, "height", 0) for c in self.children) + self.spacing * max(
                0, len(self.children) - 1)
        return max((getattr(c, "height", 0) for c in self.children), default=0)

    @property
    def minimum_width(self):
        if self.orientation == "horizontal":
            return sum(getattr(c, "width", 0) for c in self.children) + self.spacing * max(
                0, len(self.children) - 1)
        return max((getattr(c, "width", 0) for c in self.children), default=0)


class FloatLayout(Widget):
    pass


class ScrollView(Widget):
    do_scroll_x = BooleanProperty(True)
    scroll_y = NumericProperty(1.0)
    bar_width = NumericProperty(2)
    bar_color = ListProperty([1, 1, 1, 1])


class TextInput(Widget):
    text = StringProperty("")
    hint_text = StringProperty("")
    focus = BooleanProperty(False)
    multiline = BooleanProperty(True)
    foreground_color = ListProperty([1, 1, 1, 1])


# --------------------------------------------------------------------------
# animation
# --------------------------------------------------------------------------

class Animation:
    """Interpolates properties over the virtual clock and fires on_complete."""

    def __init__(self, duration: float = 0.2, t: str = "linear", **props):
        self.duration = max(0.0, float(duration))
        self.transition = t
        self.props = props
        self._target = None
        self._start = {}
        self._elapsed = 0.0
        self._bindings: dict[str, list] = {}
        self._event = None
        self._chained: Optional[Animation] = None

    # ---- chain
    def __and__(self, other):
        self._chained = other
        return other

    def bind(self, **kw):
        for name, cb in kw.items():
            self._bindings.setdefault(name, []).append(cb)
        return self

    def _complete(self):
        for cb in self._bindings.get("on_complete", []):
            cb(self, self._target)
        if self._chained is not None:
            self._chained.start(self._target)

    def start(self, widget):
        self._target = widget
        self._elapsed = 0.0
        self._start = {name: _num(getattr(widget, name, 0)) for name in self.props}
        if self.duration <= 0:
            self._apply(1.0)
            self._complete()
            return self
        self._event = Clock.schedule_interval(self._step, 1 / 60.0)
        return self

    def _step(self, dt):
        self._elapsed += dt
        progress = min(1.0, self._elapsed / self.duration)
        self._apply(_ease(self.transition, progress))
        if progress >= 1.0:
            Clock.unschedule(self._event)
            self._event = None
            self._complete()

    def _apply(self, progress: float):
        for name, target in self.props.items():
            start = self._start.get(name, 0.0)
            try:
                setattr(self._target, name, start + (_num(target) - start) * progress)
            except Exception:
                pass

    def stop(self, widget=None):
        Clock.unschedule(self._event)
        self._event = None


def _num(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _ease(kind: str, p: float) -> float:
    if kind == "out_cubic":
        return 1 - (1 - p) ** 3
    if kind == "in_cubic":
        return p ** 3
    if kind == "out_back":
        c3 = 2.70158
        return 1 + c3 * (p - 1) ** 3 + 1.70158 * (p - 1) ** 2
    if kind == "out_elastic":
        if p <= 0:
            return 0.0
        if p >= 1:
            return 1.0
        return 2 ** (-10 * p) * math.sin((p * 10 - 0.75) * (2 * math.pi / 3)) + 1
    return p


# --------------------------------------------------------------------------
# app + builder
# --------------------------------------------------------------------------

class App(EventDispatcher):
    root = Property(None)
    title = StringProperty("")
    _running: Optional["App"] = None

    def __init__(self, **kw):
        super().__init__(**kw)
        App._running = self

    @classmethod
    def get_running_app(cls):
        return cls._running

    def build(self):
        return None

    def run(self):
        App._running = self
        self.root = self.build()
        return self.root

    def stop(self, *a):
        return None

    def on_pause(self):
        return True

    def on_resume(self):
        return None


#: Filled by tests before ``build()``: id name → stand-in widget.
KV_IDS: dict[str, Any] = {}
KV_ROOT_FACTORY: Optional[Callable[[dict], Any]] = None


class ObservableIds(dict):
    """Like Kivy's ``widget.ids``: attribute *and* item access."""

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError as exc:                      # pragma: no cover
            raise AttributeError(item) from exc

    def __setattr__(self, item, value):
        if item.startswith("_"):
            object.__setattr__(self, item, value)
        else:
            self[item] = value

    def __delattr__(self, item):
        self.pop(item, None)


class _FakeRoot:
    def __init__(self, ids: dict):
        self.ids = ObservableIds(ids)


class Builder:
    _kv_file = KV_PATH

    @classmethod
    def load_file(cls, path, **kw):
        """Return a root object holding the ids declared in the KV file."""
        if KV_IDS:
            ids = dict(KV_IDS)
        else:
            from tests import fakekivy  # noqa: F401
            ids = {name: Widget() for name in kv_ids(Path(path))}
        if KV_ROOT_FACTORY is not None:
            return KV_ROOT_FACTORY(ids)
        return _FakeRoot(ids)

    @classmethod
    def load_string(cls, text, **kw):
        return _FakeRoot({name: Widget() for name in
                          re.findall(r"^\s+id:\s*([A-Za-z_]\w*)", text, re.M)})

    @classmethod
    def unload_file(cls, path):
        return True


# --------------------------------------------------------------------------
# install
# --------------------------------------------------------------------------

def install() -> None:
    """Put the fakes into ``sys.modules`` (call before importing the app)."""
    kivy = types.ModuleType("kivy")
    kivy.__version__ = "0.0-fake"

    def _mod(name, **attrs):
        module = types.ModuleType(name)
        module.__dict__.update(attrs)
        sys.modules[name] = module
        return module

    animation = _mod("kivy.animation", Animation=Animation)
    app_mod = _mod("kivy.app", App=App)
    clock_mod = _mod("kivy.clock", Clock=Clock, ClockEvent=ClockEvent)
    graphics = _mod("kivy.graphics", Color=Color, Rectangle=Rectangle,
                    RoundedRectangle=RoundedRectangle, Line=Line)
    kv_lang = _mod("kivy.lang", Builder=Builder)
    metrics = _mod("kivy.metrics", dp=lambda v: float(v), sp=lambda v: float(v),
                   Metrics=types.SimpleNamespace(density=1.0))
    properties = _mod("kivy.properties", BooleanProperty=BooleanProperty,
                      StringProperty=StringProperty, NumericProperty=NumericProperty,
                      ListProperty=ListProperty, DictProperty=DictProperty,
                      ObjectProperty=ObjectProperty, Property=Property)
    window_mod = _mod("kivy.core.window", Window=WindowDouble())
    core = _mod("kivy.core", window=window_mod)

    uix = _mod("kivy.uix")
    widget_mod = _mod("kivy.uix.widget", Widget=Widget)
    label_mod = _mod("kivy.uix.label", Label=Label)
    button_mod = _mod("kivy.uix.button", Button=Button, ButtonBehavior=ButtonBehavior)
    box_mod = _mod("kivy.uix.boxlayout", BoxLayout=BoxLayout)
    float_mod = _mod("kivy.uix.floatlayout", FloatLayout=FloatLayout)
    scroll_mod = _mod("kivy.uix.scrollview", ScrollView=ScrollView)
    text_mod = _mod("kivy.uix.textinput", TextInput=TextInput)

    kivy.animation = animation
    kivy.app = app_mod
    kivy.clock = clock_mod
    kivy.graphics = graphics
    kivy.lang = kv_lang
    kivy.metrics = metrics
    kivy.properties = properties
    kivy.uix = uix
    kivy.core = core
    kivy.__path__ = []                       # mark as a package
    sys.modules["kivy"] = kivy
    for mod in (animation, app_mod, clock_mod, graphics, kv_lang, metrics, properties,
                core, window_mod, uix, widget_mod, label_mod, button_mod, box_mod,
                float_mod, scroll_mod, text_mod):
        mod.__path__ = []
    Clock.reset()
    KV_IDS.clear()


class WindowDouble(EventDispatcher):
    width = NumericProperty(400.0)
    height = NumericProperty(800.0)
    softinput_mode = StringProperty("")

    def __init__(self, **kw):
        super().__init__(**kw)

    def bind(self, **kw):
        return super().bind(**kw)


def set_kv_ids(mapping: dict) -> None:
    KV_IDS.update(mapping)

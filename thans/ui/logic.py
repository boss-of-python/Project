"""Pure UI logic for THANS — animation, typing, suggestions, health.

Deliberately **tkinter-free**: everything here is plain arithmetic and string
work, so it can be unit-tested headlessly and reused by the Kivy front-end.

The animation model is a tiny tween engine:

    anim = Animator()
    anim.add(Tween(0.35, on_update=lambda v: widget.set_progress(v),
                   on_done=lambda: print("done")))
    # the app calls anim.tick(dt) from its single 60 fps loop
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional, Sequence

# --------------------------------------------------------------------------
# easing
# --------------------------------------------------------------------------

def linear(t: float) -> float:
    return t


def out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


def out_quart(t: float) -> float:
    return 1 - (1 - t) ** 4


def in_out_cubic(t: float) -> float:
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def out_back(t: float, overshoot: float = 1.70158) -> float:
    c3 = overshoot + 1
    return 1 + c3 * (t - 1) ** 3 + overshoot * (t - 1) ** 2


def out_elastic(t: float) -> float:
    if t <= 0:
        return 0.0
    if t >= 1:
        return 1.0
    c4 = (2 * math.pi) / 3
    return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * c4) + 1


def clamp01(t: float) -> float:
    return 0.0 if t < 0 else 1.0 if t > 1 else t


def lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation — the workhorse of every animation frame."""
    return a + (b - a) * t


def ease_between(start: float, end: float, progress: float) -> float:
    """Convenience for ``anim_to(lambda v: ...)`` callbacks."""
    return lerp(start, end, clamp01(progress))


# --------------------------------------------------------------------------
# tween engine
# --------------------------------------------------------------------------

@dataclass
class Tween:
    """One animated value.

    ``duration`` is in seconds; ``advance(dt)`` returns ``True`` once done.
    ``on_update`` receives the eased 0→1 progress (or 1→0 for ``reverse``),
    ``on_done`` fires exactly once.
    """
    duration: float
    easing: Callable[[float], float] = out_cubic
    delay: float = 0.0
    reverse: bool = False
    on_update: Optional[Callable[[float], None]] = None
    on_done: Optional[Callable[[], None]] = None
    elapsed: float = 0.0
    _done: bool = field(default=False, repr=False)
    _fired_update: bool = field(default=False, repr=False)

    def __post_init__(self) -> None:
        self.duration = max(0.0, float(self.duration))

    @property
    def done(self) -> bool:
        return self._done

    def _emit(self, raw: float) -> None:
        p = clamp01(raw)
        p = self.easing(p)
        if self.reverse:
            p = 1.0 - p
        if self.on_update:
            self.on_update(p)

    def advance(self, dt: float) -> bool:
        if self._done:
            return True
        if self.delay > 0:
            self.delay -= dt
            if self.delay > 0:
                return False
            dt = -self.delay          # spend the leftover time
            self.delay = 0.0
        self.elapsed += dt
        if self.duration <= 0 or self.elapsed >= self.duration:
            # always emit the final *raw* value; _emit() applies the easing
            # and the reverse flip, so a reverse tween lands exactly on 0.
            self._emit(1.0)
            self._done = True
            if self.on_done:
                cb, self.on_done = self.on_done, None
                cb()
            return True
        self._emit(self.elapsed / self.duration)
        return False

    def finish(self) -> None:
        """Jump to the end (used when motion is disabled or the app closes)."""
        if not self._done:
            self.delay = 0.0
            self.advance(self.duration + 1)

    @classmethod
    def chain(cls, *tweens: "Tween", gap: float = 0.0) -> list["Tween"]:
        """Run tweens one after another (returns the list for ``Animator.add``)."""
        out: list[Tween] = []
        for i, tw in enumerate(tweens):
            if i:
                tw.delay += gap
            out.append(tw)
        return out


class Animator:
    """Drives every active tween from one loop (the app's 60 fps tick)."""

    def __init__(self, fps: int = 60):
        self.dt = 1.0 / max(1, fps)
        self._tweens: list[Tween] = []

    def add(self, *tweens: Tween | Iterable[Tween]) -> Tween | None:
        flat: list[Tween] = []
        for tw in tweens:
            if isinstance(tw, Tween):
                flat.append(tw)
            else:
                flat.extend(tw)
        self._tweens.extend(flat)
        return flat[0] if flat else None

    def run(self, tween: Tween | Iterable[Tween]) -> Tween | None:
        return self.add(tween)

    @property
    def active(self) -> int:
        return len(self._tweens)

    def busy(self) -> bool:
        return bool(self._tweens)

    def tick(self, dt: float | None = None) -> int:
        """Advance every tween; returns how many are still running."""
        dt = self.dt if dt is None else dt
        self._tweens = [tw for tw in self._tweens if not tw.advance(dt)]
        return len(self._tweens)

    def clear(self) -> None:
        self._tweens.clear()

    def stop(self, tween: Tween | None) -> None:
        """Cancel one tween (no-op for ``None``)."""
        if tween is None:
            return
        if isinstance(tween, LoopTween):
            tween.stop()
        else:
            tween._done = True
        if tween in self._tweens:
            self._tweens.remove(tween)


class LoopTween(Tween):
    """Base for endless tweens: they keep emitting until :meth:`stop`."""

    looping = True

    def stop(self) -> None:
        self._done = True

    @property
    def running(self) -> bool:
        return not self._done


class PulseTween(LoopTween):
    """Endless ping-pong 0→1→0 — breathing indicators."""

    def advance(self, dt: float) -> bool:          # noqa: D102
        if self._done:
            return True
        self.elapsed += dt
        phase = (self.elapsed % (2 * self.duration)) / self.duration       # 0…2
        v = 0.5 - 0.5 * math.cos(math.pi * phase)                          # 0→1→0
        if self.on_update:
            self.on_update(clamp01(v))
        return False


class SweepTween(LoopTween):
    """Endless 0→1 saw-tooth — progress sweeps, mic levels, typewriter cursor."""

    def advance(self, dt: float) -> bool:          # noqa: D102
        if self._done:
            return True
        self.elapsed += dt
        v = (self.elapsed % self.duration) / self.duration
        if self.on_update:
            self.on_update(v)
        return False


def pulse(duration: float = 1.1, on_update: Callable[[float], None] | None = None) -> PulseTween:
    """Breathing 0→1→0 value; call ``.stop()`` to release it."""
    return PulseTween(duration, on_update=on_update)


def sweep(period: float = 2.4, on_update: Callable[[float], None] | None = None) -> SweepTween:
    """Saw-tooth 0→1 value; call ``.stop()`` to release it."""
    return SweepTween(period, on_update=on_update)


# --------------------------------------------------------------------------
# typewriter (staged replies), used for the "write-in" of every answer
# --------------------------------------------------------------------------

@dataclass
class Typewriter:
    """Reveals ``text`` progressively — long answers reveal faster."""
    text: str = ""
    cps: float = 320.0            # characters per second
    min_cps: float = 260.0
    max_cps: float = 900.0
    elapsed: float = 0.0
    started: bool = False

    def rate(self) -> float:
        """Characters per second: steady for short replies, quicker for long ones."""
        n = len(self.text)
        if n <= 400:
            return self.cps
        return min(self.max_cps, self.cps * math.sqrt(n / 400.0))

    def start(self, text: str) -> None:
        self.text = text
        self.elapsed = 0.0
        self.started = True

    def stop(self) -> None:
        self.started = False

    @property
    def done(self) -> bool:
        return not self.started or self.visible_chars >= len(self.text)

    @property
    def visible_chars(self) -> int:
        return min(len(self.text), int(self.elapsed * self.rate()))

    def advance(self, dt: float) -> str:
        self.elapsed += dt
        chars = self.visible_chars
        if not self.started or chars >= len(self.text):
            self.started = False
            return self.text
        return self.text[:chars]


# --------------------------------------------------------------------------
# command suggestions (as-you-type completion)
# --------------------------------------------------------------------------

#: Templates offered when the input is empty or being typed character by char.
TEMPLATES: tuple[str, ...] = (
    "list",
    "list <folder>",
    "how many files in <folder>",
    "create folder <name>",
    "create file <name> with <text>",
    "rename <old> to <new>",
    "move <item> to <folder>",
    "copy <item> to <folder>",
    "delete <item>",
    "find <name>",
    "search for <ext> files",
    "open <item>",
    "show in folder <item>",
    "organize <folder> by date",
    "organize <folder>",
    "go to <folder>",
    "cd",
    "undo",
    "help",
)

#: verb → which parameter follows it (drives smart completion from real files)
ITEM_VERBS = {
    "move": "item", "copy": "item", "delete": "item", "remove": "item",
    "trash": "item", "rename": "item", "open": "item", "find": "item",
    "search": "item", "cd": "folder", "go": "folder",
}
DEST_WORDS = (" to ", " into ", " in ")

#: Friendly examples shown as chips when the chat is empty (tap to fill).
STARTERS: tuple[tuple[str, str], ...] = (
    ("List this folder", "list"),
    ("Find a file", "find "),
    ("Create a folder", "create folder "),
    ("Organize by date", "organize . by date"),
    ("How many files?", "how many files in ."),
)


def _score(candidate: str, query: str) -> float:
    """Cheap-but-sensible relevance score (higher = better)."""
    c, q = candidate.casefold(), query.casefold()
    if not q:
        return 0.1
    if c == q:
        return 100.0
    if c.startswith(q):
        return 80.0 - len(c) * 0.01
    if any(part.startswith(q) for part in c.replace("/", " ").split()):
        return 60.0
    if q in c:
        return 40.0 - c.index(q)
    return 0.0


def suggest(text: str, names: Sequence[str] = (), dirs: Sequence[str] = (),
            limit: int = 6) -> list[str]:
    """Completion candidates for the input line.

    * empty input → a short tour of the command set
    * partial verb → matching templates ("cre" → "create folder <name>")
    * after a verb → real item/folder names from the working folder
    * after "to"/"into"/"in" → real folder names
    """
    text = text or ""
    low = text.strip().casefold()
    if not low:
        return list(TEMPLATES[:limit])

    # destination position → folders only
    tail = None
    for kw in DEST_WORDS:
        if kw in text:
            tail = text.rsplit(kw, 1)[1].strip()
            parts = [d for d in dirs]
            ranked = sorted(parts, key=lambda d: -_score(d, tail))
            return [d for d in ranked if _score(d, tail) > 0][:limit]

    # after a verb → items (or folders) that exist right now
    first = low.split(" ", 1)[0]
    role = ITEM_VERBS.get(first)
    if role:
        rest = text[len(first):].strip()
        pool = dirs if role == "folder" else list(dict.fromkeys(list(names) + list(dirs)))
        ranked = sorted(pool, key=lambda n: -_score(n, rest))
        hits = [n for n in ranked if _score(n, rest) > 0]
        if rest == "":
            return [f"{first} {n}" for n in pool[:limit]]
        return hits[:limit]

    # otherwise: complete the template itself
    ranked_t = sorted(TEMPLATES, key=lambda t: -_score(t, low))
    hits = [t for t in ranked_t if _score(t, low) > 0]
    return hits[:limit]


# --------------------------------------------------------------------------
# health / progress
# --------------------------------------------------------------------------

def grade_health(percent: float, budget: float = 10_000_000) -> tuple[str, str]:
    """Grade free space: (label, state) where state is ok/warn/error.

    ``percent`` is the *used* share (0–1). ``budget`` is the assumed capacity
    in bytes used only for the label wording.
    """
    p = clamp01(percent)
    if p < 0.80:
        return "healthy", "ok"
    if p < 0.93:
        return "filling up", "warn"
    return "almost full", "error"


def format_bytes(n: float) -> str:
    """1_234_567 → '1.2 MB' (human, compact)."""
    step = 1024.0
    units = ("B", "KB", "MB", "GB", "TB")
    n = float(max(0, n))
    i = 0
    while n >= step and i < len(units) - 1:
        n /= step
        i += 1
    digits = 0 if n >= 100 or i == 0 else 1
    return f"{n:.{digits}f} {units[i]}"


def progress_label(done: int, total: int) -> str:
    if total <= 0:
        return "nothing to do"
    pct = int(round(100.0 * done / total))
    return f"{done}/{total} · {pct}%"


def greeting(now=None) -> str:
    """Time-of-day greeting for the welcome card (pure & testable)."""
    import datetime as _dt
    hour = (now or _dt.datetime.now()).hour
    if hour < 5:
        return "Working late"
    if hour < 12:
        return "Good morning"
    if hour < 17:
        return "Good afternoon"
    if hour < 22:
        return "Good evening"
    return "Working late"


def truncate(text: str, limit: int = 64) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


#: Commands that earn a small celebration when they succeed.
CELEBRATE = {"organize"}


def should_celebrate(command_desc: str, ok: bool) -> bool:
    """True when a finished action deserves the particle burst."""
    if not ok:
        return False
    return (command_desc or "").split(" ", 1)[0] in CELEBRATE


def keys_hint(short: bool = False) -> str:
    """Status-bar hint. ``short`` is the compact form (fits narrow windows)."""
    if short:
        return "F1 help · F2 voice · Tab complete · Ctrl+K clear"
    return ("⏎ send · ⇧⏎ newline · ↑↓ history · Tab complete · "
            "Ctrl+K clear · Ctrl+Z undo · F1 help")

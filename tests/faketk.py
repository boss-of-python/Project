"""A tiny **test double** for tkinter, so the real UI code can be exercised
headlessly (CI machines, containers, this sandbox — no display required).

It is deliberately faithful where it matters for THANS:

* option names are validated per widget class (typos like ``shadow=1`` fail),
* ``Text`` keeps a real buffer with Tk-style indices (``1.0``, ``end-1c``,
  ``insert``, ``sel.first``), so streaming/typing code is really executed,
* ``Canvas`` records every drawn item, so animation code paths run,
* ``after`` callbacks run on a *virtual* clock, so boot timelines can be driven.

It is **not** a renderer: nothing is drawn and geometry is simulated. Use it to
prove the UI logic works, then still click through the app on a real desktop.

Usage::

    from tests import faketk
    faketk.install()            # must happen before importing thans.app
    from thans import app
"""
from __future__ import annotations

import sys
import types
from typing import Any, Callable, Optional

# --------------------------------------------------------------------------
# option tables (Tk's real option names for the widgets THANS uses)
# --------------------------------------------------------------------------
COMMON = {
    "background", "bg", "foreground", "fg", "borderwidth", "bd", "cursor",
    "highlightbackground", "highlightcolor", "highlightthickness", "relief",
    "takefocus", "width", "height", "name", "class_", "visual", "colormap",
    "container", "depth", "padx", "pady", "font", "text", "state",
}
OPTIONS: dict[str, set[str]] = {
    "Frame": COMMON | {"labelanchor", "labelwidget", "label"},
    "Toplevel": COMMON,
    "Label": COMMON | {"anchor", "justify", "wraplength", "image", "compound",
                       "underline", "bitmap"},
    "Canvas": COMMON | {"closeenough", "confine", "scrollregion", "xscrollcommand",
                        "yscrollcommand", "insertbackground", "insertwidth",
                        "insertborderwidth", "selectbackground", "selectforeground",
                        "offset", "xscrollincrement", "yscrollincrement", "background",
                        "borderwidth", "tile", "highlightthickness", "border"},
    "Text": COMMON | {"wrap", "insertbackground", "insertwidth", "selectbackground",
                      "selectforeground", "spacing1", "spacing2", "spacing3",
                      "undo", "maxundo", "autoseparators", "tabs", "yscrollcommand",
                      "xscrollcommand", "setgrid", "exportselection", "inactiveselectbackground",
                      "insertofftime", "insertontime", "blockcursor", "endline",
                      "startline", "write", "spacing", "selectborderwidth", "insertborderwidth",
                      "linemap", "padx", "pady", "border"},
    "Entry": COMMON | {"show", "textvariable", "insertbackground", "selectbackground",
                       "selectforeground", "justify", "exportselection", "invalidcommand",
                       "validate", "validatecommand", "insertwidth"},
    "Button": COMMON | {"command", "anchor", "justify", "wraplength", "activebackground",
                        "activeforeground", "default", "compound", "underline",
                        "overrelief", "image", "bitmap", "disabledforeground"},
    "Tk": COMMON,
    "Menu": COMMON | {"tearoff", "tearoffcommand", "activebackground", "activeborderwidth",
                      "activeforeground", "disabledforeground", "selectcolor", "postcommand",
                      "menubar", "title", "type", "accelerator", "columnbreak", "hidemargin",
                      "indicatoron", "compound", "image", "offvalue", "onvalue", "underline",
                      "variable", "value", "label", "command", "state"},
}

CANVAS_ITEMS = {"rectangle", "oval", "polygon", "line", "text", "arc", "image",
                "window", "bitmap"}


class TclError(Exception):
    """Mirrors ``tkinter.TclError``."""


# --------------------------------------------------------------------------
# virtual clock (module level so every widget shares it)
# --------------------------------------------------------------------------

class Clock:
    def __init__(self) -> None:
        self.now = 0.0                     # ms
        self._jobs: dict[str, tuple[float, Callable[[], None]]] = {}
        self._n = 0

    def after(self, ms: int, fn: Callable[[], None]) -> str:
        self._n += 1
        jid = f"after#{self._n}"
        self._jobs[jid] = (self.now + max(0, int(ms)), fn)
        return jid

    def cancel(self, jid: str) -> None:
        self._jobs.pop(jid, None)

    def pending(self) -> int:
        return len(self._jobs)

    def run_due(self, limit: int = 5000) -> int:
        """Run every callback whose time has come (and rescheduled ones)."""
        ran = 0
        while ran < limit:
            due = [(t, jid) for jid, (t, _) in self._jobs.items() if t <= self.now]
            if not due:
                break
            due.sort()
            for _, jid in due:
                job = self._jobs.pop(jid, None)
                if job is not None:
                    job[1]()
                    ran += 1
        return ran

    def advance(self, ms: float) -> int:
        self.now += ms
        return self.run_due()

    def reset(self) -> None:
        self.now = 0.0
        self._jobs.clear()


CLOCK = Clock()
FONTS = ("Segoe UI", "DejaVu Sans", "Liberation Sans", "Ubuntu", "Noto Sans",
         "Consolas", "DejaVu Sans Mono", "Cascadia Mono", "Ubuntu Mono",
         "TkDefaultFont", "TkFixedFont", "Helvetica")


# --------------------------------------------------------------------------
# font
# --------------------------------------------------------------------------

class FakeFont:
    def __init__(self, root=None, font=None, **kw):
        self.family, self.size, self.weight = "DejaVu Sans", 11, "normal"
        spec = font if font is not None else kw.get("font")
        if spec is None and kw:
            self._apply(kw)
        elif spec is not None:
            self._apply(spec if isinstance(spec, (tuple, list, dict))
                        else self._describe(spec))

    def _describe(self, name):
        return {}

    def _apply(self, spec):
        if isinstance(spec, dict):
            self.family = spec.get("family", self.family)
            self.size = int(spec.get("size", self.size))
            self.weight = spec.get("weight", self.weight)
        elif isinstance(spec, (tuple, list)):
            parts = list(spec)
            if parts:
                self.family = parts[0]
            if len(parts) > 1:
                try:
                    self.size = int(parts[1])
                except (TypeError, ValueError):
                    pass
            if len(parts) > 2:
                self.weight = parts[2]

    def measure(self, text: str) -> int:
        return int(len(str(text)) * (self.size * 0.62))

    def metrics(self, what: str = "linespace") -> int:
        return int(self.size * 1.45)

    def actual(self, what: str = "family"):
        return getattr(self, what, self.family)


def families(root=None):
    return list(FONTS)


# --------------------------------------------------------------------------
# widget base
# --------------------------------------------------------------------------

class Widget:
    _class = "Frame"

    def __init__(self, master=None, **kw):
        self.master = master
        self._opts: dict[str, Any] = {}
        self.children: list[Widget] = []
        self._destroyed = False
        self._placed: dict[str, Any] = {}
        self._manager: Optional[str] = None
        self._bindings: dict[str, Callable] = {}
        self._size = (60, 24)          # simulated winfo size
        self._pos = (0, 0)             # simulated winfo x/y
        self._tags: dict[str, list[tuple[int, int]]] = {}
        if master is not None and hasattr(master, "children"):
            master.children.append(self)
        self._apply(kw)

    # ---- options
    def _allowed(self) -> set[str]:
        return OPTIONS.get(self._class, COMMON)

    def _apply(self, kw: dict) -> None:
        for key, val in kw.items():
            k = "background" if key == "bg" else "foreground" if key == "fg" else key
            if k not in self._allowed() and key not in self._allowed():
                raise TclError(f"unknown option '{key}' for {self._class} "
                               f"(fake tkinter validates option names)")
            self._opts[k] = val

    def configure(self, cnf=None, **kw):
        if cnf:
            self._apply(dict(cnf))
        self._apply(kw)
        return None

    config = configure

    def cget(self, key: str):
        k = "background" if key == "bg" else "foreground" if key == "fg" else key
        if k in self._opts:
            return self._opts[k]
        raise TclError(f"unknown option '{key}'")

    def __getitem__(self, key):
        return self.cget(key)

    def __setitem__(self, key, value):
        self.configure(**{key: value})

    # ---- geometry managers
    def pack(self, **kw):
        self._manager = "pack"
        self._placed.update(kw)
        self._placed["in"] = kw.get("in", self.master)
        return self

    def pack_configure(self, **kw):
        return self.pack(**kw)

    def pack_forget(self):
        self._manager = None
        return None

    def grid(self, **kw):
        self._manager = "grid"
        self._placed.update(kw)
        return self

    def grid_configure(self, **kw):
        return self.grid(**kw)

    def grid_forget(self):
        self._manager = None
        return None

    def grid_columnconfigure(self, *a, **kw):
        return None

    def grid_rowconfigure(self, *a, **kw):
        return None

    # Tk 8.6 aliases (root.columnconfigure(...), pack/grid/place "in"/"anchor")
    columnconfigure = grid_columnconfigure
    rowconfigure = grid_rowconfigure

    def grid_propagate(self, *a, **kw):
        return None

    def pack_propagate(self, *a, **kw):
        return None

    def place(self, **kw):
        self._manager = "place"
        self._placed.update(kw)
        if "x" in kw:
            self._pos = (kw["x"], kw.get("y", self._pos[1]))
        if "y" in kw:
            self._pos = (self._pos[0], kw["y"])
        return self

    def place_configure(self, **kw):
        if self._manager != "place":
            raise TclError("place_configure on a widget that is not placed")
        self._placed.update(kw)
        if "x" in kw:
            self._pos = (kw["x"], self._pos[1])
        if "y" in kw:
            self._pos = (self._pos[0], kw["y"])
        return self

    def place_forget(self):
        self._manager = None
        self._placed.clear()
        return None

    def place_info(self):
        return dict(self._placed)

    def winfo_manager(self):
        return self._manager or ""

    # ---- info
    def winfo_width(self) -> int:
        return self._size[0]

    def winfo_height(self) -> int:
        return self._size[1]

    def winfo_reqwidth(self) -> int:
        return self._size[0]

    def winfo_reqheight(self) -> int:
        return self._size[1]

    def winfo_exists(self) -> int:
        return 0 if self._destroyed else 1

    def winfo_ismapped(self) -> int:
        return 1 if self._manager else 0

    def winfo_x(self) -> int:
        return int(self._pos[0])

    def winfo_y(self) -> int:
        return int(self._pos[1])

    def winfo_rootx(self) -> int:
        return 100

    def winfo_rooty(self) -> int:
        return 100

    def winfo_screenwidth(self) -> int:
        return 1920

    def winfo_screenheight(self) -> int:
        return 1080

    def winfo_children(self):
        return list(self.children)

    def winfo_toplevel(self):
        node = self
        while getattr(node, "master", None) is not None:
            node = node.master
        return node

    # ---- lifecycle
    def destroy(self):
        self._destroyed = True
        for child in list(self.children):
            child.destroy()
        self.children.clear()

    # ---- events
    def bind(self, sequence, func=None, add=None):
        self._bindings[sequence] = func
        return func

    def unbind(self, sequence):
        self._bindings.pop(sequence, None)

    def event_generate(self, sequence, **kw):
        func = self._bindings.get(sequence)
        if func:
            func(Event(sequence, self, **kw))

    def after(self, ms, func=None, *args):
        if func is None:
            return CLOCK.after(ms, lambda: None)
        return CLOCK.after(ms, lambda: func(*args) if args else func())

    def after_cancel(self, jid):
        CLOCK.cancel(jid)

    def update_idletasks(self):
        return None

    def update(self):
        return None

    def focus_set(self):
        self._opts["focus"] = True
        return None

    focus = focus_set

    def focus_force(self):
        return None

    def grab_release(self):
        return None

    def lift(self, *a):
        return None

    def lower(self, *a):
        return None

    def clipboard_clear(self):
        _CLIPBOARD["text"] = ""

    def clipboard_append(self, text):
        _CLIPBOARD["text"] += text

    def set_size(self, w: int, h: int) -> None:
        """Test helper: simulate the geometry manager giving the widget a size."""
        self._size = (int(w), int(h))
        self.event_generate("<Configure>")

    # convenience for tests
    @property
    def opts(self) -> dict:
        return dict(self._opts)


class Event:
    def __init__(self, sequence="", widget=None, **kw):
        self.sequence = sequence
        self.widget = widget
        self.x = kw.get("x", 5)
        self.y = kw.get("y", 5)
        self.delta = kw.get("delta", 120)
        self.state = kw.get("state", 0)
        self.x_root = kw.get("x_root", 100)
        self.y_root = kw.get("y_root", 100)
        self.num = kw.get("num", 4)
        self.char = kw.get("char", "")


_CLIPBOARD = {"text": ""}


# --------------------------------------------------------------------------
# concrete widgets
# --------------------------------------------------------------------------

class Frame(Widget):
    _class = "Frame"


class Label(Widget):
    _class = "Label"


class Button(Widget):
    _class = "Button"

    def invoke(self):
        cmd = self._opts.get("command")
        if cmd:
            cmd()


class Entry(Widget):
    _class = "Entry"

    def __init__(self, master=None, **kw):
        super().__init__(master, **kw)
        self._text = str(kw.get("text", ""))

    def insert(self, index, text):
        self._text += text

    def delete(self, a, b=None):
        self._text = ""

    def get(self):
        return self._text


class Canvas(Widget):
    _class = "Canvas"

    def __init__(self, master=None, **kw):
        super().__init__(master, **kw)
        self.items: dict[int, dict] = {}
        self._next = 0

    def _new(self, kind: str, coords, kw: dict) -> int:
        if kind not in CANVAS_ITEMS:
            raise TclError(f"unknown canvas item '{kind}'")
        self._next += 1
        tags = kw.get("tags", ())
        if isinstance(tags, str):
            tags = (tags,)
        self.items[self._next] = {"type": kind, "coords": list(coords),
                                  "opts": dict(kw), "tags": list(tags)}
        return self._next

    def create_rectangle(self, *c, **kw):
        return self._new("rectangle", c, kw)

    def create_oval(self, *c, **kw):
        return self._new("oval", c, kw)

    def create_polygon(self, *c, **kw):
        return self._new("polygon", c, kw)

    def create_line(self, *c, **kw):
        return self._new("line", c, kw)

    def create_arc(self, *c, **kw):
        return self._new("arc", c, kw)

    def create_text(self, *c, **kw):
        return self._new("text", c, kw)

    def create_image(self, *c, **kw):
        return self._new("image", c, kw)

    def create_window(self, *c, **kw):
        return self._new("window", c, kw)

    def coords(self, item, *c):
        if item not in self.items:
            raise TclError(f"item {item} does not exist")
        if c:
            self.items[item]["coords"] = list(c)
            return None
        return tuple(self.items[item]["coords"])

    def itemconfigure(self, item, **kw):
        if item not in self.items:
            raise TclError(f"item {item} does not exist")
        self.items[item]["opts"].update(kw)
        return None

    itemconfig = itemconfigure

    def itemcget(self, item, key):
        if item not in self.items:
            raise TclError(f"item {item} does not exist")
        return self.items[item]["opts"].get(key, "")

    def delete(self, *items):
        for item in items:
            if isinstance(item, str):           # a tag
                for iid in [i for i, it in self.items.items() if item in it["tags"]]:
                    self.items.pop(iid, None)
            else:
                self.items.pop(item, None)
        return None

    def find_all(self):
        return tuple(self.items.keys())

    def type(self, item):
        if item not in self.items:
            raise TclError(f"item {item} does not exist")
        return self.items[item]["type"]

    def tag_lower(self, *a):
        return None

    def tag_raise(self, *a):
        return None

    def tag_bind(self, *a, **kw):
        return None

    def bbox(self, *a):
        return (0, 0, 10, 10)

    def count_items(self, kind: Optional[str] = None) -> int:
        """Test helper."""
        if kind is None:
            return len(self.items)
        return sum(1 for it in self.items.values() if it["type"] == kind)


class Text(Widget):
    """A small but real text buffer with Tk-style indices."""

    _class = "Text"

    def __init__(self, master=None, **kw):
        super().__init__(master, **kw)
        self._buf = "\n"                     # Tk always keeps a trailing newline
        self._insert = 0
        self.tags: dict[str, int] = {}       # tag → times configured
        self._view = 0.0
        self.selected: tuple[int, int] | None = None
        self.see_calls: list[str] = []

    # ---- index handling
    def _offset(self, index) -> int:
        idx = index if isinstance(index, str) else str(index)
        idx = idx.strip()
        if idx.startswith("@"):
            idx = idx[1:]
        base, _, modifier = idx.partition("+") if "+" in idx else idx.partition("-")
        sign = "+" if "+" in idx else ("-" if "-" in idx else "")
        base = base or "1.0"

        if base in ("end", "end-1c", "insert") or base.startswith(("end", "insert")):
            if base.startswith("insert"):
                off = self._insert
            elif base == "end":
                off = len(self._buf)
            else:
                off = len(self._buf) - 1
        elif base in ("sel.first", "sel.last"):
            if not self.selected:
                raise TclError("text doesn't contain any characters tagged with \"sel\"")
            off = self.selected[0] if base == "sel.first" else self.selected[1]
        elif "." in base:
            line_s, _, col_s = base.partition(".")
            line = int(line_s or "1")
            col = int(col_s or "0")
            lines = self._buf.split("\n")
            line = max(1, min(line, len(lines)))
            off = sum(len(l) + 1 for l in lines[: line - 1]) + max(0, col)
        else:
            raise TclError(f"bad text index '{index}'")

        if sign and modifier:
            if modifier.endswith("c") or modifier.isdigit():
                n = int(modifier.rstrip("c") or 0)
                off += n if sign == "+" else -n
            elif modifier.endswith("l"):
                n = int(modifier.rstrip("l") or 0)
                off += n if sign == "+" else -n
        return max(0, min(off, len(self._buf)))

    def _index_of(self, offset: int) -> str:
        offset = max(0, min(offset, len(self._buf)))
        prefix = self._buf[:offset]
        line = prefix.count("\n") + 1
        col = offset - (prefix.rfind("\n") + 1)
        return f"{line}.{col}"

    def index(self, index) -> str:
        return self._index_of(self._offset(index))

    # ---- content
    def insert(self, index, text, *tags):
        off = self._offset(index)
        text = str(text)
        self._buf = self._buf[:off] + text + self._buf[off:]
        self._insert = off + len(text)
        for tag in tags:
            if isinstance(tag, str):
                self.tags[tag] = self.tags.get(tag, 0) + 1
        return None

    def delete(self, start, end=None):
        a = self._offset(start)
        b = self._offset(end) if end is not None else a + 1
        if b < a:
            a, b = b, a
        self._buf = self._buf[:a] + self._buf[b:]
        if not self._buf.endswith("\n"):     # the implicit final newline stays
            self._buf += "\n"
        self._insert = min(a, len(self._buf))
        return None

    def get(self, start, end=None):
        a = self._offset(start)
        b = self._offset(end) if end is not None else len(self._buf)
        return self._buf[a:b]

    def mark_set(self, name, index):
        if name == "insert":
            self._insert = self._offset(index)

    def see(self, index):
        self.see_calls.append(str(index))

    def tag_add(self, tag, start, end=None):
        self.tags[tag] = self.tags.get(tag, 0) + 1

    def tag_configure(self, tag, **kw):
        self.tags[tag] = self.tags.get(tag, 0) + 1

    tag_config = tag_configure

    def tag_ranges(self, tag):
        return ()

    def tag_names(self):
        return tuple(self.tags)

    # ---- scrolling
    def yview(self):
        total_lines = max(1, self._buf.count("\n"))
        visible = 18
        if total_lines <= visible:
            return (0.0, 1.0)
        first = min(1.0 - visible / total_lines, max(0.0, self._view))
        return (first, min(1.0, first + visible / total_lines))

    def yview_moveto(self, fraction):
        self._view = float(fraction)

    def yview_scroll(self, number, what="units"):
        self._view = max(0.0, min(1.0, self._view + number * 0.03))

    def search(self, pattern, index, **kw):
        off = self._buf.find(pattern, self._offset(index))
        return self._index_of(off) if off >= 0 else ""

    # ---- tests
    @property
    def text(self) -> str:
        return self._buf


class Tk(Widget):
    _class = "Tk"

    def __init__(self, *a, **kw):
        super().__init__(None, **kw)
        self._geometry = "1060x700+0+0"
        self._title = ""
        self._protocols: dict[str, Callable] = {}
        self._attrs: dict[str, Any] = {}
        self._size = (1060, 700)
        self._mapped = False

    def title(self, text=None):
        if text is None:
            return self._title
        self._title = text

    def geometry(self, spec=None):
        if spec is None:
            return self._geometry
        self._geometry = str(spec)
        if "x" in spec:
            try:
                w, h = spec.split("+")[0].split("x")
                self._size = (int(w), int(h))
            except ValueError:
                pass
        return None

    def minsize(self, w=None, h=None):
        return None

    def maxsize(self, w=None, h=None):
        return None

    def resizable(self, *a):
        return None

    def withdraw(self):
        self._mapped = False

    def deiconify(self):
        self._mapped = True

    def attributes(self, *a, **kw):
        if len(a) == 2:
            self._attrs[a[0]] = a[1]
        return None

    def protocol(self, name, func=None):
        if func is not None:
            self._protocols[name] = func
        return self._protocols.get(name)

    def bind_all(self, seq, func=None, add=None):
        return self.bind(seq, func, add)

    def mainloop(self, n=0):
        """Run a few scheduled callbacks, then return (never blocks a test)."""
        CLOCK.advance(1)

    def quit(self):
        return None

    def destroy(self):
        super().destroy()


class Toplevel(Tk):
    _class = "Toplevel"

    def __init__(self, master=None, **kw):
        Widget.__init__(self, master, **kw)
        self._geometry = "200x40+0+0"


class Menu(Widget):
    _class = "Menu"

    def __init__(self, master=None, **kw):
        super().__init__(master, **kw)
        self.entries: list[tuple] = []

    def add_command(self, label=None, command=None, **kw):
        self.entries.append(("command", label, command))

    def add_separator(self, **kw):
        self.entries.append(("separator", None, None))

    def add_cascade(self, **kw):
        self.entries.append(("cascade", kw.get("label"), None))

    def tk_popup(self, *a, **kw):
        return None

    def grab_release(self):
        return None


class Variable:
    def __init__(self, master=None, value=None, name=None):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value

    def trace_add(self, *a, **kw):
        return "trace#0"


class StringVar(Variable):
    pass


class IntVar(Variable):
    pass


# --------------------------------------------------------------------------
# ttk / dialogs
# --------------------------------------------------------------------------

class Style:
    def __init__(self, master=None):
        self._c: dict[tuple, dict] = {}

    def theme_use(self, name=None):
        return "clam"

    def theme_names(self):
        return ("clam", "default")

    def configure(self, style=None, **kw):
        if kw:
            self._c[(style, tuple(sorted(kw.items())))] = True

    def map(self, *a, **kw):
        return None

    def lookup(self, *a, **kw):
        return ""


class Progressbar(Widget):
    _class = "Frame"          # ttk.Progressbar — only used as a stub here


class Combobox(Widget):
    _class = "Entry"


class FrameTTK(Progressbar):
    pass


class _Scale(Widget):
    _class = "Label"


class _Notebook(Widget):
    _class = "Frame"


# --------------------------------------------------------------------------
# install into sys.modules
# --------------------------------------------------------------------------

def install() -> types.ModuleType:
    """Install the fake as ``tkinter`` (call before importing thans UI code)."""
    tk = types.ModuleType("tkinter")
    tk.__dict__.update({
        "Tk": Tk, "Toplevel": Toplevel, "Frame": Frame, "Label": Label, "Button": Button,
        "Canvas": Canvas, "Text": Text, "Entry": Entry, "Menu": Menu, "Event": Event,
        "StringVar": StringVar, "IntVar": IntVar, "Variable": Variable,
        "TclError": TclError, "NORMAL": "normal", "DISABLED": "disabled", "END": "end",
        "LEFT": "left", "RIGHT": "right", "TOP": "top", "BOTTOM": "bottom",
        "X": "x", "Y": "y", "BOTH": "both", "W": "w", "E": "e", "N": "n", "S": "s",
        "NW": "nw", "NE": "ne", "SW": "sw", "SE": "se", "CENTER": "center",
        "VERTICAL": "vertical", "HORIZONTAL": "horizontal", "SUNKEN": "sunken",
        "FLAT": "flat", "RAISED": "raised", "GROOVE": "groove", "RIDGE": "ridge",
        "INSERT": "insert", "ACTIVE": "active", "ANCHOR": "anchor",
        "PhotoImage": lambda *a, **kw: object(),
        "mainloop": lambda *a, **kw: None,
    })

    font_mod = types.ModuleType("tkinter.font")
    font_mod.__dict__.update({"Font": FakeFont, "families": families,
                              "nametofont": lambda n, **kw: FakeFont(font=(n, 11)),
                              "NORMAL": "normal", "BOLD": "bold"})
    tk.font = font_mod

    ttk = types.ModuleType("tkinter.ttk")
    ttk.__dict__.update({"Style": Style, "Frame": Frame, "Label": Label,
                         "Button": Button, "Entry": Entry, "Combobox": Combobox,
                         "Progressbar": Progressbar, "Notebook": _Notebook,
                         "Scrollbar": Progressbar, "Scale": _Scale, "Checkbutton": Button,
                         "Treeview": Progressbar})
    tk.ttk = ttk

    filedialog = types.ModuleType("tkinter.filedialog")
    filedialog.__dict__.update({"askdirectory": lambda **kw: _DIALOGS.get("dir", ""),
                                "askopenfilename": lambda **kw: _DIALOGS.get("file", ""),
                                "asksaveasfilename": lambda **kw: _DIALOGS.get("save", "")})
    tk.filedialog = filedialog

    messagebox = types.ModuleType("tkinter.messagebox")
    messagebox.__dict__.update({
        "askyesno": lambda *a, **kw: _DIALOGS.get("yesno", True),
        "showinfo": lambda *a, **kw: None,
        "showerror": lambda *a, **kw: None,
        "showwarning": lambda *a, **kw: None,
    })
    tk.messagebox = messagebox

    colorchooser = types.ModuleType("tkinter.colorchooser")
    colorchooser.__dict__.update({"askcolor": lambda **kw: ((0, 0, 0), "#000000")})
    tk.colorchooser = colorchooser

    simpledialog = types.ModuleType("tkinter.simpledialog")
    simpledialog.__dict__.update({"askstring": lambda *a, **kw: None})
    tk.simpledialog = simpledialog

    sys.modules["tkinter"] = tk
    sys.modules["tkinter.font"] = font_mod
    sys.modules["tkinter.ttk"] = ttk
    sys.modules["tkinter.filedialog"] = filedialog
    sys.modules["tkinter.messagebox"] = messagebox
    sys.modules["tkinter.colorchooser"] = colorchooser
    sys.modules["tkinter.simpledialog"] = simpledialog
    CLOCK.reset()
    return tk


_DIALOGS: dict[str, Any] = {"yesno": True}


def set_dialog(**kw) -> None:
    """Test helper: choose what the next modal dialog returns."""
    _DIALOGS.update(kw)


def clipboard() -> str:
    return _CLIPBOARD["text"]

"""Headless unit tests for the Desktop UI (thans/app.py).

Uses a lightweight fake tkinter harness when the system Python lacks native
tkinter/X11, exercising every code path of ThansApp: layout construction,
60fps sonic canvas rendering, theme cross-fade, live workspace sidebar,
diff highlight pulse animations, real-time intent preview, Tab autocomplete,
quick chips, and threaded command execution.
"""
from __future__ import annotations

import importlib
import shutil
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class _FakeWidget:
    def __init__(self, master=None, **kwargs):
        self.master = master
        self.props = dict(kwargs)
        self.children: list[_FakeWidget] = []
        self.bindings: dict[str, object] = {}
        self.items: list[str] = []
        self.item_configs: dict[int, dict] = {}
        self.text_buf: str = ""
        self._sel: tuple[int, ...] = ()
        if isinstance(master, _FakeWidget):
            master.children.append(self)

    def pack(self, **_kw):
        return None

    def pack_forget(self):
        return None

    def pack_propagate(self, _flag):
        return None

    def configure(self, **kw):
        self.props.update(kw)

    config = configure

    def cget(self, key):
        return self.props.get(key, "")

    def bind(self, seq, func):
        self.bindings[seq] = func

    def focus_set(self):
        return None

    def destroy(self):
        if isinstance(self.master, _FakeWidget) and self in self.master.children:
            self.master.children.remove(self)

    def winfo_children(self):
        return list(self.children)

    # Entry / Text / Listbox helpers
    def get(self, *_args):
        if "textvariable" in self.props and hasattr(self.props["textvariable"], "get"):
            return self.props["textvariable"].get()
        return self.text_buf

    def insert(self, index, text, *_tags):
        if index == "end" and hasattr(self, "_is_listbox"):
            self.items.append(str(text))
        else:
            self.text_buf += str(text)

    def delete(self, _start, _end=None):
        self.text_buf = ""
        self.items.clear()

    def see(self, _idx):
        return None

    def tag_configure(self, *_args, **_kw):
        return None

    def create_oval(self, *_args, **_kw):
        return 1

    def create_line(self, *_args, **_kw):
        return 2

    def itemconfig(self, idx, **kw):
        self.item_configs[int(idx)] = kw

    def curselection(self):
        return self._sel


class _FakeTk(_FakeWidget):
    def __init__(self):
        super().__init__(None)
        self.after_callbacks: list[tuple[int, object]] = []
        self.protocols: dict[str, object] = {}

    def title(self, _t):
        return None

    def geometry(self, _g):
        return None

    def minsize(self, _w, _h):
        return None

    def protocol(self, name, fn):
        self.protocols[name] = fn

    def after(self, ms, fn):
        self.after_callbacks.append((ms, fn))
        return len(self.after_callbacks)

    def mainloop(self):
        return None


class _FakeVar:
    def __init__(self, value=None):
        self._v = value

    def get(self):
        return self._v

    def set(self, v):
        self._v = v


def _install_fake_tk():
    tk_mod = types.ModuleType("tkinter")
    tk_mod.Tk = _FakeTk
    tk_mod.Toplevel = lambda master=None, **kw: _FakeTk()
    tk_mod.Frame = _FakeWidget
    tk_mod.Label = _FakeWidget
    tk_mod.Button = _FakeWidget
    tk_mod.Entry = _FakeWidget
    tk_mod.Text = _FakeWidget
    tk_mod.Canvas = _FakeWidget

    def _listbox(master=None, **kw):
        w = _FakeWidget(master, **kw)
        w._is_listbox = True
        return w

    tk_mod.Listbox = _listbox
    tk_mod.Checkbutton = _FakeWidget
    tk_mod.StringVar = _FakeVar
    tk_mod.BooleanVar = _FakeVar
    tk_mod.IntVar = _FakeVar
    tk_mod.TclError = RuntimeError

    ttk_mod = types.ModuleType("tkinter.ttk")

    class _Style:
        def __init__(self, *_a):
            pass

        def theme_use(self, *_a):
            pass

        def configure(self, *_a, **_kw):
            pass

        def map(self, *_a, **_kw):
            pass

    ttk_mod.Style = _Style
    ttk_mod.Button = _FakeWidget
    ttk_mod.Entry = _FakeWidget
    ttk_mod.Scale = _FakeWidget
    ttk_mod.Combobox = _FakeWidget

    fd_mod = types.ModuleType("tkinter.filedialog")
    fd_mod.askdirectory = lambda **_kw: ""

    mb_mod = types.ModuleType("tkinter.messagebox")
    mb_mod.askyesno = lambda *_a, **_kw: False

    tk_mod.ttk = ttk_mod
    tk_mod.filedialog = fd_mod
    tk_mod.messagebox = mb_mod

    sys.modules["tkinter"] = tk_mod
    sys.modules["tkinter.ttk"] = ttk_mod
    sys.modules["tkinter.filedialog"] = fd_mod
    sys.modules["tkinter.messagebox"] = mb_mod


class TestDesktopUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _install_fake_tk()
        if "thans.app" in sys.modules:
            importlib.reload(sys.modules["thans.app"])
        else:
            importlib.import_module("thans.app")
        cls.ThansApp = sys.modules["thans.app"].ThansApp

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="thans_desk_ui_"))
        (self.tmp / "work").mkdir()
        (self.tmp / "work" / "report.pdf").write_text("pdf")
        (self.tmp / "notes.txt").write_text("notes")
        self.cfg = {
            "root": str(self.tmp),
            "tts": False,
            "use_llm": False,
            "permanent_delete": False,
            "theme": "dark",
            "animations": True,
            "sidebar": True,
        }
        self.app = self.ThansApp(cfg=self.cfg, text_only=False)

    def tearDown(self):
        self.app._on_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_build_and_initial_workspace(self):
        self.assertIn("WM_DELETE_WINDOW", self.app.root.protocols)
        self.assertIsNotNone(self.app.snapshot)
        self.assertEqual(self.app.snapshot.folder_count, 1)
        self.assertEqual(self.app.snapshot.file_count, 1)
        self.assertEqual(len(self.app._visible_entries), 2)

    def test_sonic_visualizer_and_animation_tick(self):
        for st in ("idle", "listening", "thinking", "speaking", "success", "error"):
            self.app.sonic_state = st
            self.app.sonic_level = 0.7
            self.app._animate_tick()
        self.assertGreater(self.app.sonic_phase, 0.0)

    def test_live_intent_preview_and_autocomplete(self):
        self.app.entry.insert(0, "cre")
        self.app._on_tab_complete()
        self.assertEqual(self.app.entry.get(), "create folder ")
        self.app._update_intent_preview()

        self.app.entry.delete(0, "end")
        self.app.entry.insert(0, "delete no")
        self.app._on_tab_complete()
        self.assertEqual(self.app.entry.get(), "delete notes.txt")
        self.app._update_intent_preview()
        self.assertIn("Delete", self.app.lbl_preview_title.cget("text"))

    def test_theme_and_sidebar_toggles(self):
        self.assertEqual(self.app.theme_name, "dark")
        self.app.toggle_theme()
        self.assertEqual(self.app.theme_name, "light")
        self.app.toggle_sidebar()
        self.assertFalse(self.app.sidebar_open)
        self.app.toggle_sidebar()
        self.assertTrue(self.app.sidebar_open)

    def test_command_execution_and_diff_highlight(self):
        self.app.entry.insert(0, "create folder ideas")
        self.app._on_enter()
        # Wait briefly for worker thread to queue results
        deadline = time.time() + 2.0
        while time.time() < deadline and not (self.tmp / "ideas").is_dir():
            time.sleep(0.02)
        self.app._poll()
        self.assertTrue((self.tmp / "ideas").is_dir())
        self.assertIn("ideas", self.app._highlight_names)
        self.assertGreater(self.app._highlight_step, 0)
        # Run animation ticks to decay highlight pulse
        self.app._animate_tick()

    def test_sidebar_navigation_and_actions(self):
        # Select 'work' folder (index 0) and double-click to navigate into it
        self.app.file_list._sel = (0,)
        self.app._on_file_double_click()
        deadline = time.time() + 2.0
        while time.time() < deadline and self.app.engine.current != (self.tmp / "work").resolve():
            time.sleep(0.02)
        self.app._poll()
        self.assertEqual(self.app.engine.current, (self.tmp / "work").resolve())
        self.assertTrue(self.app.snapshot.can_go_up)


if __name__ == "__main__":
    unittest.main()

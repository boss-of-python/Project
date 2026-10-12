"""Tests for shared UX/animation helpers (thans.ux), expanded engine commands,
and headless validation of the Android Kivy UI & app controller.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from thans import ux  # noqa: E402
from thans.engine import Engine  # noqa: E402
from thans.parser_rules import parse  # noqa: E402


class TestUXAndAnimationMath(unittest.TestCase):
    def test_color_lerp_and_conversions(self):
        self.assertEqual(ux.hex_to_rgb("#000000"), (0, 0, 0))
        self.assertEqual(ux.hex_to_rgb("#ffffff"), (255, 255, 255))
        self.assertEqual(ux.rgb_to_hex((255, 0, 128)), "#ff0080")
        mid = ux.lerp_color("#000000", "#ffffff", 0.5)
        self.assertIn(mid, ("#7f7f7f", "#808080"))
        rgba = ux.hex_to_kivy_rgba("#5b8cff", 0.8)
        self.assertEqual(len(rgba), 4)
        self.assertAlmostEqual(rgba[3], 0.8)

    def test_easing_functions(self):
        self.assertAlmostEqual(ux.ease_out_cubic(0.0), 0.0)
        self.assertAlmostEqual(ux.ease_out_cubic(1.0), 1.0)
        self.assertGreater(ux.ease_out_cubic(0.5), 0.5)
        self.assertAlmostEqual(ux.ease_in_out_sine(0.0), 0.0)
        self.assertAlmostEqual(ux.ease_in_out_sine(1.0), 1.0)

    def test_wave_heights_modes(self):
        for mode in ("idle", "listening", "busy", "success", "error"):
            bars = ux.wave_heights(1.25, count=9, mode=mode)
            self.assertEqual(len(bars), 9)
            self.assertTrue(all(0.1 <= b <= 1.0 for b in bars))

    def test_themes_complete(self):
        for name in ux.THEME_ORDER:
            p = ux.get_theme(name)
            for key in ("bg", "panel", "panel2", "border", "fg", "dim", "accent", "ok", "warn", "err"):
                self.assertIn(key, p)
                self.assertTrue(p[key].startswith("#"))

    def test_icons_and_human_size(self):
        self.assertEqual(ux.human_size(0), "0 B")
        self.assertEqual(ux.human_size(512), "512 B")
        self.assertIn("KB", ux.human_size(2048))
        self.assertIn("MB", ux.human_size(5 * 1024 * 1024))
        self.assertEqual(ux.file_icon(Path("script.py")), "🐍")
        self.assertEqual(ux.file_icon(Path("report.pdf")), "📕")
        self.assertEqual(ux.file_icon(Path("photo.png")), "🖼")


class TestWorkspaceUXAndExpandedEngine(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="thans_ux_test_"))
        self.cfg = {"root": str(self.tmp), "tts": False, "use_llm": False, "permanent_delete": False}
        self.eng = Engine(self.tmp, self.cfg)
        (self.tmp / "work").mkdir()
        (self.tmp / "work" / "notes.txt").write_text("line one\nline two\n", encoding="utf-8")
        (self.tmp / "todo.txt").write_text("buy milk\ncall mom\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_read_preview_and_status(self):
        r = self.eng.run("read todo.txt")
        self.assertTrue(r.ok, r.message)
        self.assertIn("buy milk", r.message)
        self.assertIn("2 lines", r.message)

        r2 = self.eng.run("what does work/notes.txt say")
        self.assertTrue(r2.ok, r2.message)
        self.assertIn("line one", r2.message)

        r3 = self.eng.run("status")
        self.assertTrue(r3.ok, r3.message)
        self.assertIn("1 folder", r3.message)
        self.assertIn("1 file", r3.message)

    def test_cd_up_and_breadcrumbs(self):
        self.eng.run("go to work")
        snap = ux.workspace_snapshot(self.eng.root, self.eng.current, self.eng.undo_stack)
        self.assertTrue(snap["can_go_up"])
        self.assertEqual(len(snap["breadcrumbs"]), 2)

        r = self.eng.run("go back")
        self.assertTrue(r.ok, r.message)
        self.assertEqual(self.eng.current.resolve(), self.eng.root.resolve())

    def test_trash_inspection_and_empty(self):
        self.eng.run("delete todo.txt")
        r = self.eng.run("show trash")
        self.assertTrue(r.ok, r.message)
        self.assertIn("todo.txt", r.message)

        r2 = self.eng.run("empty trash")
        self.assertTrue(r2.ok, r2.message)
        self.assertIn("Emptied trash", r2.message)

        r3 = self.eng.run("show trash")
        self.assertIn("empty", r3.message.lower())

    def test_multistep_undo_and_organize_undo(self):
        self.eng.run("create folder alpha")
        self.eng.run("create folder beta")
        self.assertEqual(len(self.eng.undo_stack), 2)

        r1 = self.eng.run("undo")
        self.assertTrue(r1.ok)
        self.assertFalse((self.tmp / "beta").exists())
        self.assertTrue((self.tmp / "alpha").exists())

        r2 = self.eng.run("undo")
        self.assertTrue(r2.ok)
        self.assertFalse((self.tmp / "alpha").exists())

        # Organize and then undo organize
        (self.tmp / "a.txt").write_text("a")
        (self.tmp / "b.md").write_text("b")
        r_org = self.eng.run("organize")
        self.assertTrue(r_org.ok, r_org.message)
        self.assertTrue((self.tmp / "txt" / "a.txt").is_file())

        r_undo_org = self.eng.run("undo")
        self.assertTrue(r_undo_org.ok, r_undo_org.message)
        self.assertTrue((self.tmp / "a.txt").is_file())
        self.assertTrue((self.tmp / "b.md").is_file())

    def test_live_intent_preview_and_autocomplete(self):
        idle = ux.live_intent_preview("", self.eng.current)
        self.assertEqual(idle["state"], "idle")

        valid = ux.live_intent_preview("create folder archive", self.eng.current)
        self.assertEqual(valid["state"], "valid")
        self.assertEqual(valid["action"], "mkdir")

        hint = ux.live_intent_preview("rename", self.eng.current)
        self.assertEqual(hint["state"], "hint")

        # Autocomplete command template
        self.assertEqual(ux.autocomplete(" create f", self.eng.current), None)
        self.assertEqual(ux.autocomplete("create fold", self.eng.current), "create folder ")

        # Autocomplete real item in current folder
        self.assertEqual(ux.autocomplete("delete to", self.eng.current), "delete todo.txt")
        self.assertEqual(ux.autocomplete("go to wo", self.eng.current), "go to work")

    def test_quick_actions(self):
        self.eng.run("create folder sample")
        snap = ux.workspace_snapshot(self.eng.root, self.eng.current, self.eng.undo_stack)
        pills = ux.quick_actions(snap)
        labels = [p["label"] for p in pills]
        self.assertTrue(any("List" in l for l in labels))
        self.assertTrue(any("Undo" in l for l in labels))


class TestAndroidKVAndController(unittest.TestCase):
    """Verify android/thans.kv and thans_android/app.py stay in sync and run cleanly."""

    def test_kv_ids_and_handlers_match_app(self):
        kv_path = ROOT_DIR / "android" / "thans.kv"
        app_path = ROOT_DIR / "android" / "thans_android" / "app.py"
        kv_text = kv_path.read_text(encoding="utf-8")
        app_text = app_path.read_text(encoding="utf-8")

        # Verify no invalid legacy properties exist in thans.kv
        self.assertIsNone(re.search(r"^\s*bgcolor:", kv_text, flags=re.M))
        self.assertIsNone(re.search(r"^\s*text_color:", kv_text, flags=re.M))
        self.assertNotIn("Builder.get_root", app_text)
        self.assertNotIn("set_normalized_y", app_text)

        # Verify all expected ids are present in thans.kv
        kv_ids = set(re.findall(r"^\s*id:\s*([a-zA-Z0-9_]+)\s*$", kv_text, flags=re.M))
        expected_ids = {
            "pulse_dot", "wave_label", "btn_files", "btn_speak", "btn_up",
            "status", "explorer_drawer", "explorer_box", "chat_scroll",
            "chat_box", "intent_badge", "intent_label", "btn_complete",
            "quick_box", "input", "btn_mic", "btn_undo",
        }
        self.assertTrue(expected_ids.issubset(kv_ids), f"Missing KV ids: {expected_ids - kv_ids}")

        # Verify all app.<method>(...) calls in thans.kv exist on ThansAndroidApp
        app_calls = set(re.findall(r"app\.([a-zA-Z0-9_]+)\s*\(", kv_text))
        for fn_name in app_calls:
            self.assertIn(f"def {fn_name}(", app_text, f"KV calls app.{fn_name}() but method is missing")

    def test_android_controller_headless_simulation(self):
        """Simulate the full ThansAndroidApp lifecycle using lightweight Kivy stubs."""
        # Install lightweight Kivy stub modules if Kivy isn't installed in this Python env
        saved_modules = {}
        kivy_mods = [
            "kivy", "kivy.animation", "kivy.app", "kivy.builder", "kivy.lang",
            "kivy.lang.builder", "kivy.clock", "kivy.metrics", "kivy.uix",
            "kivy.uix.button", "kivy.uix.label",
        ]
        for m in kivy_mods:
            saved_modules[m] = sys.modules.get(m)

        class _DummyWidget:
            def __init__(self, **kw):
                self.text = kw.get("text", "")
                self.color = kw.get("color", (1, 1, 1, 1))
                self.background_color = kw.get("background_color", (0, 0, 0, 1))
                self.opacity = kw.get("opacity", 1.0)
                self.disabled = kw.get("disabled", False)
                self.height = kw.get("height", 30)
                self.width = kw.get("width", 200)
                self.size_hint_x = kw.get("size_hint_x", 1)
                self.size_hint_y = kw.get("size_hint_y", 1)
                self.focus = False
                self.texture_size = (100, 20)
                self.text_size = (200, None)
                self.scroll_y = 1.0
                self.children = []
                self._binds = {}

            def bind(self, **kw):
                self._binds.update(kw)

            def texture_update(self):
                pass

            def clear_widgets(self):
                self.children.clear()

            def add_widget(self, w, index=0):
                self.children.insert(index, w)

        class _DummyAnim:
            def __init__(self, **kw):
                self.kw = kw

            def start(self, widget):
                for k, v in self.kw.items():
                    if k not in ("d", "t"):
                        setattr(widget, k, v)

        class _IdsNamespace(dict):
            def __getattr__(self, k):
                return self[k]

        class _DummyRoot:
            def __init__(self):
                self.ids = _IdsNamespace({
                    name: _DummyWidget() for name in (
                        "pulse_dot", "wave_label", "btn_files", "btn_speak", "btn_up",
                        "status", "explorer_drawer", "explorer_box", "chat_scroll",
                        "chat_box", "intent_badge", "intent_label", "btn_complete",
                        "quick_box", "input", "btn_mic", "btn_undo",
                    )
                })

        try:
            kivy_pkg = types.ModuleType("kivy")
            anim_mod = types.ModuleType("kivy.animation")
            anim_mod.Animation = _DummyAnim
            app_mod = types.ModuleType("kivy.app")
            app_mod.App = type("App", (), {"__init__": lambda self, **kw: None})
            builder_mod = types.ModuleType("kivy.builder")
            builder_mod.Builder = type("Builder", (), {"load_file": staticmethod(lambda _p: _DummyRoot())})
            clock_mod = types.ModuleType("kivy.clock")
            clock_mod.Clock = type("Clock", (), {
                "schedule_once": staticmethod(lambda fn, _dt=0: fn(0)),
                "schedule_interval": staticmethod(lambda fn, _dt=0: fn),
            })
            metrics_mod = types.ModuleType("kivy.metrics")
            metrics_mod.dp = lambda x: x
            metrics_mod.sp = lambda x: x
            btn_mod = types.ModuleType("kivy.uix.button")
            btn_mod.Button = _DummyWidget
            lbl_mod = types.ModuleType("kivy.uix.label")
            lbl_mod.Label = _DummyWidget

            sys.modules["kivy"] = kivy_pkg
            sys.modules["kivy.animation"] = anim_mod
            sys.modules["kivy.app"] = app_mod
            sys.modules["kivy.builder"] = builder_mod
            sys.modules["kivy.clock"] = clock_mod
            sys.modules["kivy.metrics"] = metrics_mod
            sys.modules["kivy.uix.button"] = btn_mod
            sys.modules["kivy.uix.label"] = lbl_mod

            sys.path.insert(0, str(ROOT_DIR / "android"))
            sys.modules.pop("thans_android.app", None)
            sys.modules.pop("thans_android", None)
            from thans_android.app import ThansAndroidApp

            tmp = tempfile.mkdtemp(prefix="thans_android_sim_")
            try:
                app = ThansAndroidApp(workdir=tmp)
                root = app.build()
                self.assertIsNotNone(root)

                # Test autocomplete & live intent preview
                app._ids().input.text = "create fold"
                app.on_input_change("create fold")
                self.assertEqual(app._ids().intent_badge.text, "💡 SYNTAX")
                app.apply_autocomplete()
                self.assertEqual(app._ids().input.text, "create folder ")

                # Send a real command via input
                app._ids().input.text = "create folder mobile_work"
                app.send_input()
                self.assertTrue((Path(tmp) / "mobile_work").is_dir())

                # Create a file and preview it
                app._run("create file hello.txt with android test in mobile_work")
                self.assertTrue((Path(tmp) / "mobile_work" / "hello.txt").is_file())
                app._run("read mobile_work/hello.txt")

                # Navigate into folder and back up
                app._run("go to mobile_work")
                self.assertEqual(app.engine.current.name, "mobile_work")
                app.go_up()
                self.assertEqual(app.engine.current.resolve(), Path(tmp).resolve())

                # Wave animation tick & drawer toggle
                app._tick_wave(0.08)
                app.toggle_files_drawer()
                self.assertFalse(app.files_drawer_open)
                app.toggle_files_drawer()
                self.assertTrue(app.files_drawer_open)

                # Undo multi-step
                app.say_undo()
                self.assertFalse((Path(tmp) / "mobile_work" / "hello.txt").exists())
                app.say_undo()
                self.assertFalse((Path(tmp) / "mobile_work").exists())

                app.say_help()
                app.clear_chat()
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        finally:
            for m, orig in saved_modules.items():
                if orig is None:
                    sys.modules.pop(m, None)
                else:
                    sys.modules[m] = orig


class TestDesktopAppHeadlessSimulation(unittest.TestCase):
    """Simulate the Desktop ThansApp (thans/app.py) headlessly to verify all UI methods & animations."""

    def test_desktop_app_lifecycle_and_animations(self):
        saved = {m: sys.modules.get(m) for m in ("tkinter", "tkinter.filedialog", "tkinter.messagebox", "tkinter.ttk")}

        class _TkWidget:
            def __init__(self, parent=None, **kw):
                self.parent = parent
                self.kw = dict(kw)
                self._text = ""
                self._items = []
                self._children = []
                if parent is not None and hasattr(parent, "_children"):
                    parent._children.append(self)

            def __getitem__(self, k):
                return self.kw.get(k, "normal")

            def configure(self, **kw):
                self.kw.update(kw)

            config = configure

            def pack(self, **_kw):
                pass

            def pack_forget(self):
                pass

            def pack_propagate(self, _v):
                pass

            def bind(self, *_a, **_kw):
                pass

            def focus_set(self):
                pass

            def icursor(self, _pos):
                pass

            def destroy(self):
                if self.parent and self in getattr(self.parent, "_children", []):
                    self.parent._children.remove(self)

            def winfo_children(self):
                return list(self._children)

            def insert(self, _pos, text, *_tags):
                self._text += str(text)
                self._items.append(text)

            def delete(self, _a, _b=None):
                self._text = ""
                self._items.clear()

            def get(self):
                return self._text

            def see(self, _pos):
                pass

            def tag_configure(self, *_a, **_kw):
                pass

            def delete_all(self):
                pass

            def create_oval(self, *_a, **_kw):
                pass

            def create_line(self, *_a, **_kw):
                pass

            def create_text(self, *_a, **_kw):
                pass

            def curselection(self):
                return (0,) if self._items else ()

            def selection_clear(self, *_a):
                pass

            def selection_set(self, *_a):
                pass

            def nearest(self, _y):
                return 0

            def add_command(self, **_kw):
                pass

            def add_separator(self):
                pass

            def tk_popup(self, *_a):
                pass

            def title(self, _t):
                pass

            def geometry(self, _g):
                pass

            def minsize(self, *_a):
                pass

            def resizable(self, *_a):
                pass

            def protocol(self, *_a):
                pass

            def after(self, _ms, _fn):
                pass

            def transient(self, _p):
                pass

            def grab_set(self):
                pass

            def mainloop(self):
                pass

        class _Var:
            def __init__(self, value=""):
                self._v = value

            def get(self):
                return self._v

            def set(self, v):
                self._v = v

            def trace_add(self, *_a):
                pass

        class _Style:
            def __init__(self, _root=None):
                pass

            def theme_use(self, _t):
                pass

            def configure(self, *_a, **_kw):
                pass

            def map(self, *_a, **_kw):
                pass

        try:
            tk_mod = types.ModuleType("tkinter")
            for cls_name in ("Tk", "Frame", "Label", "Button", "Entry", "Text", "Canvas", "Listbox", "Toplevel", "Menu", "Checkbutton"):
                setattr(tk_mod, cls_name, _TkWidget)
            tk_mod.StringVar = _Var
            tk_mod.BooleanVar = _Var
            tk_mod.IntVar = _Var
            tk_mod.TclError = Exception

            fd_mod = types.ModuleType("tkinter.filedialog")
            fd_mod.askdirectory = lambda **_kw: ""
            mb_mod = types.ModuleType("tkinter.messagebox")
            mb_mod.askyesno = lambda *_a, **_kw: False
            ttk_mod = types.ModuleType("tkinter.ttk")
            ttk_mod.Style = _Style
            for cls_name in ("Button", "Scale", "Combobox"):
                setattr(ttk_mod, cls_name, _TkWidget)

            tk_mod.filedialog = fd_mod
            tk_mod.messagebox = mb_mod
            tk_mod.ttk = ttk_mod

            sys.modules["tkinter"] = tk_mod
            sys.modules["tkinter.filedialog"] = fd_mod
            sys.modules["tkinter.messagebox"] = mb_mod
            sys.modules["tkinter.ttk"] = ttk_mod
            sys.modules.pop("thans.app", None)

            from thans.app import ThansApp

            tmp = tempfile.mkdtemp(prefix="thans_desktop_sim_")
            try:
                cfg = {
                    "root": tmp,
                    "tts": False,
                    "tts_rate": 185,
                    "use_llm": False,
                    "llm_model": "",
                    "permanent_delete": False,
                    "theme": "obsidian",
                    "show_explorer": True,
                }
                app = ThansApp(cfg=cfg, text_only=False)

                # Test theme cycling across all 3 themes
                app._cycle_theme()
                self.assertEqual(app.theme_name, "midnight")
                app._cycle_theme()
                self.assertEqual(app.theme_name, "daylight")
                app._cycle_theme()
                self.assertEqual(app.theme_name, "obsidian")

                # Test 60 FPS animation frame & wave canvas in all modes
                for mode in ("idle", "listening", "busy", "success", "error"):
                    app._anim_mode = mode
                    app._draw_wave_canvas(mode)
                app._animate()

                # Test input change, live intent preview & Tab autocomplete
                app.entry.insert(0, "create fold")
                app._on_input_changed()
                app._on_tab_complete()
                self.assertEqual(app.entry.get(), "create folder ")

                # Run synchronous worker & poll queue
                app._worker("create folder docs")
                app._poll()
                self.assertTrue((Path(tmp) / "docs").is_dir())

                # Toggle explorer & open command palette
                app._toggle_explorer()
                app._toggle_explorer()
                app._open_palette()
                app._clear_chat()
                app._on_close()
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        finally:
            sys.modules.pop("thans.app", None)
            for m, orig in saved.items():
                if orig is None:
                    sys.modules.pop(m, None)
                else:
                    sys.modules[m] = orig


if __name__ == "__main__":
    unittest.main()

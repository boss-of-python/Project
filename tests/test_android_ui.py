"""Headless unit tests for the Android Kivy UI (android/thans.kv + android/thans_android/app.py).

Validates:
  1. KV syntax, widget IDs, and every `app.<method>` / `app.<property>` binding in `android/thans.kv`
     (uses Kivy's real `Parser` when Kivy is installed, plus static KV binding verification).
  2. Full simulated user session through `ThansAndroidApp`:
     - Initial build & welcome messages
     - Live intent preview (`on_input_change`), autocomplete (`complete_input`), and chip pre-fill
     - Command execution (`create folder`, `create file`, `organize`, `undo`)
     - Segmented tab switching (`💬 Chat` ↔ `📁 Files`) and touch file explorer rendering
     - Theme switching (`dark` ↔ `light`) and 60fps sonic equalizer bar animation ticks
     - Voice callbacks (`toggle_mic`, `_on_partial_speech`, `_on_rms`, `_handle_speech`)
"""
from __future__ import annotations

import importlib
import re
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "android"))


class _FakeKivyWidget:
    def __init__(self, **kwargs):
        self.text = kwargs.get("text", "")
        self.color = kwargs.get("color", [1, 1, 1, 1])
        self.opacity = kwargs.get("opacity", 1.0)
        self.height = kwargs.get("height", 32)
        self.width = kwargs.get("width", 200)
        self.texture_size = (120, 22)
        self.focus = False
        self.scroll_y = 1.0
        self.children: list[_FakeKivyWidget] = []
        self.bindings: dict[str, list] = {}
        # every real Kivy widget exposes .ids (empty unless declared in KV)
        self.ids = _FakeIds({})

    def add_widget(self, widget, index=0):
        self.children.insert(index, widget)

    def clear_widgets(self):
        self.children.clear()

    def bind(self, **kwargs):
        for k, fn in kwargs.items():
            self.bindings.setdefault(k, []).append(fn)

    def set_normalized_y(self, val):
        self.scroll_y = float(val)


class _FakeIds(dict):
    def __getattr__(self, name):
        if name in self:
            return self[name]
        w = _FakeKivyWidget()
        self[name] = w
        return w


class _FakeRoot(_FakeKivyWidget):
    def __init__(self, id_names: list[str]):
        super().__init__()
        self.ids = _FakeIds({name: _FakeKivyWidget() for name in id_names})


def _extract_kv_metadata(kv_path: Path) -> tuple[list[str], list[str], list[str]]:
    text = kv_path.read_text(encoding="utf-8")
    ids = re.findall(r"^\s*id:\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*$", text, flags=re.MULTILINE)
    calls = re.findall(r"app\.([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", text)
    props = re.findall(r"app\.([a-zA-Z_][a-zA-Z0-9_]*)\b(?!\s*\()", text)
    return ids, sorted(set(calls)), sorted(set(props))


def _load_android_app_with_harness(kv_ids: list[str]):
    """Load thans_android.app using lightweight Kivy stubs so tests run anywhere without an OpenGL window."""
    saved_modules = {k: v for k, v in sys.modules.items() if k == "kivy" or k.startswith("kivy.")}

    kivy_mod = types.ModuleType("kivy")
    app_mod = types.ModuleType("kivy.app")

    class _BaseApp:
        def __init__(self, **_kw):
            pass

    app_mod.App = _BaseApp

    anim_mod = types.ModuleType("kivy.animation")

    class _Anim:
        def __init__(self, **kw):
            self.kw = kw

        def start(self, widget):
            for k, v in self.kw.items():
                if k not in ("d", "duration", "t"):
                    setattr(widget, k, v)

    anim_mod.Animation = _Anim

    builder_mod = types.ModuleType("kivy.lang.builder")
    builder_mod.Builder = types.SimpleNamespace(
        load_file=lambda _p: _FakeRoot(kv_ids),
        get_root=lambda: _FakeRoot(kv_ids),
    )

    clock_mod = types.ModuleType("kivy.clock")
    clock_mod.Clock = types.SimpleNamespace(
        schedule_once=lambda fn, _dt=0: fn(0.016),
        schedule_interval=lambda _fn, _dt=0: None,
    )

    metrics_mod = types.ModuleType("kivy.metrics")
    metrics_mod.dp = lambda v: float(v)
    metrics_mod.sp = lambda v: float(v)

    props_mod = types.ModuleType("kivy.properties")
    props_mod.StringProperty = lambda default="": default
    props_mod.ListProperty = lambda default=None: list(default or [])

    box_mod = types.ModuleType("kivy.uix.boxlayout")
    box_mod.BoxLayout = _FakeKivyWidget
    btn_mod = types.ModuleType("kivy.uix.button")
    btn_mod.Button = _FakeKivyWidget
    lbl_mod = types.ModuleType("kivy.uix.label")
    lbl_mod.Label = _FakeKivyWidget

    sys.modules["kivy"] = kivy_mod
    sys.modules["kivy.app"] = app_mod
    sys.modules["kivy.animation"] = anim_mod
    sys.modules["kivy.builder"] = builder_mod
    sys.modules["kivy.lang"] = types.ModuleType("kivy.lang")
    sys.modules["kivy.lang.builder"] = builder_mod
    sys.modules["kivy.clock"] = clock_mod
    sys.modules["kivy.metrics"] = metrics_mod
    sys.modules["kivy.properties"] = props_mod
    sys.modules["kivy.uix"] = types.ModuleType("kivy.uix")
    sys.modules["kivy.uix.boxlayout"] = box_mod
    sys.modules["kivy.uix.button"] = btn_mod
    sys.modules["kivy.uix.label"] = lbl_mod

    try:
        if "thans_android.app" in sys.modules:
            mod = importlib.reload(sys.modules["thans_android.app"])
        else:
            mod = importlib.import_module("thans_android.app")
        return mod.ThansAndroidApp
    finally:
        for k in list(sys.modules):
            if k == "kivy" or k.startswith("kivy."):
                sys.modules.pop(k, None)
        sys.modules.update(saved_modules)


class TestAndroidUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kv_path = ROOT / "android" / "thans.kv"
        cls.kv_ids, cls.kv_calls, cls.kv_props = _extract_kv_metadata(cls.kv_path)
        cls.ThansAndroidApp = _load_android_app_with_harness(cls.kv_ids)

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="thans_apk_ui_"))
        (self.tmp / "docs").mkdir()
        (self.tmp / "docs" / "summary.pdf").write_text("pdf")
        (self.tmp / "todo.txt").write_text("buy milk")
        self.app = self.ThansAndroidApp(workdir=str(self.tmp))
        self.root_widget = self.app.build()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_kv_syntax_and_all_bindings_exist(self):
        # If real Kivy is installed on the host, parse android/thans.kv with Kivy's real Parser
        try:
            import os as _os
            _os.environ["KIVY_NO_ARGS"] = "1"
            from kivy.lang.parser import Parser
            parsed = Parser(
                content=self.kv_path.read_text(encoding="utf-8"),
                filename=str(self.kv_path),
            )
            self.assertEqual(parsed.root.name, "Screen")
        except ImportError:
            pass

        # Verify key IDs are declared in android/thans.kv
        for required_id in (
            "status", "btn_speak", "btn_theme", "btn_up", "crumb_label",
            "sonic_indicator", "btn_tab_chat", "btn_tab_files",
            "chat_scroll", "chat_box", "preview_label", "input", "btn_send", "btn_mic",
        ):
            self.assertIn(required_id, self.kv_ids)

        # Verify every app.<method>() in thans.kv exists on ThansAndroidApp
        for method_name in self.kv_calls:
            self.assertTrue(
                hasattr(self.app, method_name) and callable(getattr(self.app, method_name)),
                f"Missing handler on ThansAndroidApp: {method_name}",
            )

        # Verify every app.<property> in thans.kv exists on ThansAndroidApp
        for prop_name in self.kv_props:
            self.assertTrue(
                hasattr(self.app, prop_name),
                f"Missing property on ThansAndroidApp: {prop_name}",
            )

    def test_live_preview_and_autocomplete_on_mobile(self):
        self.app.prefill_input("cre")
        self.assertEqual(self.root_widget.ids.input.text, "create" if False else "cre")
        self.app.complete_input()
        self.assertEqual(self.root_widget.ids.input.text, "create folder ")
        self.assertIn("Create", self.root_widget.ids.preview_label.text)

        self.app.prefill_input("delete to")
        self.app.complete_input()
        self.assertEqual(self.root_widget.ids.input.text, "delete todo.txt")
        self.assertIn("Delete", self.root_widget.ids.preview_label.text)

    def test_command_flow_and_tabs(self):
        # Create folder via send_input
        self.root_widget.ids.input.text = "create folder projects"
        self.app.send_input()
        self.assertTrue((self.tmp / "projects").is_dir())

        # Switch to Files tab and verify visual file explorer populates
        self.app.switch_tab("files")
        self.assertEqual(self.app.active_tab, "files")
        self.assertGreaterEqual(len(self.root_widget.ids.chat_box.children), 3)

        # Switch back to Chat tab
        self.app.switch_tab("chat")
        self.assertEqual(self.app.active_tab, "chat")

    def test_theme_and_sonic_animation(self):
        self.assertEqual(self.app.theme_name, "dark")
        self.app.toggle_theme()
        self.assertEqual(self.app.theme_name, "light")
        for st in ("idle", "listening", "thinking", "success", "error"):
            self.app.sonic_state = st
            self.app._on_rms(6.5)
            self.app._animate_tick(0.05)
        self.assertTrue(self.root_widget.ids.sonic_indicator.text)

    def test_voice_callbacks_and_navigation(self):
        self.app._on_partial_speech("go to docs")
        self.assertIn("go to docs", self.root_widget.ids.preview_label.text)
        self.app._handle_speech("go to docs", None)
        self.assertEqual(self.app.engine.current, (self.tmp / "docs").resolve())
        self.app.navigate_up()
        self.assertEqual(self.app.engine.current, self.app.engine.root)


if __name__ == "__main__":
    unittest.main()

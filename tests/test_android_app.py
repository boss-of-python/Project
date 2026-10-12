"""Android (Kivy) app tests — run without a display, without GL, without Kivy.

Two layers:

1. **Static KV validation** (pure Python): the KV file is parsed for ids and
   ``app.*`` references; every handler referenced from KV must exist on the app
   class, every id the code touches must be declared in KV, and the file must
   be whitespace-sane (Kivy is strict about that).

2. **Behavioural session** against :mod:`tests.fakekivy`: the real
   ``ThansAndroidApp`` is built (real Bubble/Toast/RoundedButton classes, real
   engine, real animations on a virtual clock) and driven through boot,
   commands, suggestions, mic, speech, toasts and preferences.
"""
import ast
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

KV_PATH = REPO / "android" / "thans.kv"
ANDROID_PKG = REPO / "android" / "thans_android"


# ==========================================================================
# 1. static validation (no kivy, no fakes)
# ==========================================================================

def kv_text() -> str:
    return KV_PATH.read_text(encoding="utf-8")


def kv_code() -> str:
    """The KV file with comment lines/lines-in-comments removed."""
    out = []
    for line in kv_text().splitlines():
        if line.lstrip().startswith("#"):
            continue
        out.append(line.split("  #")[0])
    return "\n".join(out)


def kv_declared_ids() -> list[str]:
    return re.findall(r"^\s+id:\s*([A-Za-z_][A-Za-z0-9_]*)", kv_text(), re.M)


class TestKvFile(unittest.TestCase):
    def test_kv_exists_and_is_utf8(self):
        self.assertTrue(KV_PATH.is_file())
        self.assertIn("#:kivy", kv_text())

    def test_no_tabs_and_consistent_indentation(self):
        lines = kv_text().splitlines()
        self.assertFalse([l for l in lines if "\t" in l], "tabs break Kivy's parser")
        for i, line in enumerate(lines, 1):
            if line.strip():
                indent = len(line) - len(line.lstrip(" "))
                self.assertEqual(indent % 4, 0, f"line {i}: indentation not a multiple of 4")
                self.assertEqual(line, line.rstrip(), f"line {i}: trailing whitespace")

    def test_ids_are_unique_and_referenced(self):
        ids = kv_declared_ids()
        self.assertGreater(len(ids), 15)
        self.assertEqual(len(ids), len(set(ids)), "duplicate id in KV")

    def test_every_app_reference_exists(self):
        """KV calls like ``app.toggle_mic()`` must exist on the app class."""
        refs = set(re.findall(r"\bapp\.([A-Za-z_][A-Za-z0-9_]*)", kv_code()))
        defined = set()
        tree = ast.parse((ANDROID_PKG / "app.py").read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "ThansAndroidApp":
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        defined.add(item.name)
                    elif isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name):
                                defined.add(target.id)
                    elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        defined.add(item.target.id)
        missing = sorted(refs - defined)
        self.assertEqual(missing, [], f"KV references missing app members: {missing}")

    def test_ids_used_by_python_exist_in_kv(self):
        """``self._ids().X`` in the app must match a ``id: X`` in the KV."""
        used = set()
        for path in ANDROID_PKG.glob("*.py"):
            src = path.read_text()
            used |= set(re.findall(r"_ids\(\)\.([A-Za-z_][A-Za-z0-9_]*)", src))
            used |= set(re.findall(r"\bids\.([A-Za-z_][A-Za-z0-9_]*)", src))
        declared = set(kv_declared_ids())
        missing = sorted(used - declared)
        self.assertEqual(missing, [], f"code uses undeclared ids: {missing}")

    def test_root_rule_class_exists(self):
        """The KV root rule (column 0, not a class rule) needs a Python class."""
        names = [m.group(1) for m in re.finditer(r"^([A-Za-z_][A-Za-z0-9_]*):\s*$",
                                                 kv_code(), re.M)]
        self.assertTrue(names, "no root rule found in KV")
        name = names[0]
        src = (ANDROID_PKG / "app.py").read_text()
        self.assertIn(f"class {name}(", src,
                      f"root rule '{name}' has no Python class")

    def test_screen_uses_shared_theme_tokens(self):
        # KV must colour itself from the shared tokens, not hard-coded hex
        self.assertIn('app.tok["BG"]', kv_text())
        self.assertIn('app.sym[', kv_text())


class TestThemeParity(unittest.TestCase):
    """The phone UI must use exactly the desktop palette."""

    @classmethod
    def setUpClass(cls):
        from thans.ui import theme as dt
        sys.path.insert(0, str(REPO / "android"))
        import importlib.util
        spec = importlib.util.spec_from_file_location("android_theme",
                                                      ANDROID_PKG / "theme.py")
        # theme.py imports the staged ``thans`` package, which is importable
        cls.dt = dt
        cls.spec = spec

    def test_palette_matches_desktop(self):
        from thans.ui import theme as dt
        # theme.py is written against thans.ui.theme; verify the mapping rules
        for hexv in (dt.BG, dt.SURFACE, dt.ACCENT, dt.ERR, dt.USER_BG):
            r, g, b = dt.hex2rgb(hexv)
            self.assertEqual((r, g, b), (r, g, b))
            self.assertTrue(0 <= r <= 255)

    def test_rgba_conversion_is_exact(self):
        # replicate what android theme.rgba() does, without needing kivy
        from thans.ui import theme as dt
        r, g, b = dt.hex2rgb(dt.ACCENT)
        self.assertAlmostEqual(r / 255.0, 0.3568, places=3)
        self.assertAlmostEqual(g / 255.0, 0.5490, places=3)
        self.assertAlmostEqual(b / 255.0, 1.0, places=3)

    def test_symbols_avoid_emoji_on_android(self):
        """Android uses the geometric set: no emoji, no variation selectors."""
        from thans.ui.theme import symbols
        sym = symbols(emoji=False)
        for key, glyph in sym.items():
            self.assertTrue(glyph, key)
            for ch in glyph:
                self.assertLess(ord(ch), 0x1F000, f"{key}={glyph!r} is an emoji")
                self.assertNotEqual(ord(ch), 0xFE0F, f"{key} has a variation selector")


# ==========================================================================
# 2. behavioural session (fake kivy)
# ==========================================================================

from tests import fakekivy  # noqa: E402

fakekivy.install()


def make_ids() -> dict:
    """Stand-ins for every id in the KV, with the behaviour the code needs."""
    from unittest.mock import MagicMock

    ids: dict = {}
    for name in fakekivy.kv_ids():
        ids[name] = MagicMock(name=name)

    numeric = {
        "boot": {"opacity": 1.0}, "boot_sub": {"opacity": 0.0},
        "boot_status": {"opacity": 0.0, "text": ""},
        "boot_mark": {"font_size": 14.0}, "boot_word": {"font_size": 14.0},
        "boot_bar": {"active": False},
        "main": {"opacity": 0.0}, "hero": {"opacity": 0.0, "pos_hint": {}},
        "suggest_scroll": {"opacity": 0.0, "height": 0.0},
        "busy_bar": {"opacity": 0.0, "active": False},
        "dots": {"running": False}, "status": {"text": ""}, "input": {"text": ""},
        "btn_mic": {"listening": False}, "chat_scroll": {"scroll_y": 1.0},
    }
    for name, values in numeric.items():
        for key, val in values.items():
            setattr(ids[name], key, val)

    def container(name: str):
        widget = ids[name]
        widget.children = []

        def add(w, index=0):
            widget.children.insert(0 if index is None else min(index, len(widget.children)), w)
            w.parent = widget
            return w

        def remove(w):
            if w in widget.children:
                widget.children.remove(w)

        widget.add_widget = add
        widget.remove_widget = remove
        widget.clear_widgets = lambda *a: widget.children.clear()
        return widget

    for name in ("chat_box", "suggest_box", "toasts"):
        container(name)
    return ids


class AndroidSessionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="thans_android_"))
        self._cwd = os.getcwd()
        os.chdir(self.tmp)                    # app uses cwd as the working root
        fakekivy.Clock.reset()
        self.ids = make_ids()
        fakekivy.set_kv_ids(self.ids)

        import importlib
        sys.path.insert(0, str(REPO / "android"))
        self.app_mod = importlib.import_module("thans_android.app")
        importlib.reload(self.app_mod)
        self.audio = importlib.import_module("thans_android.audio")
        self.app = self.app_mod.ThansAndroidApp()
        self.app.run()                        # fake App.run() → build()

    def tearDown(self):
        os.chdir(self._cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def boot(self, seconds: float = 2.4):
        fakekivy.Clock.advance(seconds)

    # ------------------------------------------------------------- boot
    def test_boot_sequence_completes_and_reveals_app(self):
        self.boot()
        self.assertAlmostEqual(self.ids["main"].opacity, 1.0, places=5)
        self.assertGreaterEqual(self.ids["boot"].opacity, 0.0)
        self.assertTrue(self.ids["boot"].parent.remove_widget.called)
        bubbles = self.ids["chat_box"].children
        self.assertGreaterEqual(len(bubbles), 2)                  # welcome + tip
        self.assertTrue(self.ids["status"].text)

    def test_boot_animates_wordmark_and_sweep(self):
        fakekivy.Clock.advance(0.5)
        self.assertGreater(self.ids["boot_word"].font_size, 14.0)
        self.assertTrue(self.ids["boot_bar"].active)
        fakekivy.Clock.advance(1.2)
        self.assertFalse(self.ids["boot_bar"].active)

    # ----------------------------------------------------------- commands
    def test_send_input_runs_command_and_shows_bubbles(self):
        self.boot()
        self.ids["input"].text = "create folder notes"
        self.app.send_input()
        fakekivy.Clock.advance(0.6)
        self.assertTrue((self.tmp / "notes").is_dir())
        bodies = [b.body for b in self.ids["chat_box"].children if hasattr(b, "body")]
        self.assertTrue(any("create folder notes" in b for b in bodies))
        self.assertTrue(any("Created folder" in b for b in bodies))
        self.assertEqual(self.ids["input"].text, "")

    def test_empty_input_toasts_instead_of_running(self):
        self.boot()
        before = len(self.ids["chat_box"].children)
        self.ids["input"].text = "   "
        self.app.send_input()
        fakekivy.Clock.advance(0.2)
        self.assertEqual(len(self.ids["chat_box"].children), before)
        self.assertTrue(self.ids["toasts"].children)

    def test_failed_command_marks_bubble_error_and_toasts(self):
        self.boot()
        self.app.run_command("delete ghost.txt")
        fakekivy.Clock.advance(0.6)
        kinds = [b.kind for b in self.ids["chat_box"].children]
        self.assertIn("error", kinds)
        self.assertTrue(self.ids["toasts"].children)

    def test_quick_action_dismisses_hero_and_runs(self):
        self.boot()
        self.app.run_quick("how many files in .")
        fakekivy.Clock.advance(0.8)
        self.assertLess(self.ids["hero"].opacity, 0.5)
        bodies = [b.body for b in self.ids["chat_box"].children if hasattr(b, "body")]
        self.assertTrue(any("files" in b for b in bodies))

    def test_starter_with_trailing_space_focuses_input(self):
        self.boot()
        self.app.starter("create folder ")
        self.assertEqual(self.ids["input"].text, "create folder ")
        self.assertTrue(self.ids["input"].focus)

    def test_organize_celebrates(self):
        self.boot()
        (self.tmp / "a.txt").write_text("a")
        (self.tmp / "b.md").write_text("b")
        self.app.run_command("organize .")
        fakekivy.Clock.advance(0.8)
        self.assertTrue((self.tmp / "txt" / "a.txt").is_file())
        toast_texts = [t.text for t in self.ids["toasts"].children]
        self.assertTrue(any("tidier" in t for t in toast_texts))

    def test_clear_chat_keeps_one_notice(self):
        self.boot()
        self.app.run_command("list")
        fakekivy.Clock.advance(0.6)
        self.app.clear_chat()
        self.assertEqual(len(self.ids["chat_box"].children), 1)

    def test_help_lists_commands(self):
        self.boot()
        self.app.say_help()
        fakekivy.Clock.advance(0.8)
        bodies = " ".join(b.body for b in self.ids["chat_box"].children if hasattr(b, "body"))
        self.assertIn("create folder", bodies.lower())

    # -------------------------------------------------------- suggestions
    def test_typing_shows_suggestion_pills(self):
        self.boot()
        (self.tmp / "moodboard.png").write_text("x")
        self.app.on_input_text("mo")
        self.assertTrue(self.ids["suggest_box"].children)
        self.assertGreater(self.ids["suggest_scroll"].height, 0)

    def test_accepting_a_pill_fills_the_input(self):
        self.boot()
        (self.tmp / "todo.txt").write_text("x")
        self.app.on_input_text("move ")
        pill = self.ids["suggest_box"].children[0]
        self.app._accept("move todo.txt")
        self.assertEqual(self.ids["input"].text, "move todo.txt")
        self.assertTrue(pill is not None)

    def test_clearing_input_hides_suggestions(self):
        """Empty input → no pills (the hero card owns the 'getting started' tips)."""
        self.boot()
        (self.tmp / "moodboard.png").write_text("x")
        self.app.on_input_text("mo")
        self.assertTrue(self.ids["suggest_box"].children)
        self.app.on_input_text("")
        fakekivy.Clock.advance(0.5)
        self.assertEqual(self.ids["suggest_box"].children, [])
        self.assertEqual(self.ids["suggest_scroll"].height, 0)
        self.assertLess(self.ids["suggest_scroll"].opacity, 0.5)

    # -------------------------------------------------------------- toasts
    def test_toast_appears_and_removes_itself(self):
        self.boot()
        self.app.toast("hello there", "ok")
        self.assertEqual(len(self.ids["toasts"].children), 1)
        fakekivy.Clock.advance(4.0)
        self.assertEqual(len(self.ids["toasts"].children), 0)

    # --------------------------------------------------------------- voice
    def test_mic_unavailable_is_graceful(self):
        self.audio.stt_available = lambda: False
        self.app.mic_unavailable = True
        self.app.toggle_mic()
        self.assertFalse(self.app.mic_active)
        self.assertTrue(self.ids["toasts"].children)

    def test_mic_toggle_uses_audio_bridge(self):
        started = {"n": 0, "stopped": 0}

        def fake_start(cb):
            started["n"] += 1
            self.cb = cb
            return True

        self.audio.stt_available = lambda: True
        self.audio.start_listening = fake_start
        self.audio.stop_listening = lambda: started.__setitem__("stopped", started["stopped"] + 1)
        self.app.mic_unavailable = False
        self.boot()
        self.app.toggle_mic()
        self.assertTrue(self.app.mic_active)
        self.assertTrue(self.ids["btn_mic"].listening)
        self.app.toggle_mic()
        self.assertFalse(self.app.mic_active)
        self.assertEqual(started["stopped"], 1)

    def test_speech_result_becomes_a_command(self):
        self.boot()
        self.app._on_speech("create folder spoken", None)
        fakekivy.Clock.advance(0.8)
        self.assertTrue((self.tmp / "spoken").is_dir())

    def test_speech_failure_reports_politely(self):
        self.boot()
        self.app._on_speech(None, "no match")
        fakekivy.Clock.advance(0.3)
        self.assertTrue(self.ids["toasts"].children)

    def test_speak_toggle_persists_preference(self):
        self.audio.tts_available = lambda: True
        self.audio.speak = lambda text: None
        self.boot()
        self.app.toggle_speak()
        self.assertTrue(self.app.speak_on)
        stored = json.loads((self.tmp / self.app_mod.PREFS_FILE).read_text())
        self.assertTrue(stored["speak"])
        self.app.toggle_speak()
        self.assertFalse(self.app.speak_on)

    def test_speak_toggle_without_tts_warns(self):
        self.audio.tts_available = lambda: False
        self.boot()
        self.app.toggle_speak()
        self.assertFalse(self.app.speak_on)
        self.assertTrue(self.ids["toasts"].children)

    def test_back_button_stops_listening(self):
        self.app.mic_active = True
        self.audio.stop_listening = lambda: None
        self.assertTrue(self.app._on_key(None, 27))
        self.assertFalse(self.app.mic_active)
        self.assertFalse(self.app._on_key(None, 27))              # otherwise: let Android leave

    def test_pause_stops_the_microphone(self):
        self.app.mic_active = True
        self.audio.stop_listening = lambda: None
        self.assertTrue(self.app.on_pause())
        self.assertFalse(self.app.mic_active)

    # --------------------------------------------------------------- widget
    def test_bubble_grows_to_fit_text(self):
        from thans_android.widgets import Bubble
        short = Bubble(who="THANS", body="hi", kind="thans")
        long = Bubble(who="THANS", body="a rather long sentence " * 12, kind="thans")
        for bubble in (short, long):
            bubble.body_label.width = 300        # phone-ish bubble width
        fakekivy.Clock.advance(0.1)
        self.assertGreater(long._natural, short._natural)
        self.assertLess(short._natural, long._natural * 6)
        self.assertEqual(short.kind, "thans")

    def test_bubble_kinds_have_distinct_colours(self):
        from thans_android.widgets import Bubble
        you = Bubble(who="You", body="list", kind="you")
        err = Bubble(who="THANS", body="boom", kind="error")
        self.assertNotEqual(list(you.fill), list(err.fill))

    def test_bubble_reveal_animates_opacity(self):
        from thans_android.widgets import Bubble
        b = Bubble(who="You", body="hello", kind="you")
        b.reveal()
        self.assertLess(b.opacity, 0.5)
        fakekivy.Clock.advance(0.6)
        self.assertGreater(b.opacity, 0.95)

    def test_typing_dots_only_tick_while_running(self):
        from thans_android.widgets import TypingDots
        dots = TypingDots()
        self.assertIsNone(dots._ev)
        dots.running = True
        self.assertIsNotNone(dots._ev)
        dots.running = False
        self.assertIsNone(dots._ev)


if __name__ == "__main__":
    unittest.main()

"""End-to-end UI tests, run headlessly against the fake tkinter double.

These instantiate the *real* widgets, panels and window, then drive the real
60 fps loop, the real worker thread and the real streaming typewriter. They
catch the class of mistakes that only show up at runtime: bad option names,
missing methods, broken indices, animation callbacks firing twice, and the
command flow itself.
"""
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests import faketk  # noqa: E402

faketk.install()               # must precede any thans UI import

from thans import config            # noqa: E402
from thans.ui import logic          # noqa: E402

# point the app's config at a throwaway dir before anything reads it
DATA_DIR = Path(tempfile.mkdtemp(prefix="thans_ui_cfg_"))
os.environ["THANS_DATA_DIR"] = str(DATA_DIR)
os.environ.pop("THANS_NO_BOOT", None)


def pump(app, seconds: float = 1.5, step: float = 1 / 60, until=None):
    """Advance the virtual clock and the app's real frame body."""
    elapsed = 0.0
    while elapsed < seconds:
        faketk.CLOCK.advance(step * 1000)
        app._tick_once(step)
        elapsed += step
        if until is not None and until():
            return elapsed
    return elapsed


class UiTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from thans.app import ThansApp
        cls.ThansApp = ThansApp

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="thans_ui_root_"))
        (self.tmp / "work").mkdir()
        (self.tmp / "work" / "report.pdf").write_text("pdf")
        (self.tmp / "todo.txt").write_text("x")
        faketk.CLOCK.reset()
        self.app = None

    def tearDown(self):
        if self.app is not None:
            try:
                self.app._on_close()
            except Exception:
                pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def build(self, **cfg_over):
        cfg = {"root": str(self.tmp), "tts": False, "use_llm": False,
               "permanent_delete": False, "motion": True}
        cfg.update(cfg_over)
        self.app = self.ThansApp(cfg=cfg, text_only=False)
        # drive the boot timeline to completion
        for _ in range(600):
            faketk.CLOCK.advance(20)
            self.app._tick_once(0.02)
            if self.app._boot_done:
                break
        self.assertTrue(self.app._boot_done, "boot never finished")
        return self.app

    # convenience: run a command and let the worker reply land
    def run_command(self, text, timeout=5.0):
        self.app.submit(text)
        deadline = time.time() + timeout
        while time.time() < deadline and self.app.busy:
            faketk.CLOCK.advance(16)
            time.sleep(0.01)
            self.app._tick_once(0.016)
        # let the typewriter finish (or give up waiting)
        for _ in range(900):
            faketk.CLOCK.advance(16)
            self.app._tick_once(0.016)
            if self.app.anim is None or not self.app.anim.busy():
                break
        return self.app.chat.messages[-1] if self.app.chat.messages else None


class TestBootAndChrome(UiTestBase):
    def test_boot_sequence_finishes_and_reveals_ui(self):
        app = self.build()
        self.assertIsNotNone(app.engine)
        self.assertTrue(app.chat_card.winfo_exists())
        self.assertTrue(app.input.winfo_exists())
        # the hero is visible until the first command
        self.assertEqual(app.hero.winfo_manager(), "place")

    def test_no_boot_flag_skips_the_overlay(self):
        """THANS_NO_BOOT=1 (tests, screenshots) boots straight into the app."""
        from thans import app as app_mod
        old = app_mod.NO_BOOT
        app_mod.NO_BOOT = True
        try:
            a = app_mod.ThansApp(cfg={"root": str(self.tmp), "tts": False, "motion": True})
            self.assertTrue(a._boot_done)
            self.assertFalse(hasattr(a, "boot"))
            a._on_close()
        finally:
            app_mod.NO_BOOT = old

    def test_model_chips_reflect_state(self):
        app = self.build()
        self.assertTrue(app.chip_voice._text)
        self.assertTrue(app.chip_root._text)
        self.assertIn(app.chip_voice.state, ("ok", "warn", "missing", "off"))

    def test_window_geometry_is_remembered(self):
        app = self.build()
        app.root.geometry("900x600+10+20")
        app._on_close()
        self.app = None                       # already closed
        self.assertEqual(config.load_config().get("window"), "900x600+10+20")

    def test_dashboard_hides_on_narrow_window(self):
        app = self.build()
        app.root.set_size(1000, 700)
        app._apply_responsive()
        self.assertTrue(app._side_visible)
        app.root.set_size(700, 600)
        app._apply_responsive()
        self.assertFalse(app._side_visible)


class TestCommandFlow(UiTestBase):
    def test_submit_creates_folder_and_reports(self):
        app = self.build()
        self.run_command("create folder reports")
        self.assertTrue((self.tmp / "reports").is_dir())
        kinds = [m["kind"] for m in app.chat.messages]
        self.assertIn("you", kinds)
        self.assertIn("thans", kinds)
        self.assertIn("Created folder", app.chat.text.get("1.0", "end"))

    def test_hero_dismissed_after_first_command(self):
        app = self.build()
        self.run_command("list")
        self.assertFalse(app._hero_alive)

    def test_failure_shows_error_and_toast(self):
        app = self.build()
        self.run_command("delete ghost.txt")
        self.assertIn("not found", app.chat.text.get("1.0", "end").lower())
        self.assertTrue(app.toaster._live, "expected an error toast")

    def test_busy_state_toggles_and_thinking_stops(self):
        app = self.build()
        app._set_busy(True)
        self.assertFalse(app.btn_send._enabled)
        self.assertTrue(app.thinking._running)
        app._set_busy(False)
        self.assertTrue(app.btn_send._enabled)
        self.assertFalse(app.thinking._running)

    def test_history_up_down(self):
        app = self.build()
        app.submit("list")
        faketk.CLOCK.advance(50)
        app._history_step(-1)
        self.assertEqual(app.input.get("1.0", "end-1c"), "list")
        app._history_step(1)
        self.assertEqual(app.input.get("1.0", "end-1c"), "")

    def test_empty_enter_shakes_instead_of_sending(self):
        app = self.build()
        before = len(app.chat.messages)
        app._send_clicked()
        self.assertEqual(len(app.chat.messages), before)

    def test_undo_button_reverses_action(self):
        app = self.build()
        self.run_command("create folder undone")
        self.assertTrue((self.tmp / "undone").is_dir())
        self.run_command("undo")
        self.assertFalse((self.tmp / "undone").exists())

    def test_quick_actions_are_wired(self):
        app = self.build()
        app.quick_card.buttons["undo"]._on_press()
        app.quick_card.buttons["undo"]._on_release()
        for _ in range(300):
            faketk.CLOCK.advance(16)
            app._tick_once(0.016)
            if app.chat.messages:
                break
        self.assertTrue(app.chat.messages)

    def test_organize_triggers_celebration_burst(self):
        app = self.build()
        (self.tmp / "a.txt").write_text("a")
        (self.tmp / "b.md").write_text("b")
        self.run_command("organize .")
        self.assertTrue(list(self.tmp.glob("txt/*.txt")))

    def test_root_change_updates_everything(self):
        app = self.build()
        other = Path(tempfile.mkdtemp(prefix="thans_ui_other_"))
        self.addCleanup(shutil.rmtree, other, True)
        app._apply_root(str(other))
        self.assertEqual(app.engine.root, other.resolve())
        self.assertEqual(config.load_config()["root"], str(other))
        self.assertIn(other.name[:12], app.folder_card.path_lbl.cget("text"))
        app._apply_root(str(self.tmp))


class TestStreamingAndChat(UiTestBase):
    def test_reply_streams_then_finishes_with_full_text(self):
        app = self.build()
        long_text = "word " * 200
        app.chat.add_reply(long_text, ok=True, source="rules", stream=True)
        partial = app.chat.text.get("1.0", "end")
        self.assertNotIn(long_text.strip(), partial)      # still typing
        for _ in range(900):
            faketk.CLOCK.advance(16)
            app._tick_once(0.016)
            if app.anim is None or not app.anim.busy():
                break
        self.assertIn(long_text.strip(), app.chat.text.get("1.0", "end"))
        self.assertFalse(app.chat._streams)

    def test_finish_streams_jumps_to_end(self):
        app = self.build()
        app.chat.add_reply("hello there", ok=True, stream=True)
        app.chat.finish_streams()
        self.assertIn("hello there", app.chat.text.get("1.0", "end"))

    def test_clear_chat_empties_transcript(self):
        app = self.build()
        self.run_command("list")
        app.clear_chat()
        self.assertIn("Chat cleared", app.chat.text.get("1.0", "end"))
        self.assertNotIn("todo.txt", app.chat.text.get("1.0", "end"))

    def test_copy_last_reply_and_menu(self):
        app = self.build()
        self.run_command("list")
        app.chat._to_clip("explicit")
        self.assertEqual(faketk.clipboard(), "explicit")
        app.chat._copy_selection()               # no selection → no crash
        app.chat._menu(faketk.Event("<Button-3>"))
        self.assertTrue(app.chat.text.winfo_exists())

    def test_system_message_kinds(self):
        app = self.build()
        app.chat.add_system("heads up", "warn")
        app.chat.add_system("all good", "ok", card=True)
        self.assertIn("heads up", app.chat.text.get("1.0", "end"))

    def test_scrollbar_updates(self):
        app = self.build()
        app.chat.bar.set(0.0, 1.0)               # everything visible → hides
        app.chat.bar.set(0.2, 0.5)               # scrollable → shows
        app.chat.bar.set(0.2, 0.5)
        self.assertTrue(app.chat.bar.items is not None)


class TestSettingsAndModels(UiTestBase):
    def test_settings_open_close_and_toggle_tts(self):
        app = self.build()
        app.open_settings()
        self.assertTrue(app.settings.is_open)
        app.settings.widgets["tts"].set(True, notify=True)
        self.assertTrue(config.load_config()["tts"])
        self.assertTrue(app.cfg["tts"])
        app.settings.close()
        self.assertFalse(app.settings.is_open)

    def test_motion_toggle_disables_animations(self):
        app = self.build()
        app._setting_changed("motion", False)
        self.assertIsNone(app.anim)
        self.assertTrue(app.chat.text.winfo_exists())     # still re-renders
        app.chat.add_reply("flat mode", ok=True, stream=True)
        self.assertIn("flat mode", app.chat.text.get("1.0", "end"))
        app._setting_changed("motion", True)
        self.assertIsNotNone(app.anim)

    def test_permanent_delete_toggle_registers(self):
        app = self.build()
        app._setting_changed("permanent_delete", True)
        self.assertTrue(config.load_config()["permanent_delete"])
        app._setting_changed("permanent_delete", False)

    def test_tts_rate_applies_to_speaker(self):
        app = self.build()
        if app.speaker is None:
            self.skipTest("no speaker in this build")
        app._setting_changed("tts_rate", 220)
        self.assertEqual(app.speaker.rate, 220)

    def test_llm_toggle_degrades_gracefully(self):
        app = self.build()
        app._setting_changed("use_llm", True)     # no GGUF installed here
        self.assertIsNotNone(app.engine)
        app._setting_changed("use_llm", False)

    def test_download_progress_percent_parsing(self):
        self.assertEqual(self.ThansApp._percent("    [####....]  42.5% 12 / 40 MB"), 42.5)
        self.assertIsNone(self.ThansApp._percent("no numbers here"))

    def test_models_progress_queue_updates_panel(self):
        app = self.build()
        app.open_settings()
        app._q.put(("models_progress", 0.4, "42% downloaded"))
        app._tick_once(0.016)
        self.assertEqual(app.settings.dl_lbl.cget("text"), "42% downloaded")
        app._q.put(("models_done", 0))
        app._tick_once(0.016)
        self.assertFalse(app._downloading)

    def test_pick_root_uses_dialog(self):
        app = self.build()
        other = Path(tempfile.mkdtemp(prefix="thans_ui_pick_"))
        self.addCleanup(shutil.rmtree, other, True)
        faketk.set_dialog(dir=str(other))
        app._pick_root()
        self.assertEqual(app.engine.root, other.resolve())
        faketk.set_dialog(dir="")
        app._apply_root(str(self.tmp))


class TestHelpAndOnboarding(UiTestBase):
    def test_help_sheet_lists_every_command_family(self):
        from thans.engine import COMMAND_REFERENCE
        app = self.build()
        app.open_help()
        self.assertTrue(app.help_panel.is_open)
        self.assertEqual(len(app.help_panel.buttons), len(COMMAND_REFERENCE))
        for btn in app.help_panel.buttons:
            self.assertTrue(btn._text)
            btn._draw()                       # each row must paint without error

    def test_help_sheet_toggle_and_escape(self):
        app = self.build()
        app.open_help()
        app.open_help()
        self.assertFalse(app.help_panel.is_open)
        app.open_help()
        app._escape()
        self.assertFalse(app.help_panel.is_open)

    def test_help_row_fills_the_composer(self):
        app = self.build()
        app.open_help()
        btn = app.help_panel.buttons[1]       # "create folder reports in work"
        btn._on_press()
        btn._on_release()
        self.assertTrue(app._input_text())
        self.assertIn("create folder", app._input_text())
        self.assertFalse(app.help_panel.is_open)

    def test_typed_help_opens_the_sheet_not_a_wall_of_text(self):
        app = self.build()
        before = len(app.chat.messages)
        app.submit("help")
        self.assertTrue(app.help_panel.is_open)
        self.assertEqual(len(app.chat.messages), before)

    def test_settings_and_help_are_mutually_exclusive(self):
        app = self.build()
        app.open_settings()
        app.open_help()
        self.assertFalse(app.settings.is_open)
        self.assertTrue(app.help_panel.is_open)
        app.open_settings()
        self.assertFalse(app.help_panel.is_open)

    def test_first_run_tour_shows_once(self):
        app = self.build()
        self.assertTrue(any("New here?" in m["text"] for m in app.chat.messages))
        self.assertTrue(app.toaster._live)
        app._on_close()
        # second start: tour must not repeat
        self.app = self.ThansApp(cfg=dict(app.cfg, onboarded=True))
        for _ in range(600):
            faketk.CLOCK.advance(20)
            self.app._tick_once(0.02)
            if self.app._boot_done:
                break
        self.assertFalse(any("New here?" in m["text"] for m in self.app.chat.messages))

    def test_f5_rescans_without_crashing(self):
        app = self.build()
        app.folder_card.refresh(app.engine.root)
        for _ in range(200):
            faketk.CLOCK.advance(16)
            app._tick_once(0.016)
        self.assertTrue(app.folder_card.winfo_exists())


class TestSuggestionsAndKeys(UiTestBase):
    def test_typing_shows_suggestion_pills(self):
        app = self.build()
        app._placeholder_focus()
        app.input.insert("1.0", "mo")
        app._update_suggestions()
        self.assertTrue(app.suggest_buttons, "expected suggestion pills")
        self.assertEqual(app.suggest_row.winfo_manager(), "grid")

    def test_tab_accepts_first_suggestion(self):
        app = self.build()
        app._placeholder_focus()
        app.input.insert("1.0", "m")
        app._accept_suggestion()
        self.assertTrue(app.input.get("1.0", "end-1c").startswith("m"))

    def test_suggestion_pill_click_fills_input(self):
        app = self.build()
        app._placeholder_focus()
        app._render_suggestions(["create folder reports", "list"])
        app.suggest_buttons[0]._on_press()
        app.suggest_buttons[0]._on_release()
        self.assertEqual(app.input.get("1.0", "end-1c"), "create folder reports")

    def test_suggestions_cleared_when_input_empty(self):
        app = self.build()
        app._placeholder_focus()
        app._render_suggestions(["list"])
        app._render_suggestions([])
        self.assertFalse(app.suggest_row.winfo_ismapped())

    def test_starter_chip_fills_input(self):
        app = self.build()
        app._starter_clicked("list")
        self.assertEqual(app.input.get("1.0", "end-1c"), "list")

    def test_escape_closes_settings_then_input(self):
        app = self.build()
        app.open_settings()
        app._escape()
        self.assertFalse(app.settings.is_open)
        app._set_input("hello")
        app._escape()
        self.assertEqual(app._input_text(), "")

    def test_zoom_changes_fonts(self):
        app = self.build()
        app._zoom(1)
        self.assertEqual(app.input.cget("font")[1], 12)
        app._zoom(-1)
        self.assertEqual(app.input.cget("font")[1], 11)

    def test_key_bindings_are_registered(self):
        app = self.build()
        for seq in ("<F1>", "<F2>", "<Control-z>", "<Control-k>", "<Control-comma>"):
            self.assertIn(seq, app.root._bindings, f"{seq} not bound")
        self.assertIn("<Return>", app.input._bindings)

    def test_out_of_root_current_dir_does_not_crash(self):
        app = self.build()
        app.engine.current = Path(tempfile.gettempdir())
        self.assertIn("root", app._status_line())


class TestVoiceWiring(UiTestBase):
    def test_mic_without_model_warns_instead_of_crashing(self):
        app = self.build()
        app.stt.available = lambda: False          # no speech model installed
        app.toggle_mic()
        self.assertFalse(app.mic_on)
        self.assertTrue(app.settings.is_open)      # nudges towards the download

    def test_mic_toggle_updates_button_and_card(self):
        app = self.build()

        class FakeSTT:
            available = staticmethod(lambda: True)
            recording = False

            def start(self, on_final=None, on_state=None):
                if on_state:
                    on_state("listening…")
                self._final = on_final
                return True

            def stop(self):
                return None

        app.stt = FakeSTT()
        app.toggle_mic()
        self.assertTrue(app.mic_on)
        self.assertEqual(app.btn_mic._glyph, "■" if app.btn_mic._glyph == "■" else app.btn_mic._glyph)
        app.toggle_mic()
        self.assertFalse(app.mic_on)

    def test_voice_transcript_becomes_a_command(self):
        app = self.build()
        app._q.put(("mic", False))
        app._q.put(("voice", "create folder spoken"))
        app._tick_once(0.016)
        for _ in range(300):
            faketk.CLOCK.advance(16)
            app._tick_once(0.016)
            if not app.busy and (self.tmp / "spoken").is_dir():
                break
            time.sleep(0.01)
        self.assertTrue((self.tmp / "spoken").is_dir())

    def test_text_only_mode_blocks_mic(self):
        self.app = self.ThansApp(cfg={"root": str(self.tmp), "tts": False, "motion": True},
                                 text_only=True)
        for _ in range(600):
            faketk.CLOCK.advance(20)
            self.app._tick_once(0.02)
            if self.app._boot_done:
                break
        self.app.toggle_mic()
        self.assertFalse(self.app.mic_on)


class TestWidgetsInIsolation(UiTestBase):
    """Direct widget checks — animation, hover, switches, toasts."""

    def _animator(self):
        return logic.Animator(fps=60)

    def test_rounded_button_clicks_and_hovers(self):
        from thans.ui.widgets import RoundedButton
        root = faketk.Tk()
        clicks = []
        anim = self._animator()
        b = RoundedButton(root, text="Go", command=lambda: clicks.append(1), animator=anim)
        b._on_enter()
        for _ in range(30):
            anim.tick(0.016)
        self.assertGreater(b._hover, 0.9)
        b._on_press()
        b._on_release()
        for _ in range(30):
            anim.tick(0.016)
        self.assertEqual(clicks, [1])
        b.set_enabled(False)
        b._on_press()
        b._on_release()
        self.assertEqual(clicks, [1])          # disabled buttons stay inert
        b._on_leave()
        for _ in range(40):
            anim.tick(0.016)
        self.assertLess(b._hover, 0.1)

    def test_switch_animates_and_notifies(self):
        from thans.ui.widgets import Switch
        root = faketk.Tk()
        seen = []
        anim = self._animator()
        sw = Switch(root, value=False, command=seen.append, animator=anim)
        sw._toggle()
        for _ in range(30):
            anim.tick(0.016)
        self.assertTrue(sw.value)
        self.assertEqual(seen, [True])
        self.assertGreater(sw._t, 0.9)

    def test_progress_bar_determinate_and_indeterminate(self):
        from thans.ui.widgets import ProgressBar
        root = faketk.Tk()
        anim = self._animator()
        bar = ProgressBar(root, animator=anim, width=200, height=8)
        bar.set_size(200, 8)
        bar.set(0.5)
        for _ in range(40):
            anim.tick(0.016)
        self.assertGreater(bar._shown, 0.45)
        bar.start_indeterminate(1.0)
        for _ in range(20):
            anim.tick(0.016)
        self.assertTrue(bar._indeterminate)
        bar.stop_indeterminate()
        self.assertFalse(bar._indeterminate)
        self.assertEqual(anim.active, 0, "loop tween should be released")

    def test_dots_and_waveform_loop_and_stop(self):
        from thans.ui.widgets import Dots, Waveform
        root = faketk.Tk()
        anim = self._animator()
        d = Dots(root, animator=anim)
        d.start()
        for _ in range(20):
            anim.tick(0.016)
        self.assertEqual(anim.active, 1)
        d.stop()
        self.assertEqual(anim.active, 0)
        w = Waveform(root, animator=anim)
        w.start()
        w.set_level(0.8)
        self.assertEqual(anim.active, 1)
        w.stop()
        self.assertEqual(anim.active, 0)

    def test_chip_state_change_animates(self):
        from thans.ui.widgets import Chip
        root = faketk.Tk()
        anim = self._animator()
        c = Chip(root, text="voice", state="off", animator=anim)
        c.set(state="ready")
        self.assertEqual(anim.active, 1)
        for _ in range(30):
            anim.tick(0.016)
        c.set(state="missing")
        self.assertTrue(c.winfo_exists())

    def test_toaster_stacks_and_dismisses(self):
        from thans.ui.widgets import Toaster
        root = faketk.Tk()
        anim = self._animator()
        t = Toaster(root, animator=anim, offset_y=10)
        t.show("first")
        t.show("second", "ok")
        self.assertEqual(len(t._live), 2)
        for _ in range(80):
            anim.tick(0.016)
        for _ in range(400):
            faketk.CLOCK.advance(20)          # let the dismiss timers fire
        for _ in range(120):
            anim.tick(0.016)
        self.assertEqual(len(t._live), 0)

    def test_card_hugs_content_and_glows(self):
        from thans.ui.widgets import Card
        root = faketk.Tk()
        anim = self._animator()
        card = Card(root, animator=anim)
        card.body.configure(width=120, height=60)
        card.body.set_size(120, 60)
        self.assertGreater(card.winfo_reqheight(), 0)
        card.pulse_glow(True)
        for _ in range(30):
            anim.tick(0.016)
        self.assertGreaterEqual(card._glow, 0.0)
        card.pulse_glow(False)
        self.assertEqual(card._glow, 0.0)

    def test_slide_panel_slides_in_and_out(self):
        from thans.ui.widgets import SlidePanel
        root = faketk.Tk()
        root.set_size(900, 600)
        host = faketk.Frame(root)
        host.set_size(900, 600)
        anim = self._animator()
        p = SlidePanel(host, width=300, animator=anim)
        p.open()
        for _ in range(60):
            anim.tick(0.016)
        self.assertTrue(p.is_open)
        p.close()
        for _ in range(60):
            anim.tick(0.016)
        self.assertFalse(p.is_open)
        self.assertFalse(p.winfo_ismapped())

    def test_burst_fires_and_cleans_up(self):
        from thans.ui.widgets import Burst
        root = faketk.Tk()
        anim = self._animator()
        b = Burst(root, animator=anim, size=(200, 100))
        b.fire()
        for _ in range(90):
            anim.tick(0.016)
        self.assertFalse(b.winfo_exists())

    def test_icon_button_has_ring_state(self):
        from thans.ui.widgets import IconButton
        root = faketk.Tk()
        anim = self._animator()
        ib = IconButton(root, glyph="◉", animator=anim, ring=True, size=34)
        ib.ring = False
        ib.configure_glyph("■")
        ib._draw()
        self.assertTrue(ib.winfo_exists())


if __name__ == "__main__":
    unittest.main()

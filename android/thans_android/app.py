"""THANS Android — Kivy front-end around the shared offline ``thans`` engine.

Same command set, same design tokens and same motion language as the desktop
build (see ``theme.py`` — it *derives* from the desktop palette, so the two
apps cannot drift apart). Voice in/out is best-effort through Android's own
speech services; text commands always work, fully offline.

Layout lives in ``thans.kv``; this module owns state, animation and the engine.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# make the staged core package importable
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from kivy.animation import Animation                                  # noqa: E402
from kivy.app import App                                              # noqa: E402
from kivy.clock import Clock                                          # noqa: E402
from kivy.core.window import Window                                   # noqa: E402
from kivy.lang import Builder                                         # noqa: E402
from kivy.metrics import dp, sp                                       # noqa: E402
from kivy.properties import BooleanProperty, DictProperty, ListProperty, StringProperty  # noqa: E402
from kivy.uix.floatlayout import FloatLayout                          # noqa: E402

from thans.engine import Engine                                       # noqa: E402
from thans.ui import logic                                            # noqa: E402

from . import audio                                                   # noqa: E402
from . import theme as T                                              # noqa: E402
from .widgets import Bubble, RoundedButton, Toast                     # noqa: E402

KV_FILE = "thans.kv"
PREFS_FILE = "thans_prefs.json"


class ThansRoot(FloatLayout):
    """Root widget defined by ``thans.kv`` (holds every id the app talks to)."""


class ThansAndroidApp(App):
    # ---- properties the KV file binds to
    tok = DictProperty({})
    sym = DictProperty({})
    working_root = StringProperty("")
    mic_unavailable = BooleanProperty(False)
    rail_color = ListProperty(list(T.ACCENT_HI))

    # ------------------------------------------------------------------ setup
    def build(self):
        self.tok = {
            "BG": list(T.BG), "BG_RAISED": list(T.BG_RAISED), "SURFACE": list(T.SURFACE),
            "SURFACE_HI": list(T.SURFACE_HI), "BORDER": list(T.BORDER),
            "FG": list(T.FG), "FG_DIM": list(T.FG_DIM), "FG_FAINT": list(T.FG_FAINT),
            "ACCENT": list(T.ACCENT), "ACCENT_HI": list(T.ACCENT_HI),
            "ACCENT2": list(T.ACCENT2), "OK": list(T.OK), "WARN": list(T.WARN),
            "ERR": list(T.ERR), "USER_BG": list(T.USER_BG), "SYS_BG": list(T.SYS_BG),
        }
        self.sym = dict(T.SYM)

        kv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", KV_FILE)
        self._root = Builder.load_file(kv_path)

        # python-for-android starts the app with cwd = its private files dir —
        # the only storage it may manage without extra permissions.
        workdir = os.getcwd()
        self.working_root = workdir
        self.engine = Engine(workdir, {"root": workdir, "tts": False,
                                       "use_llm": False, "permanent_delete": False})
        self.prefs = self._load_prefs()
        self.speak_on = bool(self.prefs.get("speak", False)) and audio.tts_available()
        self.mic_active = False
        self.busy = False
        self._suggest_pills: list[RoundedButton] = []
        self._last_user = ""

        self.mic_unavailable = not audio.stt_available()
        if not self.mic_unavailable:
            Window.bind(on_keyboard=self._on_key)
        self._boot()
        return self._root

    # ------------------------------------------------------------------- boot
    def _boot(self) -> None:
        """Splash: mark + wordmark grow in, sweep runs, then the app fades in."""
        ids = self._ids()
        ids.boot_mark.font_size = sp(14)
        ids.boot_word.font_size = sp(14)
        Animation(font_size=sp(30), duration=T.D_SLOW, t="out_back").start(ids.boot_mark)
        Animation(font_size=sp(34), duration=T.D_SLOW, t="out_back").start(ids.boot_word)
        Clock.schedule_once(lambda _dt: self._fade(ids.boot_sub, 1.0, T.D_BASE), 0.20)
        ids.boot_bar.active = True
        Clock.schedule_once(lambda _dt: self._boot_status("checking offline models"), 0.45)
        Clock.schedule_once(lambda _dt: self._boot_status("ready — everything runs on this device"), 0.80)
        Clock.schedule_once(lambda _dt: self._boot_finish(), 1.25)

    def _boot_status(self, text: str) -> None:
        ids = self._ids()
        ids.boot_status.text = text
        if ids.boot_status.opacity < 1:
            self._fade(ids.boot_status, 1.0, T.D_BASE)

    def _boot_finish(self) -> None:
        ids = self._ids()
        ids.boot_bar.active = False
        anim = Animation(opacity=0.0, duration=T.D_BASE, t="out_cubic")
        anim.bind(on_complete=lambda *_: self._after_boot())
        anim.start(ids.boot)

    def _after_boot(self) -> None:
        ids = self._ids()
        if ids.boot.parent:
            ids.boot.parent.remove_widget(ids.boot)
        self._fade(ids.main, 1.0, T.D_BASE)
        self._reveal_hero()
        self._welcome()
        self._status(f"ready · {os.path.basename(self.working_root) or self.working_root}")
        if self.speak_on:
            self._refresh_chips()

    # ---------------------------------------------------------------- helpers
    def _ids(self):
        return self._root.ids

    def _fade(self, widget, target: float, duration: float) -> None:
        Animation(opacity=target, duration=duration, t="out_cubic").start(widget)

    def _status(self, text: str) -> None:
        self._ids().status.text = text

    def _refresh_chips(self) -> None:
        ids = self._ids()
        if self.mic_unavailable:
            ids.chip_voice.set_state("voice: text only", T.FG_FAINT)
        elif self.mic_active:
            ids.chip_voice.set_state("listening…", T.ACCENT2)
        else:
            ids.chip_voice.set_state("SPEAK: ON" if self.speak_on else "SPEAK: OFF",
                                     T.OK if self.speak_on else T.FG_DIM)

    def _set_busy(self, busy: bool) -> None:
        ids = self._ids()
        self.busy = busy
        if busy:
            ids.dots.running = True
            ids.busy_bar.active = True
            self._fade(ids.busy_bar, 1.0, T.D_FAST)
            ids.input_card.glow(True)
        else:
            ids.dots.running = False
            ids.busy_bar.active = False
            self._fade(ids.busy_bar, 0.0, T.D_BASE)
            ids.input_card.glow(False)

    # ------------------------------------------------------------------- chat
    def _add_bubble(self, who: str, text: str, kind: str = "thans") -> Bubble:
        bubble = Bubble(who=who, body=text, kind=kind)
        box = self._ids().chat_box
        box.add_widget(bubble, index=0)                     # newest on top
        bubble.reveal()
        Clock.schedule_once(lambda _dt: self._scroll_top(), 0.08)
        return bubble

    def _scroll_top(self) -> None:
        scroll = self._ids().chat_scroll
        scroll.scroll_y = 1.0

    def _welcome(self) -> None:
        root_name = os.path.basename(self.working_root.rstrip("/")) or self.working_root
        self._add_bubble("THANS",
                         f"{logic.greeting()}! This is your private workspace — "
                         f"'{root_name}'. Everything happens on this phone, nothing "
                         f"is uploaded.",
                         "thans")
        if self.mic_unavailable:
            self._add_bubble("THANS",
                             "No speech service on this device, so voice is off — "
                             "typing works exactly the same. Try 'help'.",
                             "system")
        else:
            self._add_bubble("THANS",
                             "Tap the mic and talk, or type. Try 'create folder notes', "
                             "'find pdf', 'organize .'", "system")

    def toast(self, text: str, kind: str = "info") -> None:
        host = self._ids().toasts
        t = Toast(text=text, kind=kind, size_hint=(None, None), height=dp(38),
                  width=min(Window.width - dp(24), max(dp(220), dp(13) * len(text) * 0.55)))
        host.add_widget(t)
        t.opacity = 0.0
        t.show(on_done=lambda: host.remove_widget(t) if t.parent else None)

    # --------------------------------------------------------------- commands
    def send_input(self) -> None:
        inp = self._ids().input
        text = (inp.text or "").strip()
        if not text:
            self.toast("Type a command first — try 'help'", "warn")
            return
        inp.text = ""
        self.run_command(text, who="You")

    def run_quick(self, text: str) -> None:
        """Quick-action buttons and the hero chips both land here."""
        self._dismiss_hero()
        self.run_command(text, who="You")

    def starter(self, text: str) -> None:
        self._dismiss_hero()
        self._ids().input.text = text
        if not text.endswith(" "):
            self.send_input()
        else:
            self._ids().input.focus = True

    def run_command(self, text: str, who: str = "You") -> None:
        self._dismiss_hero()
        self._last_user = text
        self._add_bubble(who, text, "you")
        self._set_busy(True)
        self._status("thinking…")
        self._hide_suggestions()
        Clock.schedule_once(lambda _dt: self._execute(text), T.D_FAST)

    def _execute(self, text: str) -> None:
        try:
            res = self.engine.run(text)
        except Exception as e:                                   # noqa: BLE001
            self._set_busy(False)
            self._add_bubble("THANS", f"Internal error: {e}", "error")
            self.toast("Something went wrong", "error")
            return
        self._set_busy(False)
        kind = "thans" if res.ok else "error"
        title = "THANS" + (f" · {res.source}" if res.source else "")
        self._add_bubble(title, res.message, kind)
        self._status(f"in {self._rel(self.engine.current)}  ·  {self.working_root}")
        if not res.ok:
            self.toast(logic.truncate(res.message, 52), "error")
        elif logic.should_celebrate(res.command, res.ok):
            self.toast("Nice — that's tidier now", "ok")
        if self.speak_on:
            audio.speak(res.message)

    def _rel(self, path) -> str:
        try:
            return Path(path).relative_to(self.engine.root).as_posix() or "."
        except ValueError:
            return str(path)

    def clear_chat(self) -> None:
        box = self._ids().chat_box
        box.clear_widgets()
        self._add_bubble("THANS", "Transcript cleared — still on this device only.", "system")

    def say_help(self) -> None:
        self.run_command("help", who="You")

    def show_capabilities(self) -> None:
        """The 'rule parser' chip explains what runs on the phone."""
        self.toast("Commands are understood on-device by the rule parser", "ok")

    # ------------------------------------------------------------ suggestions
    def on_input_text(self, text: str) -> None:
        if not (text or "").strip():            # idle input: keep the row tidy
            self._hide_suggestions()
            return
        names, dirs = [], []
        try:
            names = [p.name for p in self.engine.current.iterdir()][:80]
            dirs = [p.name for p in self.engine.current.iterdir() if p.is_dir()][:40]
        except OSError:
            pass
        items = logic.suggest(text or "", names, dirs, limit=4)
        box = self._ids().suggest_box
        for pill in self._suggest_pills:
            if pill.parent:
                pill.parent.remove_widget(pill)
        self._suggest_pills.clear()
        if not items:
            self._hide_suggestions()
            return
        for item in items:
            pill = RoundedButton(text=logic.truncate(item, 24), subtle=True,
                                 font_size=sp(11), size_hint=(None, None),
                                 height=dp(28), width=dp(9) * (len(item) + 4))
            pill.bind(on_release=lambda _b, t=item: self._accept(t))
            box.add_widget(pill)
            self._suggest_pills.append(pill)
        scroll = self._ids().suggest_scroll
        scroll.height = dp(32)
        self._fade(scroll, 1.0, T.D_FAST)

    def _accept(self, text: str) -> None:
        self._ids().input.text = text
        self._ids().input.focus = True

    def _hide_suggestions(self) -> None:
        scroll = self._ids().suggest_scroll
        box = self._ids().suggest_box
        if not self._suggest_pills and scroll.height <= 0:
            return

        def collapse(_dt):
            scroll.height = 0
            for pill in list(self._suggest_pills):
                if pill.parent:
                    pill.parent.remove_widget(pill)
            self._suggest_pills.clear()

        self._fade(scroll, 0.0, T.D_FAST)
        Clock.schedule_once(collapse, T.D_FAST)

    # ------------------------------------------------------------------- hero
    def _dismiss_hero(self) -> None:
        hero = self._ids().hero
        if hero.opacity < 0.05 or getattr(self, "_hero_gone", False):
            return
        self._hero_gone = True
        self._fade(hero, 0.0, T.D_BASE)

    def _reveal_hero(self) -> None:
        hero = self._ids().hero
        hero.pos_hint = {"center_x": 0.5, "center_y": 0.52}
        hero.opacity = 0.0
        Animation(opacity=1.0, duration=T.D_SLOW, t="out_cubic").start(hero)
        Clock.schedule_once(lambda _dt: setattr(
            hero, "pos_hint", {"center_x": 0.5, "center_y": 0.56}), T.D_FAST)

    # ------------------------------------------------------------------ voice
    def toggle_speak(self) -> None:
        if not audio.tts_available():
            self.toast("No speech output on this device", "warn")
            return
        self.speak_on = not self.speak_on
        self.prefs["speak"] = self.speak_on
        self._save_prefs()
        self._refresh_chips()
        self.toast("Spoken replies " + ("on" if self.speak_on else "off"),
                   "ok" if self.speak_on else "info")

    def stop_mic(self) -> None:
        """Stop listening (also used by the Android back button / on_pause)."""
        if not self.mic_active:
            return
        audio.stop_listening()
        self.mic_active = False
        self._ids().btn_mic.listening = False
        self._refresh_chips()
        self._status("mic stopped")

    def toggle_mic(self) -> None:
        if self.mic_active:
            self.stop_mic()
            return
        if self.mic_unavailable:
            self.toast("No speech service — typing works the same", "warn")
            return
        if audio.start_listening(self._on_speech):
            self.mic_active = True
            self._ids().btn_mic.listening = True
            self._refresh_chips()
            self._status("listening — speak now")
            self.toast("Listening…", "info")
        else:
            self.mic_unavailable = True
            self.toast("Microphone unavailable — use text", "error")

    def _on_speech(self, text, err) -> None:
        # pyjnius callbacks arrive on the Android thread — hop to Kivy's thread
        Clock.schedule_once(lambda _dt: self._handle_speech(text, err), 0)

    def _handle_speech(self, text, err) -> None:
        self.mic_active = False
        self._ids().btn_mic.listening = False
        self._refresh_chips()
        if text:
            self._add_bubble("You (voice)", text, "you")
            Clock.schedule_once(lambda _dt: self.run_command(text, who="You (voice)"), T.D_FAST)
        else:
            self._status(f"speech: {err or 'no result'}")
            self.toast("Didn't catch that — try again", "warn")

    # ---------------------------------------------------------------- prefs
    def _prefs_path(self) -> Path:
        return Path(self.working_root) / PREFS_FILE

    def _load_prefs(self) -> dict:
        try:
            return json.loads(self._prefs_path().read_text())
        except Exception:
            return {}

    def _save_prefs(self) -> None:
        try:
            self._prefs_path().write_text(json.dumps(self.prefs))
        except OSError:
            pass

    # -------------------------------------------------------------- lifecycle
    def _on_key(self, _window, key, *_a):
        if key == 27 and self.mic_active:   # Android back button / Esc
            self.stop_mic()
            return True
        return False

    def on_pause(self) -> bool:
        self.stop_mic()
        return True

    def on_resume(self):
        self._refresh_chips()

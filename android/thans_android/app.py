"""THANS Android — Kivy front-end around the shared offline thans engine.

Same command set as the desktop app (create/move/copy/rename/delete-to-trash/
search/organize/open/cd/undo/help). Voice input & spoken replies are
best-effort on-device (Android SpeechRecognizer / TextToSpeech via pyjnius);
text commands always work, fully offline.

Note: the LLM parser is desktop-only (no llama.cpp NDK recipe); the rule
parser handles the entire documented command set, so nothing is lost.
"""
from __future__ import annotations

import os
import sys

# make the staged core package importable
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from kivy.app import App  # noqa: E402
try:
    from kivy.builder import Builder  # noqa: E402  (kivy ≤ 2.3.0)
except ImportError:
    from kivy.lang.builder import Builder  # noqa: E402  (kivy ≥ 2.3.1)
from kivy.clock import Clock  # noqa: E402
from kivy.uix.label import Label  # noqa: E402

from thans.engine import Engine  # noqa: E402

from . import audio  # noqa: E402

YOU = (0.48, 0.64, 1.0, 1)
ME = (0.72, 0.76, 1.0, 1)
SYS = (0.55, 0.60, 0.68, 1)


class ThansAndroidApp(App):
    def build(self):
        kv = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "thans.kv")
        Builder.load_file(kv)
        self._root = Builder.get_root()

        # python-for-android starts the app with cwd = its internal files dir,
        # which is the only storage the app can manage without extra permissions.
        workdir = os.getcwd()
        self.engine = Engine(workdir, {
            "root": workdir,
            "tts": False,
            "use_llm": False,
            "permanent_delete": False,
        })
        self.speak_on = False
        self.mic_active = False

        self._add("THANS", f"Welcome! Working folder: {workdir}", SYS)
        self._add("THANS", "Type a command below, press HELP for the list, or try MIC "
                           "(needs a speech service on the device).", SYS)
        self._set_status(f"THANS ready · {workdir}")
        return self._root

    # ------------------------------------------------------------ helpers
    def _ids(self):
        return self._root.ids

    def _set_status(self, text: str) -> None:
        self._ids().status.text = text

    def _add(self, who: str, text: str, color) -> None:
        box = self._ids().chat_box
        lbl = Label(text=f"[b]{who}[/b]  {text}", markup=True, color=color,
                    size_hint_y=None, halign="left", font_size=15)
        box.insert(0, lbl)  # newest on top
        lbl.height = lbl.texture_size[1] + 10
        Clock.schedule_once(lambda dt: self._ids().chat_scroll.set_normalized_y(1), 0.05)

    # ------------------------------------------------------------ commands
    def send_input(self) -> None:
        inp = self._ids().input
        text = inp.text.strip()
        if not text:
            return
        inp.text = ""
        self._add("You", text, YOU)
        Clock.schedule_once(lambda dt: self._run(text), 0.05)

    def _run(self, text: str) -> None:
        try:
            res = self.engine.run(text)
        except Exception as e:  # noqa: BLE001
            self._add("THANS", f"Error: {e}", SYS)
            return
        self._add("THANS", res.message, ME if res.ok else SYS)
        self._set_status(f"working folder: {self.engine.current}")
        if self.speak_on:
            audio.speak(res.message)

    def say_help(self) -> None:
        Clock.schedule_once(lambda dt: self._run("help"), 0.05)

    def clear_chat(self) -> None:
        self._ids().chat_box.clear_widgets()
        self._add("THANS", "Chat cleared.", SYS)

    def toggle_speak(self) -> None:
        self.speak_on = not self.speak_on
        self._ids().btn_speak.text = "SPEAK: ON" if self.speak_on else "SPEAK: OFF"
        if self.speak_on and not audio.tts_available():
            self._set_status("TTS not available on this device")
            self.speak_on = False
            self._ids().btn_speak.text = "SPEAK: OFF"

    # ------------------------------------------------------------------ mic
    def toggle_mic(self) -> None:
        ids = self._ids()
        if self.mic_active:
            audio.stop_listening()
            self.mic_active = False
            ids.btn_mic.text = "MIC"
            self._set_status("mic stopped")
            return
        if audio.start_listening(self._on_speech):
            self.mic_active = True
            ids.btn_mic.text = "STOP"
            self._set_status("listening… speak now")
        else:
            self._set_status("no speech service on device — use text")

    def _on_speech(self, text: str | None, err: str | None) -> None:
        # pyjnius callbacks arrive on the Android thread — hop to Kivy's thread
        Clock.schedule_once(lambda dt: self._handle_speech(text, err), 0.05)

    def _handle_speech(self, text: str | None, err: str | None) -> None:
        self.mic_active = False
        self._ids().btn_mic.text = "MIC"
        if text:
            self._set_status(f"heard: {text}")
            self._add("You (voice)", text, YOU)
            Clock.schedule_once(lambda dt: self._run(text), 0.05)
        else:
            self._set_status(f"speech: {err or 'no result'}")

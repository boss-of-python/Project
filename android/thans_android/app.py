"""THANS Android — Kivy front-end around the shared offline thans engine & UX helpers.

Features:
  • Smooth Kivy animations (message card fade-in, animated acoustic wave header,
    collapsible live file/folder explorer drawer)
  • Real-time intent preview & one-tap autocomplete
  • Touch-first quick-action chip carousel & folder navigation
  • Best-effort on-device voice input & spoken replies via pyjnius
"""
from __future__ import annotations

import os
import sys
import time

# make the staged core package importable (or repo parent in dev/test mode)
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))
sys.path.insert(0, os.path.join(_HERE, "..", ".."))

from kivy.animation import Animation  # noqa: E402
from kivy.app import App  # noqa: E402
try:
    from kivy.builder import Builder  # noqa: E402  (kivy ≤ 2.3.0)
except ImportError:
    from kivy.lang.builder import Builder  # noqa: E402  (kivy ≥ 2.3.1)
from kivy.clock import Clock  # noqa: E402
from kivy.metrics import dp, sp  # noqa: E402
from kivy.uix.button import Button  # noqa: E402
from kivy.uix.label import Label  # noqa: E402

from thans import ux  # noqa: E402
from thans.engine import Engine  # noqa: E402

from . import audio  # noqa: E402

YOU = (0.49, 0.69, 1.0, 1)
ME = (0.84, 0.88, 1.0, 1)
SYS = (0.58, 0.64, 0.74, 1)
CMD_COL = (0.42, 0.50, 0.64, 1)

ACCENT = (0.36, 0.55, 1.0, 1)
OK_COL = (0.24, 0.84, 0.55, 1)
WARN_COL = (0.96, 0.65, 0.14, 1)
ERR_COL = (1.0, 0.36, 0.42, 1)

_WAVE_GLYPHS = "▁▂▃▄▅▆▇█"


class ThansAndroidApp(App):
    def __init__(self, workdir: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self._init_workdir = workdir
        self._root = None
        self.engine: Engine | None = None
        self.speak_on = False
        self.mic_active = False
        self.files_drawer_open = True
        self._phase = 0.0
        self._anim_mode = "idle"
        self._flash_until = 0.0
        self._wave_ev = None

    def build(self):
        kv = os.path.join(_HERE, "..", "thans.kv")
        self._root = Builder.load_file(kv)

        workdir = self._init_workdir or os.getcwd()
        self.engine = Engine(workdir, {
            "root": workdir,
            "tts": False,
            "use_llm": False,
            "permanent_delete": False,
        })

        self._refresh_workspace()
        self._add("THANS", f"Welcome! Working folder: {workdir}", SYS)
        self._add(
            "THANS",
            "Tap any quick action chip below, tap a folder/file in the FILES strip, "
            "type a command, or press 🎙 MIC.",
            SYS,
        )
        self._wave_ev = Clock.schedule_interval(self._tick_wave, 0.08)
        return self._root

    # ------------------------------------------------------------ helpers & animation
    def _ids(self):
        return self._root.ids

    def _set_status(self, text: str) -> None:
        self._ids().status.text = text

    def _tick_wave(self, _dt: float) -> None:
        if self._root is None:
            return
        self._phase += 0.22
        now = time.monotonic()
        if self.mic_active:
            mode = "listening"
        elif now < self._flash_until:
            mode = self._anim_mode
        else:
            mode = "idle"
            self._anim_mode = "idle"

        bars = ux.wave_heights(self._phase, count=7, mode=mode)
        wave_str = "".join(_WAVE_GLYPHS[min(len(_WAVE_GLYPHS) - 1, int(b * len(_WAVE_GLYPHS)))] for b in bars)
        ids = self._ids()
        if mode == "listening":
            ids.pulse_dot.color = ERR_COL
            ids.wave_label.text = f"{wave_str}  listening…"
            ids.wave_label.color = ERR_COL
        elif mode == "success":
            ids.pulse_dot.color = OK_COL
            ids.wave_label.text = f"{wave_str}  done"
            ids.wave_label.color = OK_COL
        elif mode == "error":
            ids.pulse_dot.color = WARN_COL
            ids.wave_label.text = f"{wave_str}  check"
            ids.wave_label.color = WARN_COL
        else:
            ids.pulse_dot.color = ACCENT
            ids.wave_label.text = f"{wave_str}  offline ready"
            ids.wave_label.color = SYS

    def _trigger_flash(self, ok: bool) -> None:
        self._anim_mode = "success" if ok else "error"
        self._flash_until = time.monotonic() + 1.2

    def _add(self, who: str, text: str, color) -> None:
        box = self._ids().chat_box
        lbl = Label(
            text=f"[b]{who}[/b]  {text}",
            markup=True,
            color=color,
            size_hint_y=None,
            halign="left",
            valign="top",
            font_size=sp(14),
            opacity=0.0,
        )

        def _sync_size(instance, _val):
            instance.text_size = ( max(dp(200), instance.width - dp(12)), None )
            instance.texture_update()
            instance.height = max(dp(28), instance.texture_size[1] + dp(12))

        lbl.bind(width=_sync_size)
        # In Kivy BoxLayout, add_widget(..., index=len(box.children)) puts newest at the top
        box.add_widget(lbl, index=len(box.children))
        _sync_size(lbl, lbl.width)
        Animation(opacity=1.0, d=0.20, t="out_cubic").start(lbl)
        Clock.schedule_once(lambda _dt: setattr(self._ids().chat_scroll, "scroll_y", 1.0), 0.04)

    # ------------------------------------------------------------ workspace & quick chips
    def _refresh_workspace(self) -> None:
        if self.engine is None or self._root is None:
            return
        snap = ux.workspace_snapshot(self.engine.root, self.engine.current, self.engine.undo_stack)
        ids = self._ids()

        # Update header & status strip
        total_items = snap["folders"] + snap["files"]
        ids.btn_files.text = f"FILES ({total_items})"
        ids.btn_up.disabled = not snap["can_go_up"]
        ids.btn_up.opacity = 1.0 if snap["can_go_up"] else 0.45
        ids.btn_undo.text = f"↶ UNDO ({snap['undo_count']})" if snap["undo_count"] else "↶ UNDO"
        ids.btn_undo.color = ACCENT if snap["undo_count"] else SYS
        self._set_status(f"📂 {snap['rel_path']}  ·  {snap['folders']} dir, {snap['files']} file")

        # Populate live touch File/Folder Explorer strip
        exp_box = ids.explorer_box
        exp_box.clear_widgets()
        if not snap["items"]:
            empty_lbl = Label(
                text="(folder is empty — tap +Folder or +File below)",
                font_size=sp(11), color=SYS, size_hint_x=None, width=dp(260),
            )
            exp_box.add_widget(empty_lbl)
        else:
            for item in snap["items"]:
                suffix = "/" if item["is_dir"] else ""
                chip_txt = f"{item['icon']} {item['name']}{suffix}"
                btn = Button(
                    text=chip_txt,
                    font_size=sp(11),
                    size_hint_x=None,
                    width=max(dp(84), dp(len(chip_txt) * 7 + 22)),
                    background_normal="",
                    background_color=(0.14, 0.20, 0.32, 1) if item["is_dir"] else (0.12, 0.15, 0.22, 1),
                    color=(0.88, 0.93, 1.0, 1),
                )
                btn.bind(on_release=lambda _b, cmd=item["primary_cmd"]: self._run_command_direct(cmd))
                exp_box.add_widget(btn)

        # Populate touch Quick-Action Carousel
        q_box = ids.quick_box
        q_box.clear_widgets()
        for pill in ux.quick_actions(snap):
            label = pill["label"]
            q_btn = Button(
                text=label,
                font_size=sp(11),
                size_hint_x=None,
                width=max(dp(74), dp(len(label) * 7 + 20)),
                background_normal="",
                background_color=(0.12, 0.16, 0.24, 1),
                color=(0.82, 0.88, 0.98, 1),
            )
            q_btn.bind(on_release=lambda _b, pl=pill: self._on_pill_tap(pl))
            q_box.add_widget(q_btn)

    def toggle_files_drawer(self) -> None:
        drawer = self._ids().explorer_drawer
        self.files_drawer_open = not self.files_drawer_open
        target_h = dp(40) if self.files_drawer_open else dp(0)
        target_op = 1.0 if self.files_drawer_open else 0.0
        Animation(height=target_h, opacity=target_op, d=0.20, t="out_cubic").start(drawer)

    def _on_pill_tap(self, pill: dict[str, str]) -> None:
        inp = self._ids().input
        if pill.get("kind") == "fill":
            inp.text = pill["cmd"]
            inp.focus = True
            self.on_input_change(inp.text)
        else:
            self._run_command_direct(pill["cmd"])

    def _run_command_direct(self, cmd_text: str) -> None:
        self._add("You", cmd_text, YOU)
        Clock.schedule_once(lambda _dt: self._run(cmd_text), 0.02)

    # ------------------------------------------------------------ live intent & autocomplete
    def on_input_change(self, text: str) -> None:
        if self.engine is None or self._root is None:
            return
        info = ux.live_intent_preview(text, self.engine.current)
        ids = self._ids()
        state = info["state"]
        ids.intent_badge.text = info["badge"]
        ids.intent_label.text = info["text"]
        if state == "valid":
            ids.intent_badge.color = OK_COL
            ids.intent_label.color = ME
        elif state == "hint":
            ids.intent_badge.color = WARN_COL
            ids.intent_label.color = SYS
        else:
            ids.intent_badge.color = ACCENT
            ids.intent_label.color = SYS

        comp = info.get("completion") or ""
        if comp:
            ids.btn_complete.opacity = 1.0
            ids.btn_complete.disabled = False
        else:
            ids.btn_complete.opacity = 0.0
            ids.btn_complete.disabled = True

    def apply_autocomplete(self) -> None:
        if self.engine is None:
            return
        inp = self._ids().input
        comp = ux.autocomplete(inp.text, self.engine.current)
        if comp:
            inp.text = comp
            self.on_input_change(comp)

    # ------------------------------------------------------------ commands
    def send_input(self) -> None:
        inp = self._ids().input
        text = inp.text.strip()
        if not text:
            return
        inp.text = ""
        self.on_input_change("")
        self._add("You", text, YOU)
        Clock.schedule_once(lambda _dt: self._run(text), 0.02)

    def _run(self, text: str) -> None:
        if self.engine is None:
            return
        try:
            res = self.engine.run(text)
        except Exception as e:  # noqa: BLE001
            self._add("THANS", f"Error: {e}", SYS)
            self._trigger_flash(False)
            return
        if res.command:
            self._add("→", res.command, CMD_COL)
        self._add("THANS", res.message, ME if res.ok else SYS)
        self._trigger_flash(res.ok)
        self._refresh_workspace()
        if self.speak_on:
            audio.speak(res.message)

    def go_up(self) -> None:
        self._run_command_direct("go back")

    def go_home(self) -> None:
        self._run_command_direct("cd")

    def say_undo(self) -> None:
        self._run_command_direct("undo")

    def say_help(self) -> None:
        self._run_command_direct("help")

    def clear_chat(self) -> None:
        self._ids().chat_box.clear_widgets()
        self._add("THANS", "Conversation cleared.", SYS)

    def toggle_speak(self) -> None:
        ids = self._ids()
        self.speak_on = not self.speak_on
        if self.speak_on and not audio.tts_available():
            self._set_status("TTS not available on this device")
            self.speak_on = False
        ids.btn_speak.text = "SPEAK: ON" if self.speak_on else "SPEAK: OFF"
        ids.btn_speak.background_color = (0.16, 0.36, 0.26, 1) if self.speak_on else (0.12, 0.15, 0.21, 1)
        ids.btn_speak.color = (0.85, 1.0, 0.90, 1) if self.speak_on else (0.65, 0.72, 0.82, 1)

    # ------------------------------------------------------------------ mic
    def toggle_mic(self) -> None:
        ids = self._ids()
        if self.mic_active:
            audio.stop_listening()
            self.mic_active = False
            ids.btn_mic.text = "🎙 MIC"
            ids.btn_mic.background_color = (0.14, 0.18, 0.26, 1)
            self._set_status("mic stopped")
            return
        if audio.start_listening(self._on_speech):
            self.mic_active = True
            ids.btn_mic.text = "⏹ STOP"
            ids.btn_mic.background_color = (0.65, 0.18, 0.24, 1)
            self._set_status("🎙 listening… speak now")
        else:
            self._set_status("no speech service on device — use text or quick chips")

    def _on_speech(self, text: str | None, err: str | None) -> None:
        Clock.schedule_once(lambda _dt: self._handle_speech(text, err), 0.04)

    def _handle_speech(self, text: str | None, err: str | None) -> None:
        self.mic_active = False
        ids = self._ids()
        ids.btn_mic.text = "🎙 MIC"
        ids.btn_mic.background_color = (0.14, 0.18, 0.26, 1)
        if text:
            self._set_status(f"heard: {text}")
            self._add("You (voice)", text, YOU)
            Clock.schedule_once(lambda _dt: self._run(text), 0.04)
        else:
            self._set_status(f"speech: {err or 'no result'}")

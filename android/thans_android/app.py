"""THANS Android — minimalistic, animated Kivy front-end around the shared offline thans engine.

Highlights:
  * Same offline engine & UX intelligence (`thans.engine`, `thans.ui_helpers`, `thans.animations`)
  * Curated Dark & Light themes with reactive Kivy properties
  * Animated Sonic Wave indicator reacting to Idle, Listening (RMS), Thinking, and Success/Error
  * Segmented Dual View: `💬 Chat` (animated message cards) and `📁 Files` (touch file explorer)
  * Live Intent Preview pill as you type + one-tap Quick-Action Chips & `⚡ Complete`
  * Guarded Android SpeechRecognizer (with runtime permissions, partial transcripts, and RMS) + TTS
"""
from __future__ import annotations

import os
import sys
from typing import Optional

# Make the staged core package importable
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from kivy.animation import Animation  # noqa: E402
from kivy.app import App  # noqa: E402
try:
    from kivy.builder import Builder  # noqa: E402  (kivy <= 2.3.0)
except ImportError:
    from kivy.lang.builder import Builder  # noqa: E402  (kivy >= 2.3.1)
from kivy.clock import Clock  # noqa: E402
from kivy.metrics import dp, sp  # noqa: E402
from kivy.properties import ListProperty, StringProperty  # noqa: E402
from kivy.uix.boxlayout import BoxLayout  # noqa: E402
from kivy.uix.button import Button  # noqa: E402
from kivy.uix.label import Label  # noqa: E402

from thans import animations, platforms, ui_helpers  # noqa: E402
from thans.engine import Engine  # noqa: E402

from . import audio  # noqa: E402

SONIC_GLYPHS = ("▁", "▂", "▃", "▄", "▅", "▆", "▇", "█")


class ThansAndroidApp(App):
    # Reactive theme properties referenced by thans.kv
    theme_name = StringProperty("dark")
    active_tab = StringProperty("chat")

    bg_color = ListProperty(list(animations.hex_to_rgba("#0d0f14")))
    panel_color = ListProperty(list(animations.hex_to_rgba("#13161f")))
    panel2_color = ListProperty(list(animations.hex_to_rgba("#1a1e2b")))
    fg_color = ListProperty(list(animations.hex_to_rgba("#eef0f6")))
    dim_color = ListProperty(list(animations.hex_to_rgba("#6e778c")))
    accent_color = ListProperty(list(animations.hex_to_rgba("#5b8af5")))
    ok_color = ListProperty(list(animations.hex_to_rgba("#10b981")))
    warn_color = ListProperty(list(animations.hex_to_rgba("#f59e0b")))
    err_color = ListProperty(list(animations.hex_to_rgba("#f43f5e")))
    sonic_color = ListProperty(list(animations.hex_to_rgba("#5b8af5")))

    def __init__(self, workdir: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self._workdir = workdir
        self._root = None
        self.engine: Optional[Engine] = None
        self.speak_on = False
        self.mic_active = False

        # Sonic animation state
        self.sonic_state = "idle"
        self.sonic_phase = 0.0
        self.sonic_level = 0.0
        self._flash_ticks = 0

        # Chat history & workspace snapshot
        self.chat_records: list[tuple[str, str, str]] = []  # (who, text, kind)
        self.snapshot: Optional[ui_helpers.DirSnapshot] = None

    def build(self):
        kv = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "thans.kv")
        loaded = Builder.load_file(kv)
        # Support both real Kivy (load_file returns root) and any legacy test shim
        if loaded is None and hasattr(Builder, "get_root"):
            loaded = Builder.get_root()
        self._root = loaded

        # Guarantees a writable folder (Android: the app's internal files dir;
        # falls back to home / temp if the CWD is ever read-only).
        workdir = platforms.resolve_workdir(self._workdir)
        self.engine = Engine(
            workdir,
            {
                "root": workdir,
                "tts": False,
                "use_llm": False,
                "permanent_delete": False,
            },
        )

        self._apply_theme("dark")
        self._refresh_workspace()

        self._add("THANS", f"Welcome! Working folder: {workdir}", "sys")
        self._add(
            "THANS",
            "Tap any quick chip below, switch to 📁 Files to browse visually, "
            "or type/speak a command.",
            "sys",
        )
        self._set_status(f"● ready · {self.snapshot.rel_current if self.snapshot else workdir}")
        Clock.schedule_interval(self._animate_tick, 0.05)
        return self._root

    # ------------------------------------------------------------ helpers
    def _ids(self):
        return self._root.ids

    def _set_status(self, text: str) -> None:
        self._ids().status.text = text

    def _apply_theme(self, name: str) -> None:
        self.theme_name = name
        pal = animations.get_theme(name)
        self.bg_color = list(animations.hex_to_rgba(pal["bg"]))
        self.panel_color = list(animations.hex_to_rgba(pal["panel"]))
        self.panel2_color = list(animations.hex_to_rgba(pal["panel2"]))
        self.fg_color = list(animations.hex_to_rgba(pal["fg"]))
        self.dim_color = list(animations.hex_to_rgba(pal["dim"]))
        self.accent_color = list(animations.hex_to_rgba(pal["accent"]))
        self.ok_color = list(animations.hex_to_rgba(pal["ok"]))
        self.warn_color = list(animations.hex_to_rgba(pal["warn"]))
        self.err_color = list(animations.hex_to_rgba(pal["err"]))
        if self._root and "btn_theme" in self._ids():
            self._ids().btn_theme.text = "☀️" if name == "dark" else "🌙"

    def toggle_theme(self) -> None:
        nxt = "light" if self.theme_name == "dark" else "dark"
        self._apply_theme(nxt)
        if self.active_tab == "files":
            self._render_files_view()
        else:
            self._render_chat_view()

    # ------------------------------------------------------------ animations
    def _animate_tick(self, _dt: float) -> None:
        speed = 0.28 if self.sonic_state != "idle" else 0.10
        self.sonic_phase = (self.sonic_phase + speed) % 62.83
        if self._flash_ticks > 0:
            self._flash_ticks -= 1
            if self._flash_ticks == 0 and not self.mic_active:
                self.sonic_state = "idle"

        bars = animations.compute_equalizer_bars(
            7, phase=self.sonic_phase, state=self.sonic_state, level=self.sonic_level
        )
        glyph_str = "".join(
            SONIC_GLYPHS[min(len(SONIC_GLYPHS) - 1, int(b * len(SONIC_GLYPHS)))] for b in bars
        )
        state_hex = animations.STATE_COLORS.get(self.sonic_state, animations.STATE_COLORS["idle"])[0]
        self.sonic_color = list(animations.hex_to_rgba(state_hex))
        if self._root and "sonic_indicator" in self._ids():
            self._ids().sonic_indicator.text = glyph_str

    # ------------------------------------------------------------ workspace & tabs
    def _refresh_workspace(self) -> None:
        if not self.engine:
            return
        self.snapshot = ui_helpers.dir_snapshot(
            self.engine.root, self.engine.current, prev=self.snapshot
        )
        ids = self._ids()
        if "crumb_label" in ids:
            crumbs_txt = " › ".join(lbl for lbl, _ in self.snapshot.breadcrumbs)
            ids.crumb_label.text = crumbs_txt
        if "btn_tab_files" in ids:
            total = self.snapshot.folder_count + self.snapshot.file_count
            ids.btn_tab_files.text = f"📁 Files ({total})"
        if "btn_undo_top" in ids:
            t_cnt = self.snapshot.trash_count
            ids.btn_undo_top.text = f"↩ {t_cnt}" if t_cnt > 0 else "↩"

    def switch_tab(self, tab: str) -> None:
        self.active_tab = tab if tab in ("chat", "files") else "chat"
        if self.active_tab == "files":
            self._refresh_workspace()
            self._render_files_view()
        else:
            self._render_chat_view()

    def navigate_up(self) -> None:
        self.run_quick_command("go back")

    # ------------------------------------------------------------ chat & file rendering
    def _kind_color(self, kind: str) -> list[float]:
        pal = animations.get_theme(self.theme_name)
        hex_c = {
            "you": pal["user_msg"],
            "thans": pal["asst_msg"],
            "cmd": pal["cmd_pill"],
            "ok": pal["ok"],
            "err": pal["err"],
            "sys": pal["dim"],
        }.get(kind, pal["fg"])
        return list(animations.hex_to_rgba(hex_c))

    def _make_chat_label(self, who: str, text: str, kind: str, animate: bool = True) -> Label:
        color = self._kind_color(kind)
        prefix = f"[b]{who}[/b]  " if who else ""
        lbl = Label(
            text=f"{prefix}{text}",
            markup=True,
            color=color,
            size_hint_y=None,
            halign="left",
            valign="top",
            font_size=sp(14),
            opacity=0.15 if animate else 1.0,
        )
        lbl.bind(
            width=lambda inst, w: setattr(inst, "text_size", (max(100, w - dp(12)), None)),
            texture_size=lambda inst, ts: setattr(inst, "height", max(dp(26), ts[1] + dp(10))),
        )
        lbl.height = max(dp(28), lbl.texture_size[1] + dp(10))
        if animate:
            try:
                Animation(opacity=1.0, d=0.20, t="out_cubic").start(lbl)
            except Exception:
                lbl.opacity = 1.0
        return lbl

    def _add(self, who: str, text: str, kind_or_color="sys") -> None:
        kind = kind_or_color if isinstance(kind_or_color, str) else "sys"
        self.chat_records.insert(0, (who, text, kind))
        if self.active_tab != "chat":
            return
        box = self._ids().chat_box
        lbl = self._make_chat_label(who, text, kind, animate=True)
        # Support both standard Kivy BoxLayout.add_widget and any mock list shim
        if hasattr(box, "add_widget"):
            box.add_widget(lbl, index=len(box.children))
        elif hasattr(box, "insert"):
            box.insert(0, lbl)
        self._scroll_top()

    def _render_chat_view(self) -> None:
        box = self._ids().chat_box
        box.clear_widgets()
        for who, text, kind in reversed(self.chat_records[:80]):
            lbl = self._make_chat_label(who, text, kind, animate=False)
            if hasattr(box, "add_widget"):
                box.add_widget(lbl, index=len(box.children))
            elif hasattr(box, "insert"):
                box.insert(0, lbl)
        self._scroll_top()

    def _render_files_view(self) -> None:
        box = self._ids().chat_box
        box.clear_widgets()
        if not self.snapshot or not self.snapshot.entries:
            empty_lbl = self._make_chat_label(
                "📂 Empty Folder",
                "No files here yet. Tap '➕ Folder' or '📝 File' below to create one.",
                "sys",
                animate=True,
            )
            if hasattr(box, "add_widget"):
                box.add_widget(empty_lbl)
            return

        for entry in self.snapshot.entries:
            row = BoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(40),
                spacing=dp(6),
                opacity=0.2,
            )
            main_btn = Button(
                text=f"{entry.icon}  {entry.name}   ({entry.size_label})",
                halign="left",
                valign="middle",
                font_size=sp(13),
                background_normal="",
                background_color=(
                    list(self.ok_color[:3]) + [0.22]
                    if entry.is_changed
                    else self.panel2_color
                ),
                color=self.fg_color,
            )
            main_btn.bind(
                size=lambda inst, sz: setattr(inst, "text_size", (max(60, sz[0] - dp(16)), None))
            )
            if entry.is_dir:
                main_btn.bind(on_release=lambda _b, n=entry.name: self.run_quick_command(f"go to {n}"))
            else:
                main_btn.bind(on_release=lambda _b, n=entry.name: self.prefill_input(f"rename {n} to "))

            del_btn = Button(
                text="♻️",
                size_hint_x=None,
                width=dp(44),
                font_size=sp(13),
                background_normal="",
                background_color=self.panel2_color,
                color=self.warn_color,
            )
            del_btn.bind(on_release=lambda _b, n=entry.name: self.run_quick_command(f"delete {n}"))

            row.add_widget(main_btn)
            row.add_widget(del_btn)
            box.add_widget(row)
            try:
                Animation(opacity=1.0, d=0.18, t="out_cubic").start(row)
            except Exception:
                row.opacity = 1.0

    def _scroll_top(self) -> None:
        def _do(_dt):
            sc = self._ids().chat_scroll
            if hasattr(sc, "scroll_y"):
                sc.scroll_y = 1.0
            if hasattr(sc, "set_normalized_y"):
                sc.set_normalized_y(1)

        Clock.schedule_once(_do, 0.04)

    # ------------------------------------------------------------ live preview & chips
    def on_input_change(self, text: str) -> None:
        if not self._root or "preview_label" not in self._ids():
            return
        cur = self.engine.current if self.engine else None
        prev = ui_helpers.preview_intent(text, cur)
        lbl = self._ids().preview_label
        sub = f" · {prev.subtitle}" if prev.subtitle else ""
        lbl.text = f"{prev.icon} {prev.title}{sub}"
        if prev.state == "matched":
            lbl.color = self.ok_color
        elif prev.state == "partial":
            lbl.color = self.accent_color
        elif prev.state == "unknown":
            lbl.color = self.warn_color
        else:
            lbl.color = self.dim_color

    def prefill_input(self, text: str) -> None:
        inp = self._ids().input
        inp.text = text
        inp.focus = True
        self.on_input_change(text)

    def complete_input(self) -> None:
        inp = self._ids().input
        cur = self.engine.current if self.engine else None
        completed = ui_helpers.autocomplete(inp.text, cur)
        inp.text = completed
        self.on_input_change(completed)

    def run_quick_command(self, cmd_text: str) -> None:
        self._add("You", cmd_text, "you")
        Clock.schedule_once(lambda dt: self._run(cmd_text), 0.03)

    # ------------------------------------------------------------ commands
    def send_input(self) -> None:
        inp = self._ids().input
        text = inp.text.strip()
        if not text:
            return
        inp.text = ""
        self.on_input_change("")
        if self.active_tab != "chat":
            self.switch_tab("chat")
        self._add("You", text, "you")
        Clock.schedule_once(lambda dt: self._run(text), 0.04)

    def _run(self, text: str) -> None:
        self.sonic_state = "thinking"
        try:
            res = self.engine.run(text)
        except Exception as e:  # noqa: BLE001
            self.sonic_state = "error"
            self._flash_ticks = 18
            self._add("THANS", f"Error: {e}", "err")
            return

        self.sonic_state = "success" if res.ok else "error"
        self._flash_ticks = 20
        if res.command:
            self._add("⚡", res.command, "cmd")
        self._add("THANS", res.message, "thans" if res.ok else "err")
        self._refresh_workspace()
        if self.active_tab == "files":
            self._render_files_view()
        self._set_status(f"● folder: {self.snapshot.rel_current if self.snapshot else self.engine.current}")
        if self.speak_on:
            audio.speak(res.message)

    def say_help(self) -> None:
        if self.active_tab != "chat":
            self.switch_tab("chat")
        Clock.schedule_once(lambda dt: self._run("help"), 0.04)

    def clear_chat(self) -> None:
        self.chat_records.clear()
        self._ids().chat_box.clear_widgets()
        self._add("THANS", "Chat cleared.", "sys")

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
            self.sonic_state = "idle"
            self.sonic_level = 0.0
            ids.btn_mic.text = "🎤 MIC"
            self._set_status("● mic stopped")
            return
        if audio.start_listening(
            self._on_speech,
            on_partial=self._on_partial_speech,
            on_rms=self._on_rms,
        ):
            self.mic_active = True
            self.sonic_state = "listening"
            ids.btn_mic.text = "⏹ STOP"
            self._set_status("🎙 listening… speak now")
        else:
            self._set_status("● speech unavailable — use text or chips")

    def _on_partial_speech(self, partial: str) -> None:
        Clock.schedule_once(
            lambda dt: setattr(self._ids().preview_label, "text", f"🎙 Hearing: \"{partial}\""),
            0.02,
        )

    def _on_rms(self, rms: float) -> None:
        norm = max(0.0, min(1.0, (rms + 2.0) / 12.0))
        self.sonic_level = norm

    def _on_speech(self, text: str | None, err: str | None) -> None:
        # pyjnius callbacks arrive on the Android thread — hop to Kivy's thread
        Clock.schedule_once(lambda dt: self._handle_speech(text, err), 0.04)

    def _handle_speech(self, text: str | None, err: str | None) -> None:
        self.mic_active = False
        self.sonic_state = "idle"
        self.sonic_level = 0.0
        self._ids().btn_mic.text = "🎤 MIC"
        if text:
            self._set_status(f"🎙 heard: {text}")
            self._add("You (voice)", text, "you")
            Clock.schedule_once(lambda dt: self._run(text), 0.04)
        else:
            self._set_status(f"● speech: {err or 'no result'}")

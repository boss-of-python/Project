"""THANS desktop window — minimal, animated, one accent colour.

Layout
------
    ┌ header ─────────────────────────────────────────────────────────┐
    │ ✦ THANS  v0.2.0     [folder] [voice] [llm]         ↺  ↓  ⚙      │
    ├───────────── chat transcript ──────────┬── dashboard ──────────┤
    │  THANS ▎ rules        (types itself…)  │  working folder card  │
    │                              You ▎     │  quick actions        │
    │                          list work     │  voice card           │
    ├────────────────────────────────────────┴───────────────────────┤
    │  ● suggestions                                       ┌───────┐ │
    │  [ ▍ tell me what to do…            ] [🎤] [ Send ➤ ] │status │ │
    └───────────────────────────────────────────────────────────────┘

Everything visible is drawn from ``ui/theme.py`` tokens and animated by a single
60 fps loop (``_tick``) that also drains the worker queue — one loop, one
source of truth, no widget ever blocks.
"""
from __future__ import annotations

import queue
import shutil
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from tkinter import font as tkfont
from tkinter import filedialog, messagebox, ttk
import tkinter as tk

from . import APP_NAME, APP_TAGLINE, __version__, config, model_manager
from .engine import COMMAND_REFERENCE, Engine
from .stt import VoiceSTT
from .tts import Speaker
from .ui import logic
from .ui import theme as T
from .ui.chat import ChatLog, EmptyState
from .ui.panels import (BootOverlay, FolderCard, HelpPanel, QuickCard,
                        SettingsPanel, VoiceCard)
from .ui.widgets import (Card, Chip, IconButton, ProgressBar, RoundedButton, Toaster,
                         Tooltip, widget_bg)

#: Set THANS_NO_BOOT=1 to skip the start screen (tests, screenshots, slow machines).
NO_BOOT = bool(__import__("os").environ.get("THANS_NO_BOOT"))


class ThansApp:
    """The desktop app. Public surface: :meth:`run`, :meth:`submit`."""

    def __init__(self, cfg: dict | None = None, text_only: bool = False):
        self.cfg = dict(cfg or config.load_config())
        self.text_only = text_only
        self.anim = logic.Animator(fps=60) if T.motion_enabled(self.cfg) else None

        # ---- model & engine layer (created before the window so the boot
        #      screen can report real progress)
        self.engine: Engine | None = None
        self.speaker: Speaker | None = None
        self.stt: VoiceSTT | None = None
        self.model_status: dict = {}
        self.mic_on = False
        self.busy = False
        self._downloading = False

        # ---- state
        self.history: list[str] = []
        self._hist_i: int | None = None
        self._draft = ""            # what was typed before browsing history
        self._q: "queue.Queue" = queue.Queue()
        self._last_dt = time.time()
        self._suggest_job = None
        self._boot_done = False
        self.toaster = None
        self.thinking = None
        self._hero_alive = True

        self.root = tk.Tk()
        self.root.withdraw()                       # shown once the chrome is built
        self.root.title(f"{APP_NAME} — {APP_TAGLINE}")
        self.root.configure(bg=T.BG)
        self.root.minsize(680, 520)
        self._restore_geometry()
        self.fonts = self._load_fonts()
        self._style_ttk()
        self._build()
        self._bind_keys()

        if NO_BOOT:
            self._finish_boot()
        else:
            self.root.deiconify()
            self._run_boot()

    # =====================================================================
    # boot
    # =====================================================================
    def _run_boot(self) -> None:
        steps = [
            ("starting engine", self._boot_engine),
            ("checking offline models", self._boot_models),
            ("scanning working folder", self._boot_scan),
            ("ready", lambda: None),
        ]
        self.boot = BootOverlay(self.root, self.anim, self.fonts, steps,
                                on_done=self._finish_boot)
        self.boot.start()
        self.root.deiconify()

    def _boot_engine(self) -> None:
        self.engine = Engine(self.cfg["root"], self.cfg)
        self.speaker = Speaker(self.cfg.get("tts", True), int(self.cfg.get("tts_rate", 185)))
        self.stt = VoiceSTT()

    def _boot_models(self) -> None:
        self.model_status = model_manager.status(self.cfg)

    def _boot_scan(self) -> None:
        self.folder_card.set_root(self.engine.root)

    def _finish_boot(self) -> None:
        if self._boot_done:
            return
        self._boot_done = True
        self.root.deiconify()
        self.deiconify_if_needed()
        self._refresh_chips()
        self._welcome()
        self.hero.reveal()
        self.input.focus_set()
        self._tick()

    def deiconify_if_needed(self) -> None:
        try:
            self.root.deiconify()
        except tk.TclError:
            pass

    # =====================================================================
    # chrome
    # =====================================================================
    def _restore_geometry(self) -> None:
        geo = str(self.cfg.get("window") or "")
        if geo and "x" in geo:
            try:
                self.root.geometry(geo)
                return
            except tk.TclError:
                pass
        w, h = 1060, 700
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x, y = max(0, (sw - w) // 2), max(0, (sh - h) // 3)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _load_fonts(self) -> dict:
        try:
            families = set(tkfont.families(self.root))
        except tk.TclError:
            families = set()
        ui = T.resolve_family(families, T.UI_FAMILIES)
        mono = T.resolve_family(families, T.MONO_FAMILIES)
        return {
            "ui": ui, "mono": mono,
            "title": (ui, T.SIZE_TITLE, "bold"),
            "h2": (ui, T.SIZE_BODY, "bold"),
            "body": (ui, T.SIZE_BODY),
            "mono_small": (mono, T.SIZE_SMALL),
            "small": (ui, T.SIZE_SMALL),
            "small_bold": (ui, T.SIZE_SMALL, "bold"),
            "tiny": (ui, T.SIZE_TINY),
        }

    def _style_ttk(self) -> None:
        st = ttk.Style(self.root)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure(".", background=T.BG, foreground=T.FG)
        st.configure("TCombobox", fieldbackground=T.SURFACE_HI, background=T.SURFACE_HI,
                     foreground=T.FG, arrowcolor=T.FG_DIM, borderwidth=0)
        st.configure("Vertical.TScrollbar", background=T.SURFACE_HI, troughcolor=T.BG,
                     borderwidth=0, arrowcolor=T.FG_DIM)

    def _build(self) -> None:
        self.root.grid_rowconfigure(2, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self._build_header()

        # ---- body: transcript + dashboard
        body = tk.Frame(self.root, bg=T.BG)
        body.grid(row=2, column=0, sticky="nsew", padx=T.PAD, pady=(0, T.PAD_S))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)
        self.body = body

        chat_wrap = tk.Frame(body, bg=T.BG)
        chat_wrap.grid(row=0, column=0, sticky="nsew")
        self.chat_card = Card(chat_wrap, animator=self.anim, hug=False, fill=T.BG,
                              border=T.BORDER, radius=T.RADIUS_LG, padding=0)
        self.chat_card.pack(fill="both", expand=True)
        self.chat = ChatLog(self.chat_card.body, self.anim, fonts=self.fonts,
                            on_rerun=self.submit, on_clear=self.clear_chat)
        self.chat.pack(fill="both", expand=True)
        self.hero = EmptyState(self.chat_card.body, self.anim, self.fonts,
                               on_starter=self._starter_clicked)
        self.hero.place(relx=0, rely=0, relwidth=1, relheight=1)

        # ---- dashboard column (hidden on narrow windows)
        self.side = tk.Frame(body, bg=T.BG, width=264)
        self.folder_card = FolderCard(self.side, self.anim, self.fonts,
                                      on_open=self._open_root)
        self.folder_card.pack(fill="x")
        self.quick_card = QuickCard(self.side, self.anim, self.fonts, [
            (T.SYM["wand"], "Organize", "Group this folder's files by type", "organize"),
            (T.SYM["undo"], "Undo", "Reverse the last action (Ctrl+Z)", "undo"),
            (T.SYM["search"], "Find", "Search by name or extension", "find"),
            (T.SYM["list"], "Count", "How many files are here?", "count"),
        ])
        self.quick_card.pack(fill="x", pady=(T.PAD_S, 0))
        self.voice_card = VoiceCard(self.side, self.anim, self.fonts,
                                    on_speak_toggle=self._toggle_speak,
                                    speak_on=bool(self.cfg.get("tts")))
        self.voice_card.pack(fill="x", pady=(T.PAD_S, 0))
        self.quick_card.buttons["organize"].command = lambda: self.submit("organize .")
        self.quick_card.buttons["undo"].command = lambda: self.submit("undo")
        self.quick_card.buttons["find"].command = self._focus_find
        self.quick_card.buttons["count"].command = lambda: self.submit("how many files in .")
        self._side_visible = True
        self._apply_responsive()

        self._build_composer()
        self._build_status()
        self.toaster = Toaster(self.body, self.anim, font=self.fonts["small"], offset_y=12)
        self.settings = SettingsPanel(body, self.anim, self.fonts, self.cfg,
                                      on_change=self._setting_changed,
                                      on_pick_root=self._pick_root,
                                      on_download=self._download_models)
        self.help_panel = HelpPanel(body, self.anim, self.fonts,
                                    on_run=self._fill_and_focus)
        self.root.bind("<Configure>", lambda e: self._apply_responsive())

    # ------------------------------------------------------------- header
    def _build_header(self) -> None:
        head = tk.Frame(self.root, bg=T.BG, height=58)
        head.grid(row=0, column=0, sticky="ew", padx=T.PAD, pady=(T.PAD_S, 2))
        head.pack_propagate(False)

        mark = tk.Canvas(head, width=30, height=30, bg=T.BG, highlightthickness=0, bd=0)
        mark.pack(side="left", pady=6)
        from .ui.widgets import draw_round_rect
        draw_round_rect(mark, 1, 1, 29, 29, 9, T.mix(T.ACCENT, T.ACCENT2, 0.5))
        mark.create_text(15, 15, text=T.SYM["sparkle"], fill="#ffffff",
                         font=(self.fonts["ui"], 13, "bold"))

        tk.Label(head, text=APP_NAME, bg=T.BG, fg=T.FG,
                 font=(self.fonts["ui"], 14, "bold")).pack(side="left", padx=(8, 6), pady=6)
        tk.Label(head, text=f"v{__version__}", bg=T.BG, fg=T.FG_FAINT,
                 font=self.fonts["tiny"]).pack(side="left", pady=(10, 0))

        # right-hand cluster
        tools = tk.Frame(head, bg=T.BG)
        tools.pack(side="right", pady=6)
        self.btn_settings = IconButton(tools, glyph=T.SYM["settings"], command=self.open_settings,
                                       animator=self.anim, bg=T.BG, size=34)
        self.btn_settings.pack(side="right", padx=(6, 0))
        Tooltip(self.btn_settings, "Settings  (Ctrl+,)", font=self.fonts["tiny"])
        self.btn_models = IconButton(tools, glyph=T.SYM["models"], command=self._download_models,
                                     animator=self.anim, bg=T.BG, size=34)
        self.btn_models.pack(side="right", padx=(6, 0))
        Tooltip(self.btn_models, "Download the offline speech model once (~40 MB)",
                font=self.fonts["tiny"])
        self.btn_undo = IconButton(tools, glyph=T.SYM["undo"], command=lambda: self.submit("undo"),
                                   animator=self.anim, bg=T.BG, size=34)
        self.btn_undo.pack(side="right", padx=(6, 0))
        Tooltip(self.btn_undo, "Undo the last action  (Ctrl+Z)", font=self.fonts["tiny"])

        chips = tk.Frame(head, bg=T.BG)
        chips.pack(side="right", pady=8, padx=(0, 12))
        self.chip_root = Chip(chips, text="folder", state="ready", animator=self.anim,
                              command=self._pick_root, font=self.fonts["small"], bg=T.BG)
        self.chip_root.pack(side="right", padx=4)
        Tooltip(self.chip_root, "Working folder — click to change", font=self.fonts["tiny"])
        self.chip_voice = Chip(chips, text="voice", state="off", animator=self.anim,
                               command=self.open_settings, font=self.fonts["small"], bg=T.BG)
        self.chip_voice.pack(side="right", padx=4)
        self.chip_llm = Chip(chips, text="llm", state="off", animator=self.anim,
                             command=self.open_settings, font=self.fonts["small"], bg=T.BG)
        self.chip_llm.pack(side="right", padx=4)
        tk.Frame(self.root, bg=T.BORDER, height=1).grid(row=1, column=0, sticky="ew")

    # ----------------------------------------------------------- composer
    def _build_composer(self) -> None:
        wrap = tk.Frame(self.root, bg=T.BG)
        wrap.grid(row=3, column=0, sticky="ew", padx=T.PAD, pady=(0, 6))
        wrap.grid_columnconfigure(0, weight=1)

        # suggestion pills (appear as you type, Tab/click to accept)
        self.suggest_row = tk.Frame(wrap, bg=T.BG)
        self.suggest_buttons: list[RoundedButton] = []

        box = Card(wrap, animator=self.anim, fill=T.BG_RAISED, border=T.BORDER_HI,
                   radius=T.RADIUS_LG, padding=8, hug=False, height=54)
        box.grid(row=1, column=0, sticky="ew")
        self.composer = box
        row = tk.Frame(box.body, bg=T.BG_RAISED)
        row.pack(fill="both", expand=True)

        self.input = tk.Text(row, height=1, bg=T.BG_RAISED, fg=T.FG, relief="flat",
                             insertbackground=T.ACCENT_HI, wrap="word",
                             font=self.fonts["body"], highlightthickness=0,
                             padx=6, pady=6, spacing1=2, spacing2=2, undo=True,
                             maxundo=50, selectbackground=T.ACCENT_LO)
        self.input.pack(side="left", fill="both", expand=True)
        self._placeholder = "tell me what to do — 'create folder reports', 'organize downloads'…"
        self.input.insert("1.0", self._placeholder)
        self.input.configure(fg=T.FG_FAINT)
        self._placeholder_on = True
        self.input.bind("<FocusIn>", self._placeholder_focus)
        self.input.bind("<KeyRelease>", self._on_key_release)
        self.input.bind("<Return>", self._on_return)
        self.input.bind("<Shift-Return>", lambda e: None)
        self.input.bind("<Up>", lambda e: self._history_step(-1))
        self.input.bind("<Down>", lambda e: self._history_step(1))
        self.input.bind("<Tab>", lambda e: self._accept_suggestion())
        self.input.bind("<Escape>", lambda e: self._escape())

        btns = tk.Frame(row, bg=T.BG_RAISED)
        btns.pack(side="right")
        self.btn_send = RoundedButton(btns, text="Send", glyph=T.SYM["send"], primary=True,
                                      command=self._send_clicked, animator=self.anim,
                                      font=self.fonts["small_bold"], bg=T.BG_RAISED,
                                      pad_x=12, pad_y=7)
        self.btn_send.pack(side="right", padx=(6, 0))
        self.btn_mic = IconButton(btns, glyph=T.SYM["mic"], command=self.toggle_mic,
                                  animator=self.anim, bg=T.BG_RAISED, size=34)
        if not self.text_only:
            self.btn_mic.pack(side="right", padx=(6, 0))
            Tooltip(self.btn_mic, "Voice command  (F2)", font=self.fonts["tiny"])
        else:
            self.btn_mic.pack_forget()
        self.thinking = None   # created lazily next to the send button

    # ------------------------------------------------------------- status
    def _build_status(self) -> None:
        bar = tk.Frame(self.root, bg=T.BG)
        bar.grid(row=4, column=0, sticky="ew", padx=T.PAD, pady=(0, T.PAD_S))
        self.status_lbl = tk.Label(bar, text="ready", bg=T.BG, fg=T.FG_DIM,
                                   font=self.fonts["small"], anchor="w")
        self.status_lbl.pack(side="left")
        self.status_bar = ProgressBar(bar, animator=self.anim, height=4)
        tk.Label(bar, text=logic.keys_hint(), bg=T.BG, fg=T.FG_FAINT,
                 font=self.fonts["tiny"]).pack(side="right")

    # =====================================================================
    # keyboard & input behaviour
    # =====================================================================
    def _bind_keys(self) -> None:
        r = self.root
        r.bind("<F1>", lambda e: self.open_help())
        r.bind("<F2>", lambda e: self.toggle_mic())
        r.bind("<Control-z>", lambda e: self.submit("undo"))
        r.bind("<Control-k>", lambda e: self.clear_chat())
        r.bind("<Control-l>", lambda e: self._focus_input())
        r.bind("<Control-comma>", lambda e: self.open_settings())
        r.bind("<Control-q>", lambda e: self._on_close())
        r.bind("<Escape>", lambda e: self._escape())
        r.bind("<F5>", lambda e: self.folder_card.refresh(self.engine.root))
        r.bind("<Control-plus>", lambda e: self._zoom(1))
        r.bind("<Control-minus>", lambda e: self._zoom(-1))

    def _zoom(self, delta: int) -> None:
        self._zoom_level = max(-3, min(5, getattr(self, "_zoom_level", 0) + delta))
        base = T.SIZE_BODY + self._zoom_level
        self.input.configure(font=(self.fonts["ui"], base))
        self.chat.text.configure(font=(self.fonts["ui"], base))
        for tag, size in (("body", base), ("body_you", base), ("card", base - 1),
                          ("small", base - 1), ("small_bold", base - 1),
                          ("tiny", base - 2), ("meta", base - 2)):
            try:
                self.chat.text.tag_configure(tag, font=(self.fonts["ui"], size))
            except tk.TclError:
                pass
        self.toast(f"Text size {base} pt", "info")

    def _placeholder_focus(self, _e=None) -> None:
        if self._placeholder_on:
            self.input.delete("1.0", "end")
            self.input.configure(fg=T.FG)
            self._placeholder_on = False

    def _input_text(self) -> str:
        return "" if self._placeholder_on else self.input.get("1.0", "end-1c").strip()

    def _set_input(self, text: str, caret_at_end: bool = True) -> None:
        self._placeholder_on = False
        self.input.configure(fg=T.FG)
        self.input.delete("1.0", "end")
        self.input.insert("1.0", text)
        if caret_at_end:
            self.input.mark_set("insert", "end-1c")
        self.input.focus_set()
        self._update_suggestions()

    def _focus_input(self) -> None:
        self.input.focus_set()

    def _focus_find(self) -> None:
        self._set_input("find ")
        self.toast("Type a name or extension (e.g. 'find invoice', 'search for pdf files')")

    def _escape(self) -> None:
        if self.settings.is_open:
            self.settings.close()
            return
        if self.help_panel.is_open:
            self.help_panel.close()
            return
        if self._input_text():
            self._set_input("")
            return
        if self.mic_on:
            self.toggle_mic()

    def _on_return(self, _e=None):
        if _e is not None and (_e.state & 0x0001):        # Shift+Return → newline
            return None
        self._send_clicked()
        return "break"

    def _send_clicked(self) -> None:
        text = self._input_text()
        if not text:
            self._shake_composer()
            return
        self._set_input("")
        self.submit(text)

    def _shake_composer(self) -> None:
        """Little head-shake when Enter is pressed with an empty box."""
        if self.anim is None:
            self.input.configure(bg=T.mix(T.BG_RAISED, T.ERR, 0.18))
            self.root.after(220, lambda: self.input.configure(bg=T.BG_RAISED))
            return
        self.anim.add(logic.Tween(0.24, easing=logic.out_quart,
                                  on_update=self._nudge_composer,
                                  on_done=lambda: self.input.configure(bg=T.BG_RAISED,
                                                                       padx=6)))

    def _nudge_composer(self, v: float) -> None:
        import math
        wobble = math.sin(v * math.pi * 3) * (1 - v)
        self.input.configure(padx=6 + int(wobble * 7),
                             bg=T.mix(T.BG_RAISED, T.ERR, 0.18 * (1 - v)))

    # ------------------------------------------------------------- history
    def _history_step(self, delta: int) -> str:
        """Up/Down browse previous commands; leaving the list restores the draft."""
        if not self.history:
            return "break"
        if self._hist_i is None:
            self._draft = self._input_text()
            self._hist_i = len(self.history)
        self._hist_i = max(0, min(len(self.history), self._hist_i + delta))
        if self._hist_i >= len(self.history):
            self._hist_i = None
            self._set_input(self._draft)          # back to what was being typed
        else:
            self._set_input(self.history[self._hist_i])
        return "break"

    # ---------------------------------------------------------- suggestions
    def _on_key_release(self, _e=None) -> None:
        self._update_suggestions()

    def _update_suggestions(self) -> None:
        text = self._input_text()
        names, dirs = [], []
        if self.engine is not None:
            try:
                names = [p.name for p in self.engine.current.iterdir()][:80]
                dirs = [p.name for p in self.engine.current.iterdir() if p.is_dir()][:40]
            except OSError:
                pass
        items = logic.suggest(text, names, dirs, limit=4)
        self._render_suggestions(items)

    def _render_suggestions(self, items: list[str]) -> None:
        if not items or self._placeholder_on:
            if self.suggest_row.winfo_ismapped():
                self.suggest_row.pack_forget()
            return
        for b in self.suggest_buttons:
            b.destroy()
        self.suggest_buttons.clear()
        for i, item in enumerate(items):
            b = RoundedButton(self.suggest_row, text=logic.truncate(item, 28),
                              command=lambda t=item: self._accept_suggestion(t),
                              animator=self.anim, subtle=True, pad_x=9, pad_y=3,
                              font=self.fonts["tiny"], bg=T.BG)
            b.pack(side="left", padx=(0, 6))
            self.suggest_buttons.append(b)
            if self.anim is not None:
                b.anim_to(lambda v, bb=b: bb.configure(bg=T.BG), 0.01)
        if not self.suggest_row.winfo_ismapped():
            self.suggest_row.grid(row=0, column=0, sticky="w", pady=(0, 5))

    def _accept_suggestion(self, text: str | None = None) -> str:
        if text is None:
            text = self._input_text()
            names, dirs = [], []
            if self.engine is not None:
                try:
                    names = [p.name for p in self.engine.current.iterdir()][:80]
                    dirs = [p.name for p in self.engine.current.iterdir() if p.is_dir()][:40]
                except OSError:
                    pass
            choices = logic.suggest(text, names, dirs, limit=1)
            if not choices:
                return "break"
            text = choices[0]
        self._set_input(text)
        if text.endswith(("<name>", "<text>", "<old>", "<new>", "<item>", "<folder>")):
            self.input.mark_set("insert", "end-1c")
        return "break"

    def _starter_clicked(self, command: str) -> None:
        self._set_input(command)
        self.input.focus_set()

    # =====================================================================
    # command flow
    # =====================================================================
    def submit(self, text: str) -> None:
        """Run a command: transcript entry → worker thread → streamed reply."""
        text = (text or "").strip()
        if not text:
            return
        if text.casefold() in ("help", "?", "show help"):
            self.open_help()                  # nicer than a wall of text
            return
        self._set_status("thinking…")
        self.hide_hero()
        self.chat.finish_streams()
        self.chat.add_user(text)
        self.history = [h for h in self.history if h != text] + [text]
        self._hist_i, self._draft = None, "",
        self._render_suggestions([])
        self._set_busy(True)
        threading.Thread(target=self._worker, args=(text,), daemon=True).start()

    def _worker(self, text: str) -> None:
        started = time.time()
        try:
            res = self.engine.run(text)
            elapsed = time.time() - started
            self._q.put(("reply", res, elapsed))
        except Exception:                      # noqa: BLE001
            self._q.put(("crash", traceback.format_exc(limit=6), None))

    def _on_reply(self, res, elapsed: float | None) -> None:
        self._set_busy(False)
        self.chat.add_reply(res.message, ok=res.ok, source=res.source,
                            card=len(res.message) > 260)
        self._set_status(self._status_line())
        if self.cfg.get("tts") and self.speaker:
            self.speaker.say(res.message)
        if res.ok:
            if res.command:
                self.quick_card.buttons["undo"].set_enabled(True)
            if logic.should_celebrate(res.command, res.ok):
                self._burst()
        else:
            self.toast(logic.truncate(res.message, 64), "error")
        self.folder_card.refresh(self.engine.root)
        if self.settings.is_open:
            self.settings.set_root_label(str(self.engine.root))

    def _burst(self) -> None:
        from .ui.widgets import Burst
        w = max(320, self.chat_card.winfo_width())
        h = max(160, min(240, self.chat_card.winfo_height()))
        b = Burst(self.chat_card, self.anim, size=(w, h))
        b.place(relx=0, rely=0.5, anchor="w", width=w, height=h)
        b.fire()

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.btn_send.set_enabled(not busy)
        if busy:
            self.chat_card.pulse_glow(True)
            self._start_thinking()
            self.status_bar.start_indeterminate(1.4)
            self.status_bar.place(in_=self.chat_card, relx=0, rely=1.0, anchor="sw",
                                  relwidth=1, height=3)
            self.status_bar.lift()
        else:
            self.anim_stop_thinking()
            self.chat_card.pulse_glow(False)
            self.status_bar.stop_indeterminate()
            self.status_bar.place_forget()

    # ------------------------------------------------------- thinking dots
    def _start_thinking(self) -> None:
        from .ui.widgets import Dots
        if self.thinking is None:
            self.thinking = Dots(self.root, animator=self.anim, bg=T.BG, size=22)
        try:
            self.thinking.place(in_=self.chat_card, relx=0.5, rely=0.5, anchor="center")
        except tk.TclError:
            pass
        self.thinking.start()

    def anim_stop_thinking(self) -> None:
        if self.thinking is not None:
            self.thinking.stop()
            try:
                self.thinking.place_forget()
            except tk.TclError:
                pass

    # =====================================================================
    # voice
    # =====================================================================
    def toggle_mic(self) -> None:
        if self.text_only or self.stt is None:
            self.toast("Text-only mode — restart without --text-only for voice", "warn")
            return
        if self.mic_on:
            self.stt.stop()
            self._set_mic(False)
            return
        if not self.stt.available():
            self.toast("Speech model missing — click ↓ once to download it (~40 MB)", "warn")
            self.open_settings()
            return
        ok = self.stt.start(on_final=self._voice_final, on_state=self._mic_state)
        if ok:
            self._set_mic(True)
            self.chat.add_system("Listening — speak your command, then pause.", "info")
        else:
            self.toast("Microphone unavailable", "error")

    def _mic_state(self, msg: str) -> None:
        self._q.put(("mic_state", msg))

    def _voice_final(self, text: str) -> None:
        self._q.put(("mic", False))
        self._q.put(("voice", text))

    def _set_mic(self, on: bool) -> None:
        self.mic_on = on
        if self.text_only:
            return
        self.btn_mic.configure_glyph(T.SYM["stop"] if on else T.SYM["mic"])
        self.btn_mic.primary = on
        self.btn_mic.ring = on
        self.btn_mic._hover = 0.0
        self.btn_mic._draw()
        self.voice_card.set_state("listening — speak now…" if on else "mic idle · F2 to talk", on)
        if on:
            self.chip_voice.set(state="listening")
            self._set_status("listening…")
        else:
            self._refresh_chips()
            self._set_status(self._status_line())

    def _toggle_speak(self, value: bool) -> None:
        self.cfg["tts"] = bool(value)
        if self.speaker:
            self.speaker.enabled = bool(value)
        config.save_config(self.cfg)
        self._refresh_chips()
        self.toast("Spoken replies " + ("on" if value else "off"))

    # =====================================================================
    # settings & models
    # =====================================================================
    def open_help(self) -> None:
        """Command reference as a tappable sheet (F1 / the Help button)."""
        if self.help_panel.is_open:
            self.help_panel.close()
            return
        if self.settings.is_open:
            self.settings.close()
        self.help_panel.open()

    def _fill_and_focus(self, command: str) -> None:
        """Put a suggested command in the composer, ready to run."""
        self._set_input(command)
        self.input.focus_set()
        if self.engine is not None:
            self._set_status("press ⏎ to run · Esc clears")

    def open_settings(self) -> None:
        if self.settings.is_open:
            self.settings.close()
            return
        if self.help_panel.is_open:
            self.help_panel.close()
        self.settings.cfg = dict(self.cfg)
        self.settings.open()

    def _setting_changed(self, key: str, value) -> None:
        self.cfg[key] = value
        config.save_config(self.cfg)
        if key == "motion":
            self.anim = logic.Animator(fps=60) if value else None
            for w in (self.chat, self.chat.bar, self.folder_card, self.quick_card,
                      self.voice_card, *self.quick_card.buttons.values(),
                      self.btn_send, self.btn_mic, self.btn_undo, self.btn_models,
                      self.btn_settings, self.chip_root, self.chip_voice, self.chip_llm,
                      self.folder_card.bar, self.composer):
                if hasattr(w, "anim"):
                    w.anim = self.anim
            self.toast("Animations " + ("on" if value else "off (instant UI)"))
        elif key == "tts":
            if self.speaker:
                self.speaker.enabled = bool(value)
            self._refresh_chips()
        elif key == "tts_rate":
            if self.speaker:
                self.speaker.set_rate(int(value))
        elif key == "use_llm":
            if self.engine:
                self.engine.cfg["use_llm"] = bool(value)
                if value and self.engine.llm is None:
                    try:
                        from .parser_llm import LLMParser
                        lp = LLMParser(self.cfg)
                        self.engine.llm = lp if lp.available() else None
                    except Exception:
                        self.engine.llm = None
                if not value:
                    self.engine.llm = None
            self._refresh_chips()
            if value and self.engine and self.engine.llm is None:
                self.toast("No GGUF model / llama-cpp-python found — using the rule parser",
                           "warn")
            else:
                self.toast("Free-form parsing " + ("on" if value else "off"))
        elif key == "llm_model":
            self.toast("Model set to " + logic.truncate(str(value), 28))
        elif key == "permanent_delete":
            self.toast("Permanent delete " + ("ON — deletions cannot be undone" if value else "off"),
                       "error" if value else "info")
        elif key == "root":
            self._apply_root(str(value))

    def _apply_root(self, path: str) -> None:
        if not path:
            return
        self.cfg["root"] = path
        config.save_config(self.cfg)
        if self.engine:
            self.engine.set_root(path)
        self._refresh_chips()
        self.folder_card.set_root(Path(path))
        self.settings.set_root_label(path)
        self.chat.add_system(f"All file operations are now confined to: {path}", "info", card=True)
        self._set_status(self._status_line())
        self.toast("Working folder changed", "ok")

    def _pick_root(self) -> None:
        d = filedialog.askdirectory(initialdir=str(self.engine.root) if self.engine else "~",
                                    title="Choose the folder THANS may manage")
        if d:
            self._apply_root(d)

    def _open_root(self) -> None:
        """Reveal the working folder in the OS file manager."""
        if not self.engine:
            return
        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer", str(self.engine.root)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(self.engine.root)])
            else:
                subprocess.Popen(["xdg-open", str(self.engine.root)])
        except Exception:
            self.toast("Could not open a file manager", "warn")

    def _download_models(self) -> None:
        """Fetch the offline models in the background, streaming real progress."""
        if self._downloading:
            self.toast("A download is already running")
            return
        if not messagebox.askyesno(APP_NAME,
                                   "Download the offline models now?\n\n"
                                   "• speech recognition (Vosk)  ≈ 40 MB\n"
                                   "• optional LLM (Qwen2.5 0.5B) ≈ 408 MB\n\n"
                                   "THANS is 100% offline afterwards."):
            return
        self._downloading = True
        self.settings.set_download("starting…", 0.0)
        self.toast("Downloading models — progress in Settings")
        if not self.settings.is_open:
            self.open_settings()
        threading.Thread(target=self._download_worker, daemon=True).start()

    def _download_worker(self) -> None:
        """Run scripts/download_models.py and parse its progress percentages."""
        script = config.app_root() / "scripts" / "download_models.py"
        frozen = bool(getattr(sys, "frozen", False))
        rc = 1
        try:
            if frozen or not script.exists():
                # bundled build: run it in-process (it is stdlib-only)
                import importlib.util
                spec = importlib.util.spec_from_file_location("thans_dl", script)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                rc = int(mod.main([]) or 0)
            else:
                proc = subprocess.Popen([sys.executable, str(script)],
                                        cwd=str(script.parent.parent), text=True,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, bufsize=1)
                assert proc.stdout is not None
                last = 0.0
                for raw in proc.stdout:
                    for piece in raw.replace("\r", "\n").split("\n"):
                        pct = self._percent(piece)
                        if pct is not None:
                            overall = min(0.999, last + pct / 100.0 * 0.5)
                            if pct >= 99.0:
                                last = min(1.0, last + 0.5)
                                overall = last
                            self._q.put(("models_progress", overall,
                                         piece.strip()[:60]))
                rc = proc.wait()
        except SystemExit as e:
            rc = int(getattr(e, "code", 0) or 0)
        except Exception as e:                                  # noqa: BLE001
            self._q.put(("models_error", str(e)))
            return
        self._q.put(("models_done", rc))

    @staticmethod
    def _percent(line: str) -> float | None:
        import re
        m = re.search(r"(\d{1,3}(?:\.\d+)?)\s*%", line or "")
        if not m:
            return None
        try:
            return float(m.group(1))
        except ValueError:
            return None

    def _models_finished(self, rc: int) -> None:
        self._downloading = False
        self.model_status = model_manager.status(self.cfg)
        self._refresh_chips()
        if rc == 0:
            self.settings.set_download("done — models ready", 1.0)
            self.toast("Models ready — voice input is live", "ok")
            if not self.text_only:
                self.stt = VoiceSTT()
            self.chat.add_system("Speech recognition is ready — press the mic (F2) "
                                 "and talk to THANS.", "ok")
        else:
            self.settings.set_download("finished with errors — see the terminal", 0.0)
            self.toast("Model download had errors", "warn")

    # =====================================================================
    # chrome updates
    # =====================================================================
    def _refresh_chips(self) -> None:
        if not self._boot_done:
            return
        s = self.model_status or model_manager.status(self.cfg)
        root = self.engine.root if self.engine else Path(self.cfg["root"])
        self.chip_root.set(text=logic.truncate(root.name or str(root), 16), state="ready")
        stt_ok = bool(s.get("stt") and s.get("stt_deps"))
        self.chip_voice.set(text="voice ready" if stt_ok else "voice: no model",
                            state="ok" if stt_ok else "missing")
        llm_ready = bool(s.get("llm") and s.get("llm_enabled"))
        if llm_ready:
            self.chip_llm.set(text="llm on", state="ok")
        elif s.get("llm"):
            self.chip_llm.set(text="llm off", state="warn")
        else:
            self.chip_llm.set(text="llm none", state="off")
        self.voice_card.sw_speak.set(bool(self.cfg.get("tts")))

    def _status_line(self) -> str:
        if not self.engine:
            return "starting…"
        cur = self.engine.current
        try:
            rel = cur.relative_to(self.engine.root).as_posix() or "."
        except ValueError:
            rel = str(cur)
        return f"in {rel}  ·  root {logic.truncate(str(self.engine.root), 46)}"

    def _set_status(self, text: str) -> None:
        self.status_lbl.configure(text=text)

    def _first_run_tour(self) -> None:
        """One-time, dismissible walkthrough of the four corners of the app."""
        self.toast("Tip: press F1 for the command sheet, F2 to talk", "info", 4200)
        self.toast("F5 rescans the folder · Ctrl+, opens settings", "info", 4200)
        self.chat.add_system(
            "New here? Start with one of the suggestions above the input box, "
            "or press F1 to browse all "
            f"{len(COMMAND_REFERENCE)} command families.", "info", card=True)
        self.cfg["onboarded"] = True
        config.save_config(self.cfg)

    def _welcome(self) -> None:
        s = self.model_status
        self.chat.add_reply(
            f"{logic.greeting()}! I manage files & folders inside your working folder — "
            f"by the sound of your voice or by typing. Say 'help' any time (F1), "
            f"or press the mic (F2) and just talk.",
            ok=True, source="welcome", stream=True)
        if not (s.get("stt") and s.get("stt_deps")) and not self.text_only:
            self.chat.add_system("Voice input needs the one-time speech model (~40 MB, still "
                                 "fully offline afterwards) — press the ↓ button to fetch it. "
                                 "Everything works by typing in the meantime.", "warn")
        if not self.cfg.get("onboarded"):
            self._first_run_tour()
        self._set_status(self._status_line())

    def toast(self, text: str, kind: str = "info", ms: int = 2600) -> None:
        if self.toaster:
            self.toaster.show(text, kind, ms)

    def clear_chat(self) -> None:
        self.chat.clear()
        self.chat.add_system("Chat cleared — the transcript lives only on this screen.", "info")
        self.toast("Chat cleared")

    def hide_hero(self) -> None:
        if getattr(self, "_hero_alive", True):
            self._hero_alive = False
            try:
                self.hero.dismiss()
            except tk.TclError:
                pass

    def _apply_responsive(self) -> None:
        """Hide the dashboard column when the window gets narrow."""
        if not hasattr(self, "side"):
            return
        w = self.root.winfo_width()
        if w <= 1:                                  # not mapped yet — use the plan
            try:
                w = int(self.root.geometry().split("x")[0].split("+")[0])
            except Exception:
                w = 1060
        wide = w >= 900
        if wide and not self._side_visible:
            self.side.grid(row=0, column=1, sticky="nsew", padx=(T.PAD, 0))
            self._side_visible = True
        elif not wide and self._side_visible:
            self.side.grid_forget()
            self._side_visible = False

    # =====================================================================
    # main loop
    # =====================================================================
    def _tick(self) -> None:
        """One frame of the app: animations, worker queue, dashboard."""
        now = time.time()
        dt = min(0.1, max(0.001, now - self._last_dt))
        self._last_dt = now
        self._tick_once(dt)
        self.root.after(T.TICK_MS, self._tick)

    def _tick_once(self, dt: float) -> None:
        """The frame body, separated so it can be driven by tests."""
        if self.anim is not None:
            self.anim.tick(dt)
        self._drain_queue()
        try:
            self.folder_card.poll()
            self.folder_card.tick(dt)
        except Exception:
            pass

    def _drain_queue(self) -> None:
        try:
            while True:
                item = self._q.get_nowait()
                kind = item[0]
                if kind == "reply":
                    self._on_reply(item[1], item[2])
                elif kind == "crash":
                    self._set_busy(False)
                    self.chat.add_reply("Something went wrong inside THANS:\n\n" + item[1],
                                        ok=False, source="internal error", card=True)
                    self.toast("Internal error — see the transcript", "error")
                elif kind == "mic":
                    self._set_mic(item[1])
                elif kind == "mic_state":
                    self.voice_card.set_state(item[1], self.mic_on)
                elif kind == "voice":
                    self.submit(item[1])
                elif kind == "models_progress":
                    self.settings.set_download(f"{item[2]}", float(item[1]))
                elif kind == "models_done":
                    self._models_finished(item[1])
                elif kind == "models_error":
                    self._downloading = False
                    self.settings.set_download(f"error: {item[1]}", 0.0)
                    self.toast("Model download failed", "error")
        except queue.Empty:
            pass

    # =====================================================================
    # lifecycle
    # =====================================================================
    def _on_close(self) -> None:
        try:
            self.cfg["window"] = self.root.geometry()
            config.save_config(self.cfg)
        except Exception:
            pass
        for closer in (lambda: self.stt.stop() if self.stt else None,
                       lambda: self.speaker.stop() if self.speaker else None):
            try:
                closer()
            except Exception:
                pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def run(self) -> None:
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()


def main(argv: list[str] | None = None) -> int:
    """Convenience entry point mirroring ``python -m thans``."""
    from .__main__ import main as cli_main
    return cli_main(argv)

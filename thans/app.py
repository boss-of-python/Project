"""THANS main window — minimalistic, animated desktop UI (Windows / Linux / macOS).

Architecture & UX highlights:
  * Curated Dark & Light themes with smooth cross-fade color transitions
  * 60fps Sonic Visualizer canvas (multi-ribbon sine waves + breathing orb)
  * Interactive Breadcrumb bar (`🏠 root › folder › sub`) + `⬆ Up` + `♻️ Trash` badge
  * Split-pane Live File Workspace Inspector with instant filter, smart icons,
    double-click navigation, context actions, and emerald diff highlight pulses
  * Real-time Live Intent Preview pill as you type + `Tab` autocomplete
  * One-click Quick-Action Chips (`List`, `Folder`, `File`, `Organize`, `Find`, `Undo`, `Help`)
  * Progressive streaming text reveal & slide-in toast notifications
"""
from __future__ import annotations

from datetime import datetime
import queue
import subprocess
import sys
import threading
import traceback
from pathlib import Path
from typing import Optional

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import APP_NAME, APP_TAGLINE, __version__, animations, config, model_manager, platforms, ui_helpers
from .engine import Engine
from .stt import VoiceSTT
from .tts import Speaker

# Platform-tuned typography
UI_FONT_FAMILY = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"
MONO_FAMILY = "Consolas" if sys.platform == "win32" else "DejaVu Sans Mono"

FONT_TITLE = (UI_FONT_FAMILY, 14, "bold")
FONT_SUB = (UI_FONT_FAMILY, 9)
FONT_UI = (UI_FONT_FAMILY, 9)
FONT_UI_BOLD = (UI_FONT_FAMILY, 9, "bold")
FONT_CHIP = (UI_FONT_FAMILY, 8, "bold")
FONT_MONO = (MONO_FAMILY, 10)
FONT_MONO_S = (MONO_FAMILY, 9)
FONT_MONO_B = (MONO_FAMILY, 9, "bold")


class ThansApp:
    """Minimalistic, animated desktop assistant window."""

    def __init__(self, cfg: dict | None = None, text_only: bool = False):
        self.cfg = dict(config.DEFAULTS)
        if cfg:
            self.cfg.update(cfg)
        else:
            self.cfg.update(config.load_config())

        self.theme_name: str = str(self.cfg.get("theme", "dark"))
        if self.theme_name not in animations.THEMES:
            self.theme_name = "dark"
        self.pal: dict[str, str] = animations.get_theme(self.theme_name)

        self.animations_on: bool = bool(self.cfg.get("animations", True))
        self.sidebar_open: bool = bool(self.cfg.get("sidebar", True))

        self.engine = Engine(self.cfg["root"], self.cfg)
        self.stt = VoiceSTT()
        self.speaker = Speaker(self.cfg.get("tts", True), int(self.cfg.get("tts_rate", 185)))

        self.mic_on = False
        self.busy = False
        self._downloading = False
        self._closing = False

        # Sonic visualizer & animation state
        self.sonic_state = "idle"      # idle | listening | thinking | speaking | success | error
        self.sonic_phase = 0.0
        self.sonic_level = 0.0
        self._flash_ticks = 0
        self._toast_ticks = 0

        # Workspace snapshot & diff highlight animation state
        self.snapshot: Optional[ui_helpers.DirSnapshot] = None
        self._highlight_step = 0
        self._highlight_names: set[str] = set()
        self._selected_entry: Optional[ui_helpers.DirEntry] = None

        # Command history
        self.history: list[str] = []
        self._hist_i: int | None = None
        self._q: "queue.Queue" = queue.Queue()
        self.text_only = text_only

        # Root window
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} — {APP_TAGLINE}")
        self.root.geometry("1060x660")
        self.root.minsize(760, 480)
        self.root.configure(bg=self.pal["bg"])

        self._style()
        self._build()
        self._bind_shortcuts()
        self._refresh_chips()
        self._refresh_workspace(animate_diff=False)
        self._update_intent_preview()
        self._welcome()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(60, self._poll)
        self.root.after(40, self._animate_tick)

    # ------------------------------------------------------------------ styling
    def _style(self) -> None:
        p = self.pal
        st = ttk.Style(self.root)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure(".", background=p["panel"], foreground=p["fg"], font=FONT_UI)
        st.configure(
            "TButton",
            background=p["panel2"],
            foreground=p["fg"],
            padding=(10, 6),
            borderwidth=0,
            focusthickness=0,
            font=FONT_UI,
        )
        st.map("TButton", background=[("active", p["panel_hover"])])
        st.configure(
            "Accent.TButton",
            background=p["accent"],
            foreground="#ffffff",
            padding=(14, 7),
            borderwidth=0,
            font=FONT_UI_BOLD,
        )
        st.map("Accent.TButton", background=[("active", p["accent_hover"])])
        st.configure(
            "TEntry",
            fieldbackground=p["panel2"],
            foreground=p["fg"],
            insertcolor=p["fg"],
            borderwidth=0,
            padding=6,
        )

    # ------------------------------------------------------------------ layout
    def _build(self) -> None:
        p = self.pal

        # ===================== 1. HEADER BAR =====================
        self.head = tk.Frame(self.root, bg=p["bg"])
        self.head.pack(fill="x", padx=16, pady=(12, 4))

        brand = tk.Frame(self.head, bg=p["bg"])
        brand.pack(side="left")
        self.lbl_title = tk.Label(brand, text=APP_NAME, font=FONT_TITLE, bg=p["bg"], fg=p["fg"])
        self.lbl_title.pack(side="left")
        self.lbl_sub = tk.Label(
            brand,
            text=f"  offline assistant · v{__version__}",
            font=FONT_SUB,
            bg=p["bg"],
            fg=p["dim"],
        )
        self.lbl_sub.pack(side="left", pady=(4, 0))

        # Sonic Visualizer Canvas (multi-ribbon sine wave + breathing orb)
        self.sonic_canvas = tk.Canvas(
            self.head,
            width=190,
            height=30,
            bg=p["panel"],
            highlightthickness=1,
            highlightbackground=p["border"],
            bd=0,
        )
        self.sonic_canvas.pack(side="left", padx=(16, 8))
        self._draw_sonic_canvas()

        # Right-side status chips & quick controls
        self.cframe = tk.Frame(self.head, bg=p["bg"])
        self.cframe.pack(side="right")

        self.chips: dict[str, tk.Label] = {}
        for key, label in (
            ("root", "📂 …"),
            ("stt", "STT —"),
            ("tts", "TTS —"),
            ("llm", "LLM —"),
            ("trash", "♻️ 0"),
        ):
            lbl = tk.Label(
                self.cframe,
                text=label,
                font=FONT_CHIP,
                bg=p["panel"],
                fg=p["dim"],
                padx=8,
                pady=4,
                cursor="hand2" if key in ("root", "trash") else "arrow",
            )
            lbl.pack(side="left", padx=2)
            self.chips[key] = lbl

        self.chips["root"].bind("<Button-1>", lambda e: self._pick_root())
        self.chips["trash"].bind("<Button-1>", lambda e: self._submit("undo"))

        self.btn_theme = tk.Button(
            self.cframe,
            text="☀️" if self.theme_name == "dark" else "🌙",
            font=FONT_UI,
            bg=p["panel2"],
            fg=p["fg"],
            bd=0,
            padx=8,
            pady=3,
            cursor="hand2",
            command=self.toggle_theme,
        )
        self.btn_theme.pack(side="left", padx=(6, 2))

        self.btn_sidebar = tk.Button(
            self.cframe,
            text="◫ Files",
            font=FONT_CHIP,
            bg=p["accent_soft"] if self.sidebar_open else p["panel2"],
            fg=p["accent"] if self.sidebar_open else p["fg"],
            bd=0,
            padx=8,
            pady=4,
            cursor="hand2",
            command=self.toggle_sidebar,
        )
        self.btn_sidebar.pack(side="left", padx=2)

        # ===================== 2. BREADCRUMB BAR =====================
        self.nav_bar = tk.Frame(
            self.root,
            bg=p["panel"],
            highlightthickness=1,
            highlightbackground=p["border"],
        )
        self.nav_bar.pack(fill="x", padx=16, pady=(2, 6))

        self.btn_up = tk.Button(
            self.nav_bar,
            text="⬆ Up",
            font=FONT_CHIP,
            bg=p["panel2"],
            fg=p["fg"],
            bd=0,
            padx=8,
            pady=3,
            cursor="hand2",
            command=lambda: self._submit("go back"),
        )
        self.btn_up.pack(side="left", padx=(6, 4), pady=4)

        self.crumb_frame = tk.Frame(self.nav_bar, bg=p["panel"])
        self.crumb_frame.pack(side="left", fill="x", expand=True, padx=4)

        self.lbl_counts = tk.Label(
            self.nav_bar,
            text="",
            font=FONT_SUB,
            bg=p["panel"],
            fg=p["dim"],
            padx=8,
        )
        self.lbl_counts.pack(side="right", pady=4)

        # ===================== 3. MAIN SPLIT BODY =====================
        self.body = tk.Frame(self.root, bg=p["bg"])
        self.body.pack(fill="both", expand=True, padx=16, pady=2)

        # Left pane: Toast Banner + Chat Stream
        self.chat_pane = tk.Frame(
            self.body,
            bg=p["panel"],
            highlightthickness=1,
            highlightbackground=p["border"],
        )
        self.chat_pane.pack(side="left", fill="both", expand=True)

        self.toast_bar = tk.Label(
            self.chat_pane,
            text="",
            font=FONT_UI_BOLD,
            bg=p["accent_soft"],
            fg=p["accent"],
            anchor="w",
            padx=12,
            pady=5,
        )
        # toast_bar is packed dynamically when active

        self.chat = tk.Text(
            self.chat_pane,
            bg=p["panel"],
            fg=p["fg"],
            insertbackground=p["fg"],
            font=FONT_MONO,
            relief="flat",
            wrap="word",
            state="disabled",
            padx=14,
            pady=12,
            spacing1=3,
            spacing3=3,
            highlightthickness=0,
        )
        self._configure_chat_tags()
        self.chat.pack(fill="both", expand=True)

        # Right pane: Collapsible Live File Workspace Inspector
        self.sidebar = tk.Frame(
            self.body,
            bg=p["panel"],
            width=295,
            highlightthickness=1,
            highlightbackground=p["border"],
        )
        if self.sidebar_open:
            self.sidebar.pack(side="right", fill="y", padx=(10, 0))
            self.sidebar.pack_propagate(False)

        self._build_sidebar()

        # ===================== 4. LIVE INTENT PREVIEW & QUICK CHIPS =====================
        self.preview_bar = tk.Frame(
            self.root,
            bg=p["panel"],
            highlightthickness=1,
            highlightbackground=p["border"],
        )
        self.preview_bar.pack(fill="x", padx=16, pady=(6, 2))

        self.lbl_preview_icon = tk.Label(
            self.preview_bar,
            text="✨",
            font=FONT_UI_BOLD,
            bg=p["panel"],
            fg=p["accent"],
            padx=8,
            pady=4,
        )
        self.lbl_preview_icon.pack(side="left")

        self.lbl_preview_title = tk.Label(
            self.preview_bar,
            text="Ready for voice or text command",
            font=FONT_UI_BOLD,
            bg=p["panel"],
            fg=p["fg"],
            anchor="w",
        )
        self.lbl_preview_title.pack(side="left")

        self.lbl_preview_sub = tk.Label(
            self.preview_bar,
            text="",
            font=FONT_SUB,
            bg=p["panel"],
            fg=p["dim"],
            anchor="w",
            padx=8,
        )
        self.lbl_preview_sub.pack(side="left", fill="x", expand=True)

        # Quick-Action Chips Row
        self.chips_row = tk.Frame(self.root, bg=p["bg"])
        self.chips_row.pack(fill="x", padx=16, pady=(2, 3))
        self.quick_buttons: list[tk.Button] = []
        for qc in ui_helpers.QUICK_CHIPS:
            b = tk.Button(
                self.chips_row,
                text=qc.label,
                font=FONT_CHIP,
                bg=p["panel2"],
                fg=p["fg_secondary"],
                activebackground=p["panel_hover"],
                activeforeground=p["fg"],
                bd=0,
                padx=9,
                pady=3,
                cursor="hand2",
                command=lambda c=qc: self._on_quick_chip(c),
            )
            b.pack(side="left", padx=(0, 5))
            self.quick_buttons.append(b)

        # ===================== 5. INPUT DOCK =====================
        self.input_row = tk.Frame(self.root, bg=p["bg"])
        self.input_row.pack(fill="x", padx=16, pady=(2, 6))

        self.entry = tk.Entry(
            self.input_row,
            font=FONT_MONO,
            bg=p["panel2"],
            fg=p["fg"],
            insertbackground=p["fg"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=p["border"],
            highlightcolor=p["accent"],
        )
        self.entry.pack(side="left", fill="x", expand=True, ipady=8, padx=(0, 8))
        self.entry.bind("<Return>", lambda e: self._on_enter())
        self.entry.bind("<Up>", lambda e: self._on_hist(-1))
        self.entry.bind("<Down>", lambda e: self._on_hist(1))
        self.entry.bind("<KeyRelease>", lambda e: self._update_intent_preview())
        self.entry.bind("<Tab>", self._on_tab_complete)
        self.entry.focus_set()

        self.btn_send = ttk.Button(
            self.input_row,
            text="Send ↵",
            style="Accent.TButton",
            command=self._on_enter,
        )
        self.btn_send.pack(side="left", padx=(0, 6))

        if not self.text_only:
            self.btn_mic = tk.Button(
                self.input_row,
                text="🎤",
                font=(UI_FONT_FAMILY, 12),
                bd=0,
                bg=p["panel2"],
                fg=p["fg"],
                activebackground=p["panel_hover"],
                activeforeground=p["fg"],
                width=4,
                cursor="hand2",
                command=self._toggle_mic,
            )
            self.btn_mic.pack(side="left", padx=(0, 6))

        ttk.Button(self.input_row, text="📂 Root", command=self._pick_root).pack(side="left", padx=(0, 6))
        self.btn_dl = ttk.Button(self.input_row, text="⬇ Models", command=self._download_models)
        self.btn_dl.pack(side="left", padx=(0, 6))
        ttk.Button(self.input_row, text="⚙ Settings", command=self._settings).pack(side="left")

        # ===================== 6. STATUS BAR =====================
        self.status_bar = tk.Frame(self.root, bg=p["panel"])
        self.status_bar.pack(fill="x", side="bottom")
        self.status = tk.Label(
            self.status_bar,
            text="ready",
            bg=p["panel"],
            fg=p["dim"],
            font=FONT_SUB,
            anchor="w",
        )
        self.status.pack(side="left", fill="x", expand=True, padx=12, pady=4)
        self.lbl_footer = tk.Label(
            self.status_bar,
            text=f"{APP_NAME} v{__version__} · 100% offline · Tab=complete · Ctrl+Z=undo",
            bg=p["panel"],
            fg=p["dim"],
            font=FONT_SUB,
        )
        self.lbl_footer.pack(side="right", padx=12, pady=4)

    def _build_sidebar(self) -> None:
        p = self.pal
        sh = tk.Frame(self.sidebar, bg=p["panel"])
        sh.pack(fill="x", padx=10, pady=(8, 4))
        self.lbl_side_title = tk.Label(
            sh,
            text="LIVE WORKSPACE",
            font=FONT_CHIP,
            bg=p["panel"],
            fg=p["dim"],
        )
        self.lbl_side_title.pack(side="left")
        self.btn_refresh = tk.Button(
            sh,
            text="↻",
            font=FONT_UI_BOLD,
            bg=p["panel"],
            fg=p["dim"],
            bd=0,
            cursor="hand2",
            command=lambda: self._refresh_workspace(animate_diff=False),
        )
        self.btn_refresh.pack(side="right")

        # Instant filter bar inside sidebar
        ff = tk.Frame(self.sidebar, bg=p["panel"])
        ff.pack(fill="x", padx=10, pady=(0, 6))
        self.filter_var = tk.StringVar(value="")
        self.filter_entry = tk.Entry(
            ff,
            textvariable=self.filter_var,
            font=FONT_MONO_S,
            bg=p["panel2"],
            fg=p["fg"],
            insertbackground=p["fg"],
            relief="flat",
        )
        self.filter_entry.pack(fill="x", ipady=4)
        self.filter_entry.bind("<KeyRelease>", lambda e: self._render_file_list())

        # File listbox
        self.file_list = tk.Listbox(
            self.sidebar,
            bg=p["panel"],
            fg=p["fg"],
            selectbackground=p["accent_soft"],
            selectforeground=p["accent"],
            font=FONT_MONO_S,
            relief="flat",
            bd=0,
            highlightthickness=0,
            activestyle="none",
        )
        self.file_list.pack(fill="both", expand=True, padx=8, pady=2)
        self.file_list.bind("<<ListboxSelect>>", self._on_file_select)
        self.file_list.bind("<Double-Button-1>", self._on_file_double_click)

        # Quick Context Action Bar for selected item
        self.side_actions = tk.Frame(self.sidebar, bg=p["panel2"])
        self.side_actions.pack(fill="x", side="bottom", padx=8, pady=8)
        for lbl, act in (
            ("↗ Open", "open"),
            ("✏️ Rename", "rename"),
            ("✨ Organize", "organize"),
            ("♻️ Trash", "delete"),
        ):
            tk.Button(
                self.side_actions,
                text=lbl,
                font=FONT_CHIP,
                bg=p["panel2"],
                fg=p["fg_secondary"],
                bd=0,
                padx=5,
                pady=4,
                cursor="hand2",
                command=lambda a=act: self._on_sidebar_action(a),
            ).pack(side="left", expand=True, fill="x")

    def _configure_chat_tags(self) -> None:
        p = self.pal
        self.chat.tag_configure("you_badge", foreground=p["accent"], font=FONT_MONO_B)
        self.chat.tag_configure("you", foreground=p["user_msg"], font=FONT_MONO)
        self.chat.tag_configure("thans_badge", foreground=p["ok"], font=FONT_MONO_B)
        self.chat.tag_configure("thans", foreground=p["asst_msg"], font=FONT_MONO)
        self.chat.tag_configure("sys", foreground=p["dim"], font=FONT_MONO_S)
        self.chat.tag_configure("err", foreground=p["err"], font=FONT_MONO_S)
        self.chat.tag_configure("cmd", foreground=p["cmd_pill"], font=FONT_MONO_S)

    def _bind_shortcuts(self) -> None:
        self.root.bind("<Control-k>", lambda e: self.entry.focus_set())
        self.root.bind("<Control-z>", lambda e: self._submit("undo"))
        self.root.bind("<Control-l>", lambda e: self.clear_chat())
        self.root.bind("<Control-b>", lambda e: self.toggle_sidebar())
        self.root.bind("<Control-t>", lambda e: self.toggle_theme())
        if not self.text_only:
            self.root.bind("<F2>", lambda e: self._toggle_mic())

    # ------------------------------------------------------------ welcome
    def _welcome(self) -> None:
        s = model_manager.status(self.cfg)
        self._post(
            "sys",
            f"Welcome to {APP_NAME} — type or speak a file command, or click any quick chip below. "
            f"Say 'help' for the full command reference.",
            "★ ",
        )
        if not self.text_only and not (s["stt"] and s["stt_deps"]):
            self._post(
                "sys",
                "Voice input needs the STT model: click '⬇ Models' once (~40 MB download), "
                "or just use text commands & quick chips.",
                "⚠ ",
            )
        self._set_status(f"working folder: {self.engine.current}")

    # ------------------------------------------------------------ animations
    def _draw_sonic_canvas(self) -> None:
        try:
            self.sonic_canvas.delete("all")
            w = int(self.sonic_canvas.cget("width") or 190)
            h = int(self.sonic_canvas.cget("height") or 30)
            geom = animations.compute_sonic_waves(
                w, h, phase=self.sonic_phase, state=self.sonic_state, level=self.sonic_level
            )
            orb = geom["orb"]
            r = orb["r"]
            gr = orb["glow_r"]
            cx, cy = orb["cx"], orb["cy"]
            glow_col = animations.lerp_color(self.pal["panel"], orb["color"], 0.32)
            self.sonic_canvas.create_oval(
                cx - gr, cy - gr, cx + gr, cy + gr, fill=glow_col, outline=""
            )
            for rib in reversed(geom["ribbons"]):
                self.sonic_canvas.create_line(
                    *rib["coords"], fill=rib["color"], width=rib["width"], smooth=True
                )
            self.sonic_canvas.create_oval(
                cx - r, cy - r, cx + r, cy + r, fill=orb["color"], outline=""
            )
        except Exception:
            pass

    def _animate_tick(self) -> None:
        if self._closing:
            return
        if self.animations_on:
            speed = 0.24 if self.sonic_state != "idle" else 0.09
            self.sonic_phase = (self.sonic_phase + speed) % (62.83)
            if self._flash_ticks > 0:
                self._flash_ticks -= 1
                if self._flash_ticks == 0 and not self.mic_on and not self.busy:
                    self.sonic_state = "idle"
            self._draw_sonic_canvas()

            # File diff emerald highlight pulse decay
            if self._highlight_step > 0:
                self._highlight_step -= 1
                self._apply_list_highlights()

        # Toast auto-dismiss
        if self._toast_ticks > 0:
            self._toast_ticks -= 1
            if self._toast_ticks == 0:
                try:
                    self.toast_bar.pack_forget()
                except Exception:
                    pass

        self.root.after(45, self._animate_tick)

    def show_toast(self, text: str, kind: str = "info") -> None:
        p = self.pal
        bg_map = {
            "info": (p["accent_soft"], p["accent"]),
            "ok": (p["ok_soft"], p["ok"]),
            "warn": (p["warn_soft"], p["warn"]),
            "err": (p["err_soft"], p["err"]),
        }
        bg_c, fg_c = bg_map.get(kind, bg_map["info"])
        self.toast_bar.config(text=text, bg=bg_c, fg=fg_c)
        try:
            self.toast_bar.pack(fill="x", side="top", before=self.chat)
        except Exception:
            self.toast_bar.pack(fill="x", side="top")
        self._toast_ticks = 48  # ~2.2 seconds

    # ------------------------------------------------------------ config
    def _safe_save(self) -> None:
        """Persist settings; a read-only config dir must never crash the UI."""
        try:
            config.save_config(self.cfg)
        except OSError as e:
            try:
                self.show_toast(f"⚠ Could not save settings: {e}", "warn")
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------ theme & sidebar
    def toggle_theme(self) -> None:
        old_pal = dict(self.pal)
        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        self.cfg["theme"] = self.theme_name
        self._safe_save()
        target_pal = animations.get_theme(self.theme_name)

        if not self.animations_on:
            self.pal = target_pal
            self._apply_palette()
            return

        # Smooth 6-step cross-fade transition
        steps = 6

        def step_fn(i: int) -> None:
            if self._closing:
                return
            try:
                t = animations.ease_in_out_sine(i / float(steps))
                blended = {
                    k: animations.lerp_color(old_pal[k], target_pal[k], t)
                    for k in target_pal
                }
                self.pal = blended
                self._apply_palette()
                if i < steps:
                    self.root.after(22, lambda: step_fn(i + 1))
            except Exception:  # noqa: BLE001 — window may be mid-destroy
                return

        step_fn(1)
        self.show_toast(f"Switched to {self.theme_name.title()} theme", "info")

    def _apply_palette(self) -> None:
        p = self.pal
        self._style()
        self.root.configure(bg=p["bg"])
        self.head.configure(bg=p["bg"])
        self.lbl_title.configure(bg=p["bg"], fg=p["fg"])
        self.lbl_sub.configure(bg=p["bg"], fg=p["dim"])
        self.cframe.configure(bg=p["bg"])
        self.sonic_canvas.configure(bg=p["panel"], highlightbackground=p["border"])
        self.btn_theme.configure(
            text="☀️" if self.theme_name == "dark" else "🌙",
            bg=p["panel2"],
            fg=p["fg"],
        )
        self.btn_sidebar.configure(
            bg=p["accent_soft"] if self.sidebar_open else p["panel2"],
            fg=p["accent"] if self.sidebar_open else p["fg"],
        )
        self.nav_bar.configure(bg=p["panel"], highlightbackground=p["border"])
        self.btn_up.configure(bg=p["panel2"], fg=p["fg"] if (self.snapshot and self.snapshot.can_go_up) else p["dim"])
        self.crumb_frame.configure(bg=p["panel"])
        self.lbl_counts.configure(bg=p["panel"], fg=p["dim"])
        self.body.configure(bg=p["bg"])
        self.chat_pane.configure(bg=p["panel"], highlightbackground=p["border"])
        self.chat.configure(bg=p["panel"], fg=p["fg"], insertbackground=p["fg"])
        self._configure_chat_tags()
        self.sidebar.configure(bg=p["panel"], highlightbackground=p["border"])
        self.lbl_side_title.configure(bg=p["panel"], fg=p["dim"])
        self.btn_refresh.configure(bg=p["panel"], fg=p["dim"])
        self.filter_entry.configure(bg=p["panel2"], fg=p["fg"], insertbackground=p["fg"])
        self.file_list.configure(
            bg=p["panel"],
            fg=p["fg"],
            selectbackground=p["accent_soft"],
            selectforeground=p["accent"],
        )
        self.side_actions.configure(bg=p["panel2"])
        self.preview_bar.configure(bg=p["panel"], highlightbackground=p["border"])
        self.lbl_preview_icon.configure(bg=p["panel"])
        self.lbl_preview_title.configure(bg=p["panel"], fg=p["fg"])
        self.lbl_preview_sub.configure(bg=p["panel"], fg=p["dim"])
        self.chips_row.configure(bg=p["bg"])
        for b in self.quick_buttons:
            b.configure(bg=p["panel2"], fg=p["fg_secondary"], activebackground=p["panel_hover"])
        self.input_row.configure(bg=p["bg"])
        self.entry.configure(
            bg=p["panel2"],
            fg=p["fg"],
            insertbackground=p["fg"],
            highlightbackground=p["border"],
            highlightcolor=p["accent"],
        )
        if hasattr(self, "btn_mic"):
            self.btn_mic.configure(bg=p["err"] if self.mic_on else p["panel2"], fg=p["fg"])
        self.status_bar.configure(bg=p["panel"])
        self.status.configure(bg=p["panel"], fg=p["dim"])
        self.lbl_footer.configure(bg=p["panel"], fg=p["dim"])
        self._refresh_chips()
        self._render_breadcrumbs()
        self._draw_sonic_canvas()

    def toggle_sidebar(self) -> None:
        self.sidebar_open = not self.sidebar_open
        self.cfg["sidebar"] = self.sidebar_open
        self._safe_save()
        if self.sidebar_open:
            self.sidebar.pack(side="right", fill="y", padx=(10, 0))
            self.sidebar.pack_propagate(False)
            self._refresh_workspace(animate_diff=False)
        else:
            self.sidebar.pack_forget()
        self.btn_sidebar.configure(
            bg=self.pal["accent_soft"] if self.sidebar_open else self.pal["panel2"],
            fg=self.pal["accent"] if self.sidebar_open else self.pal["fg"],
        )

    # ------------------------------------------------------------ workspace & breadcrumbs
    def _refresh_workspace(self, animate_diff: bool = True) -> None:
        prev = self.snapshot if animate_diff else None
        q = self.filter_var.get() if hasattr(self, "filter_var") else ""
        self.snapshot = ui_helpers.dir_snapshot(self.engine.root, self.engine.current, prev=prev, filter_query=q)
        self._render_breadcrumbs()
        self._render_file_list()
        self._refresh_chips()

        if animate_diff and self.snapshot.changed_names:
            self._highlight_names = set(self.snapshot.changed_names)
            self._highlight_step = 18
            self._apply_list_highlights()

    def _render_breadcrumbs(self) -> None:
        p = self.pal
        for child in list(self.crumb_frame.winfo_children()):
            child.destroy()

        if not self.snapshot:
            return

        self.btn_up.configure(
            state="normal" if self.snapshot.can_go_up else "disabled",
            fg=p["fg"] if self.snapshot.can_go_up else p["dim"],
        )
        for idx, (label, target) in enumerate(self.snapshot.breadcrumbs):
            if idx > 0:
                tk.Label(self.crumb_frame, text="›", font=FONT_SUB, bg=p["panel"], fg=p["dim"]).pack(
                    side="left", padx=2
                )
            is_last = idx == len(self.snapshot.breadcrumbs) - 1
            btn = tk.Button(
                self.crumb_frame,
                text=label,
                font=FONT_UI_BOLD if is_last else FONT_UI,
                bg=p["accent_soft"] if is_last else p["panel"],
                fg=p["accent"] if is_last else p["fg_secondary"],
                bd=0,
                padx=6,
                pady=2,
                cursor="hand2",
                command=lambda t=target: self._submit(f"go to {t}" if t != "~" else "cd"),
            )
            btn.pack(side="left", padx=1)

        self.lbl_counts.configure(
            text=f"{self.snapshot.folder_count} folders · {self.snapshot.file_count} files"
        )

    def _render_file_list(self) -> None:
        if not hasattr(self, "file_list"):
            return
        q = self.filter_var.get().strip().lower() if hasattr(self, "filter_var") else ""
        self.file_list.delete(0, "end")
        self._visible_entries: list[ui_helpers.DirEntry] = []

        if not self.snapshot:
            return

        for entry in self.snapshot.entries:
            if q and q not in entry.name.lower():
                continue
            self._visible_entries.append(entry)
            row_txt = f" {entry.icon}  {entry.name:<22}  {entry.size_label}"
            self.file_list.insert("end", row_txt)

        if not self._visible_entries:
            self.file_list.insert("end", "   (no matching items)")

        self._apply_list_highlights()

    def _apply_list_highlights(self) -> None:
        if not hasattr(self, "file_list") or not getattr(self, "_visible_entries", None):
            return
        p = self.pal
        intensity = animations.pulse_intensity(18 - self._highlight_step, 18) if self._highlight_step > 0 else 0.0
        hl_bg = animations.lerp_color(p["panel"], p["ok_soft"], intensity)
        hl_fg = animations.lerp_color(p["fg"], p["ok"], intensity)
        for idx, entry in enumerate(self._visible_entries):
            try:
                if entry.name in self._highlight_names and self._highlight_step > 0:
                    self.file_list.itemconfig(idx, bg=hl_bg, fg=hl_fg)
                else:
                    self.file_list.itemconfig(idx, bg=p["panel"], fg=p["fg"])
            except Exception:
                pass

    def _on_file_select(self, _event=None) -> None:
        try:
            sel = self.file_list.curselection()
            if sel and sel[0] < len(getattr(self, "_visible_entries", [])):
                self._selected_entry = self._visible_entries[sel[0]]
        except Exception:
            self._selected_entry = None

    def _on_file_double_click(self, _event=None) -> None:
        self._on_file_select()
        entry = self._selected_entry
        if not entry:
            return
        if entry.is_dir:
            self._submit(f"go to {entry.name}")
        else:
            self._submit(f"open {entry.name}")

    def _on_sidebar_action(self, action: str) -> None:
        entry = self._selected_entry
        if action == "organize" and not entry:
            self._submit("organize")
            return
        if not entry:
            self.show_toast("Select a file or folder in the sidebar first", "warn")
            return
        if action == "open":
            self._submit(f"go to {entry.name}" if entry.is_dir else f"open {entry.name}")
        elif action == "delete":
            self._submit(f"delete {entry.name}")
        elif action == "organize":
            self._submit(f"organize {entry.name}" if entry.is_dir else "organize")
        elif action == "rename":
            self.entry.delete(0, "end")
            self.entry.insert(0, f"rename {entry.name} to ")
            self.entry.focus_set()
            self._update_intent_preview()

    # ------------------------------------------------------------ live preview & chips
    def _update_intent_preview(self) -> None:
        text = self.entry.get()
        prev = ui_helpers.preview_intent(text, self.engine.current)
        p = self.pal
        color_map = {
            "idle": p["dim"],
            "matched": p["ok"],
            "partial": p["accent"],
            "unknown": p["warn"],
        }
        fg_c = color_map.get(prev.state, p["accent"])
        self.lbl_preview_icon.configure(text=prev.icon, fg=fg_c)
        self.lbl_preview_title.configure(text=prev.title, fg=fg_c if prev.state == "matched" else p["fg"])
        self.lbl_preview_sub.configure(text=f"·  {prev.subtitle}" if prev.subtitle else "")

    def _on_tab_complete(self, _event=None) -> str:
        cur_txt = self.entry.get()
        completed = ui_helpers.autocomplete(cur_txt, self.engine.current)
        if completed != cur_txt:
            self.entry.delete(0, "end")
            self.entry.insert(0, completed)
            self._update_intent_preview()
        return "break"

    def _on_quick_chip(self, chip: ui_helpers.QuickChip) -> None:
        if chip.execute_now:
            self._submit(chip.command)
        else:
            self.entry.delete(0, "end")
            self.entry.insert(0, chip.command)
            self.entry.focus_set()
            self._update_intent_preview()

    # ------------------------------------------------------------ chat api
    def _post(self, kind: str, text: str, prefix: str | None = None, stream: bool = False) -> None:
        self.chat.config(state="normal")
        if prefix:
            badge_tag = "you_badge" if kind == "you" else ("thans_badge" if kind == "thans" else kind)
            self.chat.insert("end", prefix, badge_tag)

        if stream and self.animations_on and len(text) > 28:
            chunks = animations.stream_chunks(text, max_steps=10)
            self.chat.insert("end", chunks[0], kind)
            self.chat.config(state="disabled")
            self.chat.see("end")

            def stream_step(idx: int) -> None:
                if self._closing:
                    return
                self.chat.config(state="normal")
                if idx < len(chunks):
                    self.chat.insert("end", chunks[idx], kind)
                    self.chat.config(state="disabled")
                    self.chat.see("end")
                    self.root.after(14, lambda: stream_step(idx + 1))
                else:
                    self.chat.insert("end", "\n\n", kind)
                    self.chat.config(state="disabled")
                    self.chat.see("end")

            self.root.after(14, lambda: stream_step(1))
            return

        self.chat.insert("end", text + "\n\n", kind)
        self.chat.config(state="disabled")
        self.chat.see("end")

    def clear_chat(self) -> None:
        self.chat.config(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.config(state="disabled")
        self._post("sys", "Conversation cleared.", "· ")

    def _set_status(self, text: str) -> None:
        self.status.config(text=text)

    def _set_mic(self, on: bool) -> None:
        self.mic_on = on
        self.sonic_state = "listening" if on else "idle"
        if not on:
            self.sonic_level = 0.0
        if hasattr(self, "btn_mic"):
            self.btn_mic.config(bg=self.pal["err"] if on else self.pal["panel2"])
            self.btn_mic.config(text="⏹" if on else "🎤")
        self._set_status(
            "🎙 listening — speak a command, then pause…"
            if on
            else f"working folder: {self.engine.current}"
        )

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        if busy:
            self.sonic_state = "thinking"
            self._set_status("⚡ executing…")

    # ------------------------------------------------------------- polling
    def _poll(self) -> None:
        if self._closing:
            return
        try:
            while True:
                item = self._q.get_nowait()
                kind = item[0]
                if kind == "post":
                    stream_flag = bool(item[4]) if len(item) > 4 else False
                    self._post(item[1], item[2], item[3], stream=stream_flag)
                elif kind == "busy":
                    self._set_busy(item[1])
                    if not item[1]:
                        self._set_status(f"working folder: {self.engine.current}")
                elif kind == "after_action":
                    ok_flag, cmd_desc = item[1], item[2]
                    self.sonic_state = "success" if ok_flag else "error"
                    self._flash_ticks = 22
                    self._refresh_workspace(animate_diff=True)
                    if ok_flag and cmd_desc and not cmd_desc.startswith(("list", "help", "search")):
                        self.show_toast(f"✓ {cmd_desc}", "ok")
                elif kind == "chips":
                    self._refresh_chips()
                elif kind == "status":
                    self._set_status(item[1])
                elif kind == "mic":
                    self._set_mic(item[1])
                elif kind == "mic_state":
                    self._set_status(item[1])
                elif kind == "mic_partial":
                    self.lbl_preview_icon.configure(text="🎙", fg=self.pal["err"])
                    self.lbl_preview_title.configure(text=f"Hearing: \"{item[1]}\"")
                elif kind == "mic_level":
                    self.sonic_level = float(item[1])
                elif kind == "voice":
                    self._submit(item[1])
                elif kind == "downloading":
                    self._downloading = item[1]
                    self.btn_dl.config(state="disabled" if item[1] else "normal")
        except queue.Empty:
            pass
        self.root.after(60, self._poll)

    def _refresh_chips(self) -> None:
        p = self.pal
        s = model_manager.status(self.cfg)
        root_name = Path(self.engine.root).name or str(self.engine.root)
        self.chips["root"].config(
            text=f"📂 {root_name}",
            bg=p["panel"],
            fg=p["fg"] if self.engine.root.is_dir() else p["err"],
        )
        stt = s["stt"] and s["stt_deps"]
        self.chips["stt"].config(
            text="STT ✓" if stt else "STT ✗",
            bg=p["panel"],
            fg=p["ok"] if stt else p["dim"],
        )
        self.chips["tts"].config(
            text="TTS ✓" if s["tts"] else "TTS off",
            bg=p["panel"],
            fg=p["ok"] if s["tts"] else p["dim"],
        )
        if s["llm_enabled"] and s["llm"]:
            self.chips["llm"].config(text="LLM ✓", bg=p["panel"], fg=p["ok"])
        elif s["llm"]:
            self.chips["llm"].config(text="LLM off", bg=p["panel"], fg=p["warn"])
        else:
            self.chips["llm"].config(text="Rules ⚡", bg=p["panel"], fg=p["accent"])

        t_count = ui_helpers.count_trash(self.engine.root)
        self.chips["trash"].config(
            text=f"♻️ {t_count}",
            bg=p["panel"],
            fg=p["warn"] if t_count > 0 else p["dim"],
        )

    # ------------------------------------------------------------ commands
    def _on_enter(self) -> None:
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self.history.append(text)
        self._hist_i = None
        self._update_intent_preview()
        self._submit(text)

    def _on_hist(self, delta: int) -> None:
        if not self.history:
            return
        self._hist_i = (
            len(self.history) - 1
            if self._hist_i is None
            else max(0, min(len(self.history) - 1, self._hist_i + delta))
        )
        self.entry.delete(0, "end")
        self.entry.insert(0, self.history[self._hist_i])
        self._update_intent_preview()

    def _submit(self, text: str) -> None:
        stamp = datetime.now().strftime("%H:%M")
        self._post("you", text, f"[{stamp}] You › ")
        threading.Thread(target=self._worker, args=(text,), daemon=True).start()

    def _worker(self, text: str) -> None:
        self._q.put(("busy", True))
        try:
            res = self.engine.run(text)
            if res.command:
                self._q.put(("post", "cmd", f"⚡ {res.command}", None, False))
            tag = "thans" if res.ok else "err"
            prefix = "THANS › " if res.ok else "⚠ "
            self._q.put(("post", tag, res.message, prefix, res.ok))
            self._q.put(("after_action", res.ok, res.command))
            if self.cfg.get("tts"):
                self.speaker.say(res.message)
        except Exception:  # noqa: BLE001
            self._q.put(("post", "err", "Internal error:\n" + traceback.format_exc(limit=4), "⚠ ", False))
            self._q.put(("after_action", False, ""))
        finally:
            self._q.put(("busy", False))

    # ------------------------------------------------------------------ mic
    def _toggle_mic(self) -> None:
        if self.mic_on:
            self.stt.stop()
            self._q.put(("mic", False))
            return
        if not self.stt.available():
            self._post(
                "sys",
                "Speech model missing — click '⬇ Models' to download it once (~40 MB), "
                "or use text commands.",
                "⚠ ",
            )
            self.show_toast("Speech model not installed — click '⬇ Models'", "warn")
            return
        ok = self.stt.start(
            on_final=self._voice_final,
            on_state=self._mic_state_cb,
            on_partial=lambda part: self._q.put(("mic_partial", part)),
            on_level=lambda lvl: self._q.put(("mic_level", lvl)),
        )
        if ok:
            self._q.put(("mic", True))

    def _mic_state_cb(self, msg: str) -> None:
        self._q.put(("mic_state", msg))

    def _voice_final(self, text: str) -> None:
        self._q.put(("mic", False))
        self._q.put(("voice", text))

    # --------------------------------------------------------------- dialogs
    def _pick_root(self) -> None:
        d = filedialog.askdirectory(
            initialdir=str(self.engine.root),
            title="Choose the working folder THANS may manage",
        )
        if not d:
            return
        self.cfg["root"] = d
        self._safe_save()
        self.engine.set_root(d)
        self._refresh_workspace(animate_diff=False)
        self._set_status(f"working folder: {d}")
        self._post("sys", f"All file operations are now confined to: {d}", "📂 ")
        self.show_toast(f"📂 Working root set to {Path(d).name or d}", "info")

    def _download_models(self) -> None:
        if self._downloading:
            return
        if messagebox.askyesno(
            APP_NAME,
            "Download offline models?\n\n"
            "• STT model (Vosk) ≈ 40 MB\n"
            "• LLM model (Qwen2.5-0.5B) ≈ 408 MB\n\n"
            "One-time; THANS then runs with no internet at all.",
        ):
            self._start_download()

    def _start_download(self) -> None:
        self._downloading = True
        self.btn_dl.config(state="disabled")
        self._post("sys", "Downloading offline models (one-time; needs internet)…", "⬇ ")

        def job() -> None:
            try:
                script, py = platforms.find_downloader()
            except (FileNotFoundError, RuntimeError) as e:
                self._q.put(("post", "err", f"Could not start downloader: {e}", None, False))
                self._q.put(("downloading", False))
                return
            try:
                proc = subprocess.Popen(
                    [py, str(script), "--dir", str(config.models_dir())],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=str(script.parent.parent),
                )
                assert proc.stdout is not None
                for line in proc.stdout:
                    line = line.rstrip()
                    if line:
                        self._q.put(("post", "sys", line, None, False))
                code = proc.wait()
            except Exception as e:  # noqa: BLE001
                code = -1
                self._q.put(("post", "err", f"Could not start downloader: {e}", None, False))
            self._q.put(
                (
                    "post",
                    "sys" if code == 0 else "err",
                    "Download finished — voice input ready."
                    if code == 0
                    else f"Download failed (code {code}). Check the network and retry.",
                    None,
                    False,
                )
            )
            self._q.put(("downloading", False))
            self._q.put(("chips",))

        threading.Thread(target=job, daemon=True).start()

    def _settings(self) -> None:
        p = self.pal
        dlg = tk.Toplevel(self.root)
        dlg.title("THANS Settings")
        dlg.configure(bg=p["panel"])
        dlg.resizable(False, False)
        pad = dict(padx=16, pady=6)

        tk.Label(
            dlg,
            text="Working folder (THANS is strictly confined to this folder)",
            bg=p["panel"],
            fg=p["dim"],
            font=FONT_UI_BOLD,
        ).pack(anchor="w", **pad)
        f1 = tk.Frame(dlg, bg=p["panel"])
        f1.pack(fill="x", **pad)
        var_root = tk.StringVar(value=str(self.engine.root))
        tk.Entry(
            f1,
            textvariable=var_root,
            font=FONT_MONO,
            bg=p["panel2"],
            fg=p["fg"],
            insertbackground=p["fg"],
            relief="flat",
        ).pack(side="left", fill="x", expand=True, ipady=4)

        def browse() -> None:
            d = filedialog.askdirectory(initialdir=var_root.get())
            if d:
                var_root.set(d)

        ttk.Button(f1, text="Browse", command=browse).pack(side="left", padx=(6, 0))

        var_tts = tk.BooleanVar(value=bool(self.cfg.get("tts")))
        tk.Checkbutton(
            dlg,
            text="Speak replies aloud (offline TTS)",
            variable=var_tts,
            bg=p["panel"],
            fg=p["fg"],
            activebackground=p["panel"],
            activeforeground=p["fg"],
            selectcolor=p["panel2"],
        ).pack(anchor="w", **pad)

        f2 = tk.Frame(dlg, bg=p["panel"])
        f2.pack(fill="x", **pad)
        tk.Label(f2, text="Speech rate:", bg=p["panel"], fg=p["dim"]).pack(side="left")
        var_rate = tk.IntVar(value=int(self.cfg.get("tts_rate", 185)))
        ttk.Scale(
            f2, from_=110, to=280, variable=var_rate, orient="horizontal", length=220
        ).pack(side="left", padx=(8, 0))

        var_anim = tk.BooleanVar(value=bool(self.animations_on))
        tk.Checkbutton(
            dlg,
            text="Enable 60fps sonic wave & smooth UI animations",
            variable=var_anim,
            bg=p["panel"],
            fg=p["fg"],
            activebackground=p["panel"],
            activeforeground=p["fg"],
            selectcolor=p["panel2"],
        ).pack(anchor="w", **pad)

        var_llm = tk.BooleanVar(value=bool(self.cfg.get("use_llm")))
        tk.Checkbutton(
            dlg,
            text="Use offline LLM for free-form commands (optional)",
            variable=var_llm,
            bg=p["panel"],
            fg=p["fg"],
            activebackground=p["panel"],
            activeforeground=p["fg"],
            selectcolor=p["panel2"],
        ).pack(anchor="w", **pad)

        tk.Label(
            dlg, text="LLM model (models/*.gguf):", bg=p["panel"], fg=p["dim"], font=FONT_SUB
        ).pack(anchor="w", **pad)
        ggufs = [m.name for m in model_manager.all_gguf()]
        cur = self.cfg.get("llm_model", "")
        if cur and cur not in ggufs:
            ggufs = [cur] + ggufs
        var_llm_model = tk.StringVar(value=cur)
        ttk.Combobox(
            dlg, textvariable=var_llm_model, values=ggufs or [cur], state="readonly"
        ).pack(fill="x", **pad)

        var_perm = tk.BooleanVar(value=bool(self.cfg.get("permanent_delete")))
        tk.Checkbutton(
            dlg,
            text="Danger: deletes bypass the trash (permanent)",
            variable=var_perm,
            bg=p["panel"],
            fg=p["warn"],
            activebackground=p["panel"],
            activeforeground=p["warn"],
            selectcolor=p["panel2"],
        ).pack(anchor="w", **pad)

        def save() -> None:
            cfg = self.cfg
            cfg["root"] = var_root.get().strip() or cfg["root"]
            cfg["tts"] = bool(var_tts.get())
            cfg["tts_rate"] = int(var_rate.get())
            cfg["animations"] = bool(var_anim.get())
            cfg["use_llm"] = bool(var_llm.get())
            cfg["llm_model"] = var_llm_model.get().strip() or cfg.get("llm_model", "")
            cfg["permanent_delete"] = bool(var_perm.get())
            try:
                config.save_config(cfg)
            except OSError as e:
                self.show_toast(f"⚠ Could not save settings: {e}", "err")
                return
            self.cfg = cfg
            self.animations_on = cfg["animations"]
            self.engine = Engine(cfg["root"], cfg)
            self.speaker.enabled = cfg["tts"]
            self.speaker.set_rate(int(cfg["tts_rate"]))
            self._refresh_workspace(animate_diff=False)
            self._set_status(f"working folder: {self.engine.current}")
            self._post("sys", "Settings saved.", "⚙ ")
            self.show_toast("⚙ Settings saved", "ok")
            dlg.destroy()

        ttk.Button(dlg, text="Save Settings", style="Accent.TButton", command=save).pack(
            pady=(10, 14)
        )
        dlg.grab_set()
        dlg.transient(self.root)

    # ---------------------------------------------------------------- misc
    def _on_close(self) -> None:
        self._closing = True
        try:
            self.stt.stop()
        except Exception:
            pass
        try:
            self.speaker.stop()
        except Exception:
            pass
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()

"""THANS main window — sleek minimalist UI, 60 FPS animations, live explorer & intent preview.

Layout:
  [header: brand · animated voice/activity wave canvas · status chips · theme/palette/explorer toggles]
  [interactive breadcrumb bar: 🏠 root › 📁 subfolder · ⬆ Up · 📂 Root]
  [split body: animated chat stream (left)  |  live workspace inspector sidebar (right)]
  [live intent preview bar + Tab autocomplete hint]
  [input bar | Send | 🎤 Mic | quick action pills]
  [status bar: working dir · undo/trash status · shortcuts · version]
"""
from __future__ import annotations

import math
import queue
import shutil
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import APP_NAME, APP_TAGLINE, __version__, config, model_manager, ux
from .engine import Engine
from .stt import VoiceSTT
from .tts import Speaker

IS_WIN = sys.platform == "win32"
FONT_UI = ("Segoe UI", 10) if IS_WIN else ("DejaVu Sans", 10)
FONT_UI_B = ("Segoe UI", 10, "bold") if IS_WIN else ("DejaVu Sans", 10, "bold")
FONT_SM = ("Segoe UI", 9) if IS_WIN else ("DejaVu Sans", 9)
FONT_SM_B = ("Segoe UI", 9, "bold") if IS_WIN else ("DejaVu Sans", 9, "bold")
FONT_TITLE = ("Segoe UI", 15, "bold") if IS_WIN else ("DejaVu Sans", 14, "bold")
MONO = ("Consolas", 10) if IS_WIN else ("DejaVu Sans Mono", 10)
MONO_S = ("Consolas", 9) if IS_WIN else ("DejaVu Sans Mono", 9)
MONO_B = ("Consolas", 10, "bold") if IS_WIN else ("DejaVu Sans Mono", 10, "bold")


class ThansApp:
    def __init__(self, cfg: dict | None = None, text_only: bool = False):
        self.cfg = dict(cfg or config.load_config())
        self.theme_name = str(self.cfg.get("theme", "obsidian"))
        self.palette = ux.get_theme(self.theme_name)
        self.show_explorer = bool(self.cfg.get("show_explorer", True))

        self.engine = Engine(self.cfg["root"], self.cfg)
        self.stt = VoiceSTT()
        self.speaker = Speaker(self.cfg.get("tts", True), int(self.cfg.get("tts_rate", 185)))
        self.mic_on = False
        self._busy = False
        self._downloading = False
        self.history: list[str] = []
        self._hist_i: int | None = None
        self._q: "queue.Queue" = queue.Queue()
        self.text_only = text_only

        # Animation state (60 FPS wave + smooth color transitions + typewriter stream)
        self._phase = 0.0
        self._anim_mode = "idle"       # "idle" | "listening" | "busy" | "success" | "error"
        self._flash_until = 0.0
        self._stream_queue: list[tuple[str, str]] = []
        self._explorer_items: list[dict[str, Any]] = []
        self._pill_buttons: list[tk.Button] = []

        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} — {APP_TAGLINE}")
        self.root.geometry("1040x660")
        self.root.minsize(740, 480)
        self._style()
        self._build()
        self._apply_theme()
        self._refresh_chips()
        self._refresh_workspace()
        self._welcome()
        self._bind_shortcuts()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(60, self._poll)
        self.root.after(25, self._animate)

    # ------------------------------------------------------------------ style & theme
    def _style(self) -> None:
        self.ttk_style = ttk.Style(self.root)
        try:
            self.ttk_style.theme_use("clam")
        except tk.TclError:
            pass

    def _apply_theme(self) -> None:
        p = self.palette
        self.root.configure(bg=p["bg"])
        st = self.ttk_style
        st.configure(".", background=p["panel"], foreground=p["fg"])
        st.configure("TButton", background=p["panel2"], foreground=p["fg"], padding=6,
                     borderwidth=0, focusthickness=0)
        st.map("TButton", background=[("active", p["panel3"])])
        st.configure("Accent.TButton", background=p["accent"], foreground="#ffffff", padding=8)
        st.map("Accent.TButton", background=[("active", p["accent_hover"])])

        # Re-color key frames and widgets
        for w in (self.head_frame, self.crumb_frame, self.body_frame, self.input_outer, self.pills_frame):
            w.configure(bg=p["bg"])

        self.title_lbl.configure(bg=p["bg"], fg=p["fg"])
        self.sub_lbl.configure(bg=p["bg"], fg=p["dim"])
        self.wave_canvas.configure(bg=p["panel"])
        self.chips_frame.configure(bg=p["bg"])

        self.chat_card.configure(bg=p["border"])
        self.chat.configure(bg=p["panel"], fg=p["fg"], insertbackground=p["fg"])
        self.chat.tag_configure("you_badge", foreground=p["accent"], font=MONO_B)
        self.chat.tag_configure("you", foreground=p["user"], font=MONO)
        self.chat.tag_configure("thans_badge", foreground=p["ok"], font=MONO_B)
        self.chat.tag_configure("thans", foreground=p["asst"], font=MONO)
        self.chat.tag_configure("sys_badge", foreground=p["warn"], font=MONO_B)
        self.chat.tag_configure("sys", foreground=p["dim"], font=MONO_S)
        self.chat.tag_configure("cmd", foreground=p["muted"], font=MONO_S)
        self.chat.tag_configure("time", foreground=p["muted"], font=MONO_S)

        self.explorer_card.configure(bg=p["border"])
        self.explorer_inner.configure(bg=p["panel"])
        self.exp_head.configure(bg=p["panel"])
        self.exp_title.configure(bg=p["panel"], fg=p["fg"])
        self.exp_counts.configure(bg=p["panel"], fg=p["dim"])
        self.exp_list.configure(
            bg=p["panel"], fg=p["fg"],
            selectbackground=p["accent_soft"], selectforeground=p["fg"],
        )
        self.exp_foot.configure(bg=p["panel2"])
        self.btn_undo_side.configure(bg=p["panel2"], fg=p["fg"], activebackground=p["panel3"], activeforeground=p["fg"])
        self.btn_trash_side.configure(bg=p["panel2"], fg=p["dim"], activebackground=p["panel3"], activeforeground=p["fg"])

        self.intent_bar.configure(bg=p["panel"])
        self.intent_badge.configure(bg=p["accent_soft"], fg=p["accent"])
        self.intent_text.configure(bg=p["panel"], fg=p["dim"])
        self.intent_tab.configure(bg=p["panel"], fg=p["muted"])

        self.entry_border.configure(bg=p["border"])
        self.entry.configure(bg=p["panel2"], fg=p["fg"], insertbackground=p["fg"])

        for b in (self.btn_theme, self.btn_palette, self.btn_explorer, self.btn_root, self.btn_dl, self.btn_settings):
            b.configure(bg=p["panel2"], fg=p["fg"], activebackground=p["panel3"], activeforeground=p["fg"])
        self.btn_send.configure(bg=p["accent"], fg="#ffffff", activebackground=p["accent_hover"], activeforeground="#ffffff")
        if hasattr(self, "btn_mic"):
            self.btn_mic.configure(
                bg=p["err"] if self.mic_on else p["panel2"],
                fg="#ffffff" if self.mic_on else p["fg"],
                activebackground=p["panel3"],
            )

        self.status_bar.configure(bg=p["panel"])
        self.status.configure(bg=p["panel"], fg=p["dim"])
        self.status_right.configure(bg=p["panel"], fg=p["muted"])

        self._refresh_chips()
        self._refresh_workspace()
        self._on_input_changed()

    def _cycle_theme(self) -> None:
        idx = ux.THEME_ORDER.index(self.theme_name) if self.theme_name in ux.THEME_ORDER else 0
        self.theme_name = ux.THEME_ORDER[(idx + 1) % len(ux.THEME_ORDER)]
        self.palette = ux.get_theme(self.theme_name)
        self.cfg["theme"] = self.theme_name
        config.save_config(self.cfg)
        self._apply_theme()
        self._set_status(f"Theme switched to {self.palette['name']}")

    # ------------------------------------------------------------------ build UI
    def _make_flat_btn(self, parent: tk.Widget, text: str, cmd, accent: bool = False, width: int | None = None) -> tk.Button:
        p = self.palette
        bg = p["accent"] if accent else p["panel2"]
        fg = "#ffffff" if accent else p["fg"]
        kw: dict[str, Any] = dict(
            text=text, command=cmd, font=FONT_SM_B, bd=0, relief="flat",
            bg=bg, fg=fg, padx=10, pady=5, cursor="hand2",
            activebackground=p["accent_hover"] if accent else p["panel3"],
            activeforeground="#ffffff" if accent else p["fg"],
        )
        if width is not None:
            kw["width"] = width
        btn = tk.Button(parent, **kw)

        def on_enter(_e):
            if btn["state"] != "disabled":
                btn.configure(bg=self.palette["accent_hover"] if accent else self.palette["panel3"])

        def on_leave(_e):
            if btn["state"] != "disabled":
                btn.configure(bg=self.palette["accent"] if accent else self.palette["panel2"])

        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)
        return btn

    def _build(self) -> None:
        p = self.palette

        # 1. Header bar: brand + animated wave canvas + model chips + toolbar toggles
        self.head_frame = tk.Frame(self.root, bg=p["bg"])
        self.head_frame.pack(fill="x", padx=16, pady=(12, 4))

        brand_box = tk.Frame(self.head_frame, bg=p["bg"])
        brand_box.pack(side="left")
        self.title_lbl = tk.Label(brand_box, text=APP_NAME, font=FONT_TITLE, bg=p["bg"], fg=p["fg"])
        self.title_lbl.pack(side="left")
        self.sub_lbl = tk.Label(
            brand_box,
            text=f"  offline voice & text assistant  ·  v{__version__}",
            font=FONT_SM, bg=p["bg"], fg=p["dim"],
        )
        self.sub_lbl.pack(side="left", pady=(4, 0))

        # Animated acoustic wave & status orb canvas
        self.wave_canvas = tk.Canvas(
            self.head_frame, width=132, height=28, bg=p["panel"],
            highlightthickness=0, bd=0,
        )
        self.wave_canvas.pack(side="left", padx=(14, 6))

        # Right-side controls & status chips
        self.chips_frame = tk.Frame(self.head_frame, bg=p["bg"])
        self.chips_frame.pack(side="right")

        self.chips: dict[str, tk.Label] = {}
        for key, label in (("stt", "STT"), ("tts", "TTS"), ("llm", "LLM")):
            lbl = tk.Label(self.chips_frame, text=label, font=FONT_SM_B, bg=p["panel"], fg=p["dim"], padx=8, pady=4)
            lbl.pack(side="left", padx=2)
            self.chips[key] = lbl

        self.btn_theme = self._make_flat_btn(self.chips_frame, "◑ Theme", self._cycle_theme)
        self.btn_theme.pack(side="left", padx=(6, 2))
        self.btn_palette = self._make_flat_btn(self.chips_frame, "⌘ Commands", self._open_palette)
        self.btn_palette.pack(side="left", padx=2)
        self.btn_explorer = self._make_flat_btn(self.chips_frame, "📁 Explorer", self._toggle_explorer)
        self.btn_explorer.pack(side="left", padx=2)

        # 2. Interactive Breadcrumb & Workspace Path Bar
        self.crumb_frame = tk.Frame(self.root, bg=p["bg"])
        self.crumb_frame.pack(fill="x", padx=16, pady=(2, 4))
        self.crumb_inner = tk.Frame(self.crumb_frame, bg=p["bg"])
        self.crumb_inner.pack(side="left", fill="x", expand=True)

        # 3. Main Split Body: Chat Stream (left) + Collapsible Live Workspace Inspector (right)
        self.body_frame = tk.Frame(self.root, bg=p["bg"])
        self.body_frame.pack(fill="both", expand=True, padx=16, pady=4)

        # Left: Chat card with 1px subtle border
        self.chat_card = tk.Frame(self.body_frame, bg=p["border"], padx=1, pady=1)
        self.chat_card.pack(side="left", fill="both", expand=True)

        self.chat = tk.Text(
            self.chat_card, bg=p["panel"], fg=p["fg"], insertbackground=p["fg"],
            font=MONO, relief="flat", wrap="word", state="disabled",
            padx=16, pady=12, spacing1=3, spacing3=4, highlightthickness=0,
        )
        self.chat.pack(fill="both", expand=True)

        # Right: Live Workspace Explorer card
        self.explorer_card = tk.Frame(self.body_frame, bg=p["border"], width=275, padx=1, pady=1)
        if self.show_explorer:
            self.explorer_card.pack(side="right", fill="y", padx=(10, 0))
        self.explorer_card.pack_propagate(False)

        self.explorer_inner = tk.Frame(self.explorer_card, bg=p["panel"])
        self.explorer_inner.pack(fill="both", expand=True)

        self.exp_head = tk.Frame(self.explorer_inner, bg=p["panel"])
        self.exp_head.pack(fill="x", padx=10, pady=(8, 4))
        self.exp_title = tk.Label(self.exp_head, text="WORKSPACE", font=FONT_SM_B, bg=p["panel"], fg=p["fg"])
        self.exp_title.pack(side="left")
        self.exp_counts = tk.Label(self.exp_head, text="", font=FONT_SM, bg=p["panel"], fg=p["dim"])
        self.exp_counts.pack(side="right")

        self.exp_list = tk.Listbox(
            self.explorer_inner, font=MONO_S, bg=p["panel"], fg=p["fg"],
            bd=0, relief="flat", highlightthickness=0, activestyle="none",
            selectbackground=p["accent_soft"], selectforeground=p["fg"],
        )
        self.exp_list.pack(fill="both", expand=True, padx=8, pady=4)
        self.exp_list.bind("<Double-Button-1>", self._on_explorer_dblclick)
        self.exp_list.bind("<Return>", self._on_explorer_dblclick)
        self.exp_list.bind("<Button-3>", self._on_explorer_context)

        self.exp_foot = tk.Frame(self.explorer_inner, bg=p["panel2"])
        self.exp_foot.pack(fill="x", side="bottom")
        self.btn_undo_side = tk.Button(
            self.exp_foot, text="↶ Undo", font=FONT_SM, bd=0, relief="flat",
            bg=p["panel2"], fg=p["fg"], padx=8, pady=5, cursor="hand2",
            command=lambda: self._submit("undo"),
        )
        self.btn_undo_side.pack(side="left", fill="x", expand=True)
        self.btn_trash_side = tk.Button(
            self.exp_foot, text="🗑 Trash (0)", font=FONT_SM, bd=0, relief="flat",
            bg=p["panel2"], fg=p["dim"], padx=8, pady=5, cursor="hand2",
            command=lambda: self._submit("show trash"),
        )
        self.btn_trash_side.pack(side="right", fill="x", expand=True)

        # 4. Live Intent Preview & Tab Autocomplete Bar
        self.intent_bar = tk.Frame(self.root, bg=p["panel"])
        self.intent_bar.pack(fill="x", padx=16, pady=(2, 2))
        self.intent_badge = tk.Label(
            self.intent_bar, text="READY", font=FONT_SM_B,
            bg=p["accent_soft"], fg=p["accent"], padx=8, pady=2,
        )
        self.intent_badge.pack(side="left", padx=(6, 8), pady=3)
        self.intent_text = tk.Label(
            self.intent_bar, text="", font=FONT_SM,
            bg=p["panel"], fg=p["dim"], anchor="w",
        )
        self.intent_text.pack(side="left", fill="x", expand=True)
        self.intent_tab = tk.Label(
            self.intent_bar, text="", font=MONO_S,
            bg=p["panel"], fg=p["muted"], padx=8,
        )
        self.intent_tab.pack(side="right")

        # 5. Input Row
        self.input_outer = tk.Frame(self.root, bg=p["bg"])
        self.input_outer.pack(fill="x", padx=16, pady=(2, 4))

        self.entry_border = tk.Frame(self.input_outer, bg=p["border"], padx=1, pady=1)
        self.entry_border.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry = tk.Entry(
            self.entry_border, font=MONO, bg=p["panel2"], fg=p["fg"],
            insertbackground=p["fg"], relief="flat", bd=6,
        )
        self.entry.pack(fill="x", expand=True, ipady=3)
        self.entry.bind("<Return>", lambda _e: self._on_enter())
        self.entry.bind("<Up>", lambda _e: self._on_hist(-1))
        self.entry.bind("<Down>", lambda _e: self._on_hist(1))
        self.entry.bind("<Tab>", self._on_tab_complete)
        self.entry.bind("<KeyRelease>", lambda _e: self._on_input_changed())
        self.entry.bind("<FocusIn>", lambda _e: self.entry_border.configure(bg=self.palette["accent"]))
        self.entry.bind("<FocusOut>", lambda _e: self.entry_border.configure(bg=self.palette["border"]))
        self.entry.focus_set()

        self.btn_send = self._make_flat_btn(self.input_outer, "Send ↵", self._on_enter, accent=True)
        self.btn_send.pack(side="left", padx=(0, 6), ipady=3)

        if not self.text_only:
            self.btn_mic = tk.Button(
                self.input_outer, text="🎤 Speak", font=FONT_SM_B, bd=0, relief="flat",
                bg=p["panel2"], fg=p["fg"], padx=10, pady=5, cursor="hand2",
                command=self._toggle_mic,
            )
            self.btn_mic.pack(side="left", padx=(0, 6), ipady=3)

        self.btn_root = self._make_flat_btn(self.input_outer, "📂 Folder", self._pick_root)
        self.btn_root.pack(side="left", padx=(0, 6), ipady=3)
        self.btn_dl = self._make_flat_btn(self.input_outer, "⬇ Models", self._download_models)
        self.btn_dl.pack(side="left", padx=(0, 6), ipady=3)
        self.btn_settings = self._make_flat_btn(self.input_outer, "⚙ Settings", self._settings)
        self.btn_settings.pack(side="left", ipady=3)

        # 6. Quick-Action Pills Bar
        self.pills_frame = tk.Frame(self.root, bg=p["bg"])
        self.pills_frame.pack(fill="x", padx=16, pady=(0, 6))

        # 7. Status Bar
        self.status_bar = tk.Frame(self.root, bg=p["panel"])
        self.status_bar.pack(fill="x", side="bottom")
        self.status = tk.Label(self.status_bar, text="ready", bg=p["panel"], fg=p["dim"], font=FONT_SM, anchor="w")
        self.status.pack(side="left", fill="x", expand=True, padx=12, pady=4)
        self.status_right = tk.Label(
            self.status_bar,
            text=f"F2 Voice · Tab Complete · Ctrl+K Commands · Ctrl+B Explorer · v{__version__}",
            bg=p["panel"], fg=p["muted"], font=FONT_SM,
        )
        self.status_right.pack(side="right", padx=12, pady=4)

    def _bind_shortcuts(self) -> None:
        if not self.text_only:
            self.root.bind("<F2>", lambda _e: self._toggle_mic())
        self.root.bind("<Control-k>", lambda _e: self._open_palette())
        self.root.bind("<Control-K>", lambda _e: self._open_palette())
        self.root.bind("<Control-b>", lambda _e: self._toggle_explorer())
        self.root.bind("<Control-B>", lambda _e: self._toggle_explorer())
        self.root.bind("<Control-l>", lambda _e: self._clear_chat())

    # ------------------------------------------------------------ animations
    def _animate(self) -> None:
        """60 FPS animation loop: acoustic wave canvas + status orb + streamed message lines."""
        now = time.monotonic()
        self._phase += 0.085

        # Determine active animation mode
        if self.mic_on:
            mode = "listening"
        elif self._busy or self._downloading:
            mode = "busy"
        elif now < self._flash_until:
            mode = self._anim_mode
        else:
            mode = "idle"
            self._anim_mode = "idle"

        self._draw_wave_canvas(mode)

        # Stream any queued lines smoothly for a responsive typewriter feel
        if self._stream_queue:
            tag, chunk = self._stream_queue.pop(0)
            self.chat.config(state="normal")
            self.chat.insert("end", chunk, tag)
            self.chat.config(state="disabled")
            self.chat.see("end")

        self.root.after(25, self._animate)

    def _draw_wave_canvas(self, mode: str) -> None:
        c = self.wave_canvas
        p = self.palette
        c.delete("all")
        w, h = 132, 28
        cy = h / 2.0

        # Choose accent color based on mode
        if mode == "listening":
            base_col = p["err"]
            label_txt = "REC"
        elif mode == "busy":
            base_col = p["accent"]
            label_txt = "RUN"
        elif mode == "success":
            base_col = p["ok"]
            label_txt = "OK"
        elif mode == "error":
            base_col = p["warn"]
            label_txt = "!"
        else:
            base_col = p["accent"]
            label_txt = "IDLE"

        # Pulsing orb on the left of the wave canvas
        pulse = 0.5 + 0.5 * math.sin(self._phase * (3.2 if mode != "idle" else 1.2))
        outer_r = 5.5 + (3.0 * pulse if mode != "idle" else 1.0 * pulse)
        glow_col = ux.lerp_color(p["panel"], base_col, 0.35 + 0.35 * pulse)
        ox = 14.0
        c.create_oval(ox - outer_r, cy - outer_r, ox + outer_r, cy + outer_r, fill=glow_col, outline="")
        c.create_oval(ox - 3.5, cy - 3.5, ox + 3.5, cy + 3.5, fill=base_col, outline="")

        # 9 animated wave bars
        bars = ux.wave_heights(self._phase, count=9, mode=mode)
        x0 = 30
        for i, bh in enumerate(bars):
            bx = x0 + i * 7
            half_h = max(2.0, bh * 10.5)
            bar_col = ux.lerp_color(p["muted"], base_col, min(1.0, bh + 0.25))
            c.create_line(bx, cy - half_h, bx, cy + half_h, fill=bar_col, width=3, capstyle="round")

        # Mode micro-label on the right of the canvas
        c.create_text(112, cy, text=label_txt, fill=p["dim"], font=FONT_SM_B)

    def _trigger_flash(self, ok: bool) -> None:
        self._anim_mode = "success" if ok else "error"
        self._flash_until = time.monotonic() + 1.1

    # ------------------------------------------------------------ workspace & breadcrumbs
    def _refresh_workspace(self) -> None:
        snap = ux.workspace_snapshot(self.engine.root, self.engine.current, self.engine.undo_stack)
        p = self.palette

        # 1. Rebuild breadcrumbs
        for child in self.crumb_inner.winfo_children():
            child.destroy()

        tk.Label(self.crumb_inner, text="PATH", font=FONT_SM_B, bg=p["bg"], fg=p["muted"], padx=4).pack(side="left")
        for idx, (label, target) in enumerate(snap["breadcrumbs"]):
            if idx > 0:
                tk.Label(self.crumb_inner, text="›", font=FONT_SM_B, bg=p["bg"], fg=p["muted"], padx=2).pack(side="left")
            is_last = idx == len(snap["breadcrumbs"]) - 1
            b = tk.Button(
                self.crumb_inner, text=label, font=FONT_SM_B if is_last else FONT_SM,
                bd=0, relief="flat", padx=7, pady=2, cursor="hand2",
                bg=p["accent_soft"] if is_last else p["panel"],
                fg=p["accent"] if is_last else p["dim"],
                activebackground=p["panel2"], activeforeground=p["fg"],
                command=(lambda t=target: self._submit(f"go to {t}" if t != "~" else "cd")),
            )
            b.pack(side="left", padx=1)

        if snap["can_go_up"]:
            up_btn = tk.Button(
                self.crumb_inner, text="⬆ Up", font=FONT_SM, bd=0, relief="flat",
                padx=7, pady=2, cursor="hand2", bg=p["panel2"], fg=p["fg"],
                command=lambda: self._submit("go back"),
            )
            up_btn.pack(side="left", padx=(8, 2))

        # 2. Populate Explorer Listbox
        self._explorer_items = snap["items"]
        self.exp_counts.config(text=f"{snap['folders']} dir · {snap['files']} file")
        self.exp_list.delete(0, "end")
        if not self._explorer_items:
            self.exp_list.insert("end", "  (folder is empty)")
        else:
            for item in self._explorer_items:
                suffix = "/" if item["is_dir"] else ""
                meta = f"  [{item['size']}]" if item["size"] else ""
                self.exp_list.insert("end", f" {item['icon']} {item['name']}{suffix}{meta}")

        # 3. Update Undo & Trash footer buttons
        if snap["undo_count"] > 0:
            self.btn_undo_side.config(text=f"↶ {snap['undo_label'][:22]}", fg=p["accent"], state="normal")
        else:
            self.btn_undo_side.config(text="↶ Undo (0)", fg=p["muted"], state="normal")
        self.btn_trash_side.config(
            text=f"🗑 Trash ({snap['trash_count']})",
            fg=p["warn"] if snap["trash_count"] else p["dim"],
        )

        # 4. Rebuild contextual Quick-Action pills
        for child in self.pills_frame.winfo_children():
            child.destroy()
        self._pill_buttons.clear()

        for pill in ux.quick_actions(snap):
            btn = tk.Button(
                self.pills_frame, text=pill["label"], font=FONT_SM, bd=0, relief="flat",
                bg=p["panel"], fg=p["dim"], padx=9, pady=3, cursor="hand2",
                activebackground=p["accent_soft"], activeforeground=p["accent"],
                command=(lambda pl=pill: self._on_pill_click(pl)),
            )
            btn.pack(side="left", padx=(0, 5))
            btn.bind("<Enter>", lambda _e, b=btn: b.configure(bg=self.palette["panel2"], fg=self.palette["fg"]))
            btn.bind("<Leave>", lambda _e, b=btn: b.configure(bg=self.palette["panel"], fg=self.palette["dim"]))
            self._pill_buttons.append(btn)

    def _toggle_explorer(self) -> None:
        self.show_explorer = not self.show_explorer
        self.cfg["show_explorer"] = self.show_explorer
        config.save_config(self.cfg)
        if self.show_explorer:
            self.explorer_card.pack(side="right", fill="y", padx=(10, 0))
            self._refresh_workspace()
        else:
            self.explorer_card.pack_forget()

    def _on_explorer_dblclick(self, _event=None) -> None:
        sel = self.exp_list.curselection()
        if not sel or not self._explorer_items:
            return
        idx = sel[0]
        if idx >= len(self._explorer_items):
            return
        item = self._explorer_items[idx]
        self._submit(item["primary_cmd"])

    def _on_explorer_context(self, event) -> None:
        if not self._explorer_items:
            return
        idx = self.exp_list.nearest(event.y)
        if idx < 0 or idx >= len(self._explorer_items):
            return
        self.exp_list.selection_clear(0, "end")
        self.exp_list.selection_set(idx)
        item = self._explorer_items[idx]
        name = item["name"]
        p = self.palette
        menu = tk.Menu(self.root, tearoff=0, bg=p["panel2"], fg=p["fg"], activebackground=p["accent"], activeforeground="#ffffff")
        if item["is_dir"]:
            menu.add_command(label=f"📁 Enter '{name}'", command=lambda: self._submit(f"go to {name}"))
            menu.add_command(label=f"📋 List '{name}'", command=lambda: self._submit(f"list {name}"))
            menu.add_command(label=f"✨ Organize '{name}'", command=lambda: self._submit(f"organize {name}"))
        else:
            menu.add_command(label=f"👁 Preview '{name}'", command=lambda: self._submit(f"read {name}"))
            menu.add_command(label=f"🚀 Open '{name}'", command=lambda: self._submit(f"open {name}"))
        menu.add_separator()
        menu.add_command(label="✏ Rename…", command=lambda: self._prefill_input(f"rename {name} to "))
        menu.add_command(label="📦 Move to…", command=lambda: self._prefill_input(f"move {name} to "))
        menu.add_command(label="📑 Copy to…", command=lambda: self._prefill_input(f"copy {name} to "))
        menu.add_separator()
        menu.add_command(label="🗑 Move to Trash", command=lambda: self._submit(f"delete {name}"))
        menu.tk_popup(event.x_root, event.y_root)

    # ------------------------------------------------------------ live intent & autocomplete
    def _on_input_changed(self) -> None:
        txt = self.entry.get()
        info = ux.live_intent_preview(txt, self.engine.current)
        p = self.palette
        state = info["state"]
        if state == "valid":
            self.intent_badge.config(text=info["badge"], bg=p["accent_soft"], fg=p["ok"])
            self.intent_text.config(text=info["text"], fg=p["fg"])
        elif state == "hint":
            self.intent_badge.config(text=info["badge"], bg=p["panel2"], fg=p["warn"])
            self.intent_text.config(text=info["text"], fg=p["dim"])
        else:
            self.intent_badge.config(text=info["badge"], bg=p["panel2"], fg=p["accent"])
            self.intent_text.config(text=info["text"], fg=p["dim"])

        comp = info.get("completion") or ""
        self.intent_tab.config(text=f"⇥ Tab: {comp}" if comp else "")

    def _on_tab_complete(self, _event=None) -> str:
        txt = self.entry.get()
        comp = ux.autocomplete(txt, self.engine.current)
        if comp:
            self.entry.delete(0, "end")
            self.entry.insert(0, comp)
            self._on_input_changed()
        return "break"

    def _prefill_input(self, text: str) -> None:
        self.entry.delete(0, "end")
        self.entry.insert(0, text)
        self.entry.focus_set()
        self.entry.icursor("end")
        self._on_input_changed()

    def _on_pill_click(self, pill: dict[str, str]) -> None:
        if pill.get("kind") == "fill":
            self._prefill_input(pill["cmd"])
        else:
            self._submit(pill["cmd"])

    # ------------------------------------------------------------ chat api
    def _welcome(self) -> None:
        s = model_manager.status(self.cfg)
        self._post(
            "sys",
            f"Welcome to {APP_NAME} — type or speak a natural command, click any item in the "
            f"Explorer on the right, or press Ctrl+K for the Command Palette.",
            "★ SYSTEM",
            stream=False,
        )
        if not self.text_only and not (s["stt"] and s["stt_deps"]):
            self._post(
                "sys",
                "Offline voice input uses the Vosk STT model (~40 MB). Click '⬇ Models' once "
                "to download it, or use text commands right away.",
                "ℹ VOICE",
                stream=False,
            )
        self._set_status(f"Working folder: {self.engine.root}")

    def _post(self, kind: str, text: str, prefix: str | None = None, stream: bool = True) -> None:
        stamp = datetime.now().strftime("%H:%M")
        badge_tag = "you_badge" if kind == "you" else ("thans_badge" if kind == "thans" else "sys_badge")
        self.chat.config(state="normal")
        if prefix:
            self.chat.insert("end", f"[{stamp}] ", "time")
            self.chat.insert("end", f"{prefix}  ", badge_tag)
        if not stream or kind in ("you", "cmd") or len(text) < 28:
            self.chat.insert("end", text + "\n\n", kind)
            self.chat.config(state="disabled")
            self.chat.see("end")
        else:
            self.chat.config(state="disabled")
            lines = (text + "\n\n").splitlines(keepends=True)
            for ln in lines:
                self._stream_queue.append((kind, ln))

    def _clear_chat(self) -> None:
        self._stream_queue.clear()
        self.chat.config(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.config(state="disabled")
        self._post("sys", "Conversation cleared.", "✨ CLEAR", stream=False)

    def _set_status(self, text: str) -> None:
        self.status.config(text=text)

    def _set_mic(self, on: bool) -> None:
        self.mic_on = on
        p = self.palette
        if hasattr(self, "btn_mic"):
            self.btn_mic.config(
                bg=p["err"] if on else p["panel2"],
                fg="#ffffff" if on else p["fg"],
                text="⏹ Stop" if on else "🎤 Speak",
            )
        self._set_status(
            "🎙 Listening — speak your command, then pause…"
            if on else f"Working folder: {self.engine.current}"
        )

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        if busy:
            self._set_status("⚡ Executing command…")

    # ------------------------------------------------------------- polling
    def _poll(self) -> None:
        try:
            while True:
                item = self._q.get_nowait()
                kind = item[0]
                if kind == "post":
                    self._post(item[1], item[2], item[3])
                elif kind == "done":
                    ok = bool(item[1])
                    self._set_busy(False)
                    self._trigger_flash(ok)
                    self._refresh_workspace()
                    self._on_input_changed()
                    self._set_status(f"Working folder: {self.engine.current}")
                elif kind == "busy":
                    self._set_busy(item[1])
                elif kind == "chips":
                    self._refresh_chips()
                elif kind == "status":
                    self._set_status(item[1])
                elif kind == "mic":
                    self._set_mic(item[1])
                elif kind == "mic_state":
                    self._set_status(item[1])
                elif kind == "voice":
                    self._submit(item[1])
                elif kind == "downloading":
                    self._downloading = item[1]
                    self.btn_dl.config(state="disabled" if item[1] else "normal")
        except queue.Empty:
            pass
        self.root.after(60, self._poll)

    def _refresh_chips(self) -> None:
        s = model_manager.status(self.cfg)
        p = self.palette
        stt = s["stt"] and s["stt_deps"]
        self.chips["stt"].config(text="🎙 STT ✓" if stt else "🎙 STT ·", fg=p["ok"] if stt else p["dim"], bg=p["panel"])
        self.chips["tts"].config(text="🔊 TTS ✓" if s["tts"] else "🔇 TTS ·", fg=p["ok"] if s["tts"] else p["dim"], bg=p["panel"])
        if s["llm_enabled"] and s["llm"]:
            self.chips["llm"].config(text="🧠 LLM ✓", fg=p["ok"], bg=p["panel"])
        elif s["llm"]:
            self.chips["llm"].config(text="🧠 LLM off", fg=p["warn"], bg=p["panel"])
        else:
            self.chips["llm"].config(text="⚡ Rules", fg=p["accent"], bg=p["panel"])

    # ------------------------------------------------------------ commands
    def _on_enter(self) -> None:
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self.history.append(text)
        self._hist_i = None
        self._on_input_changed()
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
        self._on_input_changed()

    def _submit(self, text: str) -> None:
        self._post("you", text, "YOU ›", stream=False)
        threading.Thread(target=self._worker, args=(text,), daemon=True).start()

    def _worker(self, text: str) -> None:
        self._q.put(("busy", True))
        ok = False
        try:
            res = self.engine.run(text)
            ok = res.ok
            if res.command:
                self._q.put(("post", "cmd", f"   ↳ {res.command}", None))
            tag = "thans" if res.ok else "sys"
            badge = "THANS ›" if res.ok else "NOTICE ›"
            self._q.put(("post", tag, res.message, badge))
            if self.cfg.get("tts"):
                self.speaker.say(res.message)
        except Exception:  # noqa: BLE001
            self._q.put(("post", "sys", "Internal error:\n" + traceback.format_exc(limit=4), "ERROR ›"))
        finally:
            self._q.put(("done", ok))

    # ------------------------------------------------------------ command palette (Ctrl+K)
    def _open_palette(self) -> None:
        p = self.palette
        dlg = tk.Toplevel(self.root)
        dlg.title("Command Palette")
        dlg.geometry("540x400")
        dlg.configure(bg=p["panel"])
        dlg.transient(self.root)
        dlg.grab_set()

        tk.Label(
            dlg, text="⌘ Quick Command Palette — type to filter, Enter to select",
            font=FONT_SM_B, bg=p["panel"], fg=p["dim"], anchor="w",
        ).pack(fill="x", padx=14, pady=(12, 6))

        q_var = tk.StringVar()
        q_entry = tk.Entry(
            dlg, textvariable=q_var, font=MONO, bg=p["panel2"], fg=p["fg"],
            insertbackground=p["fg"], relief="flat", bd=6,
        )
        q_entry.pack(fill="x", padx=14, pady=(0, 8))
        q_entry.focus_set()

        lb = tk.Listbox(
            dlg, font=MONO_S, bg=p["panel2"], fg=p["fg"], bd=0, relief="flat",
            highlightthickness=0, selectbackground=p["accent"], selectforeground="#ffffff",
        )
        lb.pack(fill="both", expand=True, padx=14, pady=(0, 12))

        filtered: list[dict[str, str]] = []

        def refresh_list(*_args) -> None:
            q = q_var.get().strip().lower()
            lb.delete(0, "end")
            filtered.clear()
            for item in ux.COMMAND_CATALOG:
                if not q or q in item["label"].lower() or q in item["desc"].lower() or q in item["fill"].lower():
                    filtered.append(item)
                    lb.insert("end", f" {item['label']:<22}  {item['desc']}")
            if filtered:
                lb.selection_set(0)

        def choose(_event=None) -> None:
            sel = lb.curselection()
            if not sel or not filtered:
                return
            chosen = filtered[sel[0]]
            dlg.destroy()
            if chosen["cmd"]:
                self._submit(chosen["cmd"])
            else:
                self._prefill_input(chosen["fill"])

        q_var.trace_add("write", refresh_list)
        q_entry.bind("<Return>", choose)
        q_entry.bind("<Escape>", lambda _e: dlg.destroy())
        q_entry.bind("<Down>", lambda _e: (lb.focus_set(), lb.selection_set(0)))
        lb.bind("<Return>", choose)
        lb.bind("<Double-Button-1>", choose)
        lb.bind("<Escape>", lambda _e: dlg.destroy())
        refresh_list()

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
                "⚠ VOICE",
            )
            return
        ok = self.stt.start(on_final=self._voice_final, on_state=self._mic_state_cb)
        if ok:
            self._q.put(("mic", True))

    def _mic_state_cb(self, msg: str) -> None:
        self._q.put(("mic_state", msg))

    def _voice_final(self, text: str) -> None:
        self._q.put(("mic", False))
        self._q.put(("voice", text))

    # --------------------------------------------------------------- other
    def _pick_root(self) -> None:
        d = filedialog.askdirectory(
            initialdir=str(self.engine.root),
            title="Choose the working folder THANS may manage",
        )
        if not d:
            return
        self.cfg["root"] = d
        config.save_config(self.cfg)
        self.engine.set_root(d)
        self._refresh_chips()
        self._refresh_workspace()
        self._set_status(f"Working folder: {d}")
        self._post("sys", f"All file operations are now confined to: {d}", "📂 ROOT")

    def _download_models(self) -> None:
        if self._downloading:
            return
        if messagebox.askyesno(
            APP_NAME,
            "Download offline models?\n\n• STT model (Vosk) ≈ 40 MB\n"
            "• LLM model (Qwen2.5-0.5B) ≈ 408 MB\n\n"
            "One-time; THANS then runs with no internet at all.",
        ):
            self._start_download()

    def _start_download(self) -> None:
        self._downloading = True
        self.btn_dl.config(state="disabled")
        self._post("sys", "Downloading offline models (one-time; needs internet)…", "⬇ MODELS")

        def job() -> None:
            script = config.app_root() / "scripts" / "download_models.py"
            py = shutil.which("python3") or shutil.which("python") or sys.executable
            try:
                proc = subprocess.Popen(
                    [py, str(script), "--dir", str(config.models_dir())],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, cwd=str(config.app_root()),
                )
                assert proc.stdout is not None
                for line in proc.stdout:
                    line = line.rstrip()
                    if line:
                        self._q.put(("post", "sys", line, None))
                code = proc.wait()
            except Exception as e:  # noqa: BLE001
                code = -1
                self._q.put(("post", "sys", f"Could not start downloader: {e}", None))
            self._q.put((
                "post", "sys",
                "Download finished — voice input ready." if code == 0
                else f"Download failed (code {code}). Check the network and retry.",
                None,
            ))
            self._q.put(("downloading", False))
            self._q.put(("chips",))

        threading.Thread(target=job, daemon=True).start()

    def _settings(self) -> None:
        p = self.palette
        dlg = tk.Toplevel(self.root)
        dlg.title("THANS Settings")
        dlg.configure(bg=p["panel"])
        dlg.resizable(False, False)
        pad = dict(padx=14, pady=6)

        tk.Label(
            dlg, text="Working folder (THANS can only touch this)",
            bg=p["panel"], fg=p["dim"], font=FONT_SM_B,
        ).pack(anchor="w", **pad)
        f1 = tk.Frame(dlg, bg=p["panel"])
        f1.pack(fill="x", **pad)
        var_root = tk.StringVar(value=str(self.engine.root))
        tk.Entry(
            f1, textvariable=var_root, font=MONO, bg=p["panel2"], fg=p["fg"],
            insertbackground=p["fg"], relief="flat",
        ).pack(side="left", fill="x", expand=True, ipady=4)

        def browse() -> None:
            d = filedialog.askdirectory(initialdir=var_root.get())
            if d:
                var_root.set(d)

        ttk.Button(f1, text="Browse", command=browse).pack(side="left", padx=(6, 0))

        f_theme = tk.Frame(dlg, bg=p["panel"])
        f_theme.pack(fill="x", **pad)
        tk.Label(f_theme, text="Theme:", bg=p["panel"], fg=p["dim"], font=FONT_SM_B).pack(side="left")
        var_theme = tk.StringVar(value=self.theme_name)
        ttk.Combobox(
            f_theme, textvariable=var_theme, values=ux.THEME_ORDER, state="readonly", width=16,
        ).pack(side="left", padx=(10, 0))

        var_tts = tk.BooleanVar(value=bool(self.cfg.get("tts")))
        tk.Checkbutton(
            dlg, text="Speak replies (TTS)", variable=var_tts,
            bg=p["panel"], fg=p["fg"], activebackground=p["panel"],
            activeforeground=p["fg"], selectcolor=p["panel2"],
        ).pack(anchor="w", **pad)

        f2 = tk.Frame(dlg, bg=p["panel"])
        f2.pack(fill="x", **pad)
        tk.Label(f2, text="Speech rate:", bg=p["panel"], fg=p["dim"]).pack(side="left")
        var_rate = tk.IntVar(value=int(self.cfg.get("tts_rate", 185)))
        ttk.Scale(f2, from_=110, to=280, variable=var_rate, orient="horizontal", length=220).pack(side="left", padx=(8, 0))

        var_llm = tk.BooleanVar(value=bool(self.cfg.get("use_llm")))
        tk.Checkbutton(
            dlg, text="Use offline LLM for free-form commands (optional)",
            variable=var_llm, bg=p["panel"], fg=p["fg"], activebackground=p["panel"],
            activeforeground=p["fg"], selectcolor=p["panel2"],
        ).pack(anchor="w", **pad)

        tk.Label(
            dlg, text="LLM model (models/*.gguf):", bg=p["panel"], fg=p["dim"], font=FONT_SM,
        ).pack(anchor="w", **pad)
        ggufs = [m.name for m in model_manager.all_gguf()]
        cur = self.cfg.get("llm_model", "")
        if cur and cur not in ggufs:
            ggufs = [cur] + ggufs
        var_llm_model = tk.StringVar(value=cur)
        ttk.Combobox(dlg, textvariable=var_llm_model, values=ggufs or [cur], state="readonly").pack(fill="x", **pad)

        var_perm = tk.BooleanVar(value=bool(self.cfg.get("permanent_delete")))
        tk.Checkbutton(
            dlg, text="Danger: deletes bypass the trash (permanent)",
            variable=var_perm, bg=p["panel"], fg=p["warn"], activebackground=p["panel"],
            activeforeground=p["warn"], selectcolor=p["panel2"],
        ).pack(anchor="w", **pad)

        def save() -> None:
            cfg = self.cfg
            cfg["root"] = var_root.get().strip() or cfg["root"]
            cfg["theme"] = var_theme.get().strip() or "obsidian"
            cfg["tts"] = bool(var_tts.get())
            cfg["tts_rate"] = int(var_rate.get())
            cfg["use_llm"] = bool(var_llm.get())
            cfg["llm_model"] = var_llm_model.get().strip() or cfg.get("llm_model", "")
            cfg["permanent_delete"] = bool(var_perm.get())
            config.save_config(cfg)
            self.cfg = cfg
            self.theme_name = cfg["theme"]
            self.palette = ux.get_theme(self.theme_name)
            self.engine = Engine(cfg["root"], cfg)
            self.speaker.enabled = cfg["tts"]
            self.speaker.set_rate(int(cfg["tts_rate"]))
            self._apply_theme()
            self._set_status(f"Working folder: {self.engine.root}")
            self._post("sys", "Settings saved.", "⚙ SETTINGS")
            dlg.destroy()

        ttk.Button(dlg, text="Save Settings", style="Accent.TButton", command=save).pack(pady=(10, 14))
        dlg.grab_set()
        dlg.transient(self.root)

    # ---------------------------------------------------------------- misc
    def _on_close(self) -> None:
        try:
            self.speaker.stop()
        except Exception:
            pass
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()

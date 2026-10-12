"""App-level panels: boot animation, dashboard cards, settings slide-over.

Everything here is built from ``ui/widgets`` + ``ui/theme`` so the whole window
shares one visual language. Panels never touch the engine directly — the app
passes callbacks in, which keeps file work on the worker thread.
"""
from __future__ import annotations

import os
import shutil
import threading
import tkinter as tk
import queue
from pathlib import Path
from tkinter import ttk
from typing import Callable, Optional

from .. import config
from . import logic
from . import theme as T
from .widgets import (Card, Chip, IconButton, ProgressBar, RoundedButton, SlidePanel,
                      Switch, Tooltip, Waveform, draw_round_rect, widget_bg)


# ==========================================================================
# boot overlay
# ==========================================================================

class BootOverlay(tk.Canvas):
    """Full-window start screen: mark punch-in, gradient sweep, real init steps.

    The steps are *actually executed* while the animation plays, so the app has
    finished loading by the time the overlay fades — no fake progress bar.
    """

    def __init__(self, master, animator, fonts, steps: list[tuple[str, Callable[[], None]]],
                 on_done: Callable[[], None], bg=T.BG):
        super().__init__(master, bg=bg, highlightthickness=0, bd=0)
        self.anim = animator
        self.fonts = fonts
        self.steps = list(steps)
        self.on_done = on_done
        self.bg = bg
        self._items: list[int] = []
        self._t0 = 0.0
        self._finished = False
        self._status = "starting…"
        self._sweep = 0.0
        self._sweep_tw = None
        self.bind("<Configure>", lambda e: self._draw())

    # ------------------------------------------------------------- lifecycle
    def start(self) -> None:
        self.place(x=0, y=0, relwidth=1, relheight=1)
        self.lift()
        self._draw()
        if self.anim is None:
            self._run_steps_sync()
            return
        # mark + wordmark punch-in
        self.anim.add(logic.Tween(0.62, easing=logic.out_back,
                                  on_update=lambda v: self._set_slide(v)))
        self.anim.add(logic.Tween(0.45, delay=0.18, on_update=lambda v: self._set_sub(v)))
        self._sweep_tw = logic.sweep(1.5, on_update=self._set_sweep)
        self.anim.add(self._sweep_tw)
        self._schedule_steps(delay_ms=340)

    def _schedule_steps(self, delay_ms: int) -> None:
        gap = max(90, int(620 / max(1, len(self.steps))))
        for i, (label, fn) in enumerate(self.steps):
            self.after(delay_ms + i * gap, lambda l=label, f=fn, last=(i == len(self.steps) - 1):
                       self._step(l, f, last))

    def _step(self, label: str, fn: Callable[[], None], last: bool) -> None:
        self._status = label
        self._draw()
        try:
            fn()
        except Exception:                      # never block startup on a panic
            pass
        if last:
            self.after(160, self._finish)

    def _run_steps_sync(self) -> None:
        for label, fn in self.steps:
            try:
                fn()
            except Exception:
                pass
        self._dismiss()

    # -------------------------------------------------------------- animation
    def _set_slide(self, v: float) -> None:
        self._t0 = v
        self._draw()

    def _set_sub(self, v: float) -> None:
        self._sub_t = v
        self._draw()

    def _set_sweep(self, v: float) -> None:
        self._sweep = v
        self._draw()

    def _finish(self) -> None:
        if self._finished:
            return
        self._finished = True
        self._status = "ready"
        if self._sweep_tw is not None:
            self.anim.stop(self._sweep_tw) if self.anim else None
            self._sweep_tw = None
        self.after(120, lambda: self.anim.add(logic.Tween(0.34, on_update=self._fade_out,
                                                         on_done=self._dismiss))
                   if self.anim else self._dismiss())

    def _fade_out(self, v: float) -> None:
        if not self.winfo_exists():
            return
        for item in self.find_all():
            try:
                kind = self.type(item)
                if kind in ("text", "rectangle", "oval", "polygon"):
                    cur = self.itemcget(item, "fill")
                    self.itemconfigure(item, fill=T.mix(cur, self.bg, v))
                elif kind == "line":
                    cur = self.itemcget(item, "fill")
                    self.itemconfigure(item, fill=T.mix(cur, self.bg, v))
            except tk.TclError:
                continue
        if v >= 1.0:
            self._dismiss()

    def _dismiss(self) -> None:
        try:
            self.destroy()
        except Exception:
            pass
        self.on_done()

    # ------------------------------------------------------------------ paint
    def _draw(self) -> None:
        if not self.winfo_exists():
            return
        self.delete("all")
        w, h = max(2, self.winfo_width()), max(2, self.winfo_height())
        cx, cy = w / 2, h / 2
        t0 = getattr(self, "_t0", 0.0)
        sub_t = max(0.0, min(1.0, getattr(self, "_sub_t", 0.0)))

        # brand mark: rounded square grows in with the wordmark
        m = 34 * (0.55 + 0.45 * t0)
        x0, y0 = cx - m / 2, cy - 108 - m / 2
        mark_fill = T.mix(self.bg, T.mix(T.ACCENT, T.ACCENT2, 0.5), min(1.0, t0 * 1.4))
        draw_round_rect(self, x0, y0, x0 + m, y0 + m, m * 0.30, mark_fill)
        self.create_text(cx, y0 + m / 2, text=T.SYM["sparkle"], fill="#ffffff",
                         font=(self.fonts.get("ui", "TkDefaultFont"), int(max(8, m * 0.5))))

        # wordmark: font size eases up for a "punch-in"
        size = int(12 + 24 * t0)
        self.create_text(cx, cy - 40, text="THANS", fill=T.mix(self.bg, T.FG, min(1.0, t0 * 1.3)),
                         font=(self.fonts.get("ui", "TkDefaultFont"), size, "bold"))
        self.create_text(cx, cy - 6, text="offline voice & text file assistant",
                         fill=T.mix(self.bg, T.FG_DIM, sub_t),
                         font=(self.fonts.get("ui", "TkDefaultFont"), T.SIZE_SMALL))

        # gradient sweep bar
        bar_w, bar_h = min(300, w * 0.6), 6
        bx, by = cx - bar_w / 2, cy + 44
        draw_round_rect(self, bx, by, bx + bar_w, by + bar_h, bar_h / 2,
                        T.mix(T.SURFACE_HI, self.bg, 0.35))
        span = bar_w * 0.34
        x = bx + self._sweep * (bar_w - span)
        for i in range(int(span)):
            col = T.mix(T.ACCENT, T.ACCENT2, i / max(1, span))
            self.create_line(x + i, by, x + i, by + bar_h, fill=col)
        # round the sweep ends
        for off, col in ((0, T.ACCENT), (span, T.ACCENT2)):
            self.create_oval(x + off - bar_h / 2, by, x + off + bar_h / 2, by + bar_h,
                             fill=col, outline="")

        # status line
        self.create_text(cx, by + 30, text=self._status,
                         fill=T.mix(self.bg, T.FG_FAINT, max(0.2, sub_t)),
                         font=(self.fonts.get("ui", "TkDefaultFont"), T.SIZE_SMALL))


# ==========================================================================
# dashboard cards
# ==========================================================================

class FolderCard(Card):
    """Working-folder dashboard: files · folders · size, scanned in background."""

    def __init__(self, master, animator, fonts, on_open: Optional[Callable[[], None]] = None,
                 on_rescan: Optional[Callable[[], None]] = None):
        super().__init__(master, animator=animator, fill=T.SURFACE, radius=T.RADIUS_LG,
                         padding=T.PAD)
        self.anim = animator
        self.fonts = fonts
        self.on_open = on_open
        self._q: queue.Queue = queue.Queue()
        self._stat_labels: dict[str, tk.Label] = {}
        self._shown = {"files": 0.0, "folders": 0.0, "size": 0.0}
        self._target = {"files": 0, "folders": 0, "size": 0}

        head = tk.Frame(self.body, bg=T.SURFACE)
        head.pack(fill="x")
        tk.Label(head, text="WORKING FOLDER", bg=T.SURFACE, fg=T.FG_FAINT,
                 font=(fonts["ui"], T.SIZE_TINY, "bold")).pack(side="left")
        self.btn_open = RoundedButton(head, text="Open", glyph=T.SYM["folder"],
                                      command=on_open, animator=animator, subtle=True,
                                      pad_x=8, pad_y=3, font=(fonts["ui"], T.SIZE_TINY),
                                      bg=T.SURFACE)
        self.btn_open.pack(side="right")

        self.path_lbl = tk.Label(self.body, text="—", bg=T.SURFACE, fg=T.FG,
                                 font=(fonts["small_bold"]), anchor="w", justify="left")
        self.path_lbl.pack(fill="x", pady=(6, 0))

        stats = tk.Frame(self.body, bg=T.SURFACE)
        stats.pack(fill="x", pady=(10, 2))
        for i, (key, label) in enumerate((("files", "files"), ("folders", "folders"),
                                         ("size", "total size"))):
            col = tk.Frame(stats, bg=T.SURFACE)
            col.pack(side="left", expand=True, fill="x")
            val = tk.Label(col, text="0", bg=T.SURFACE, fg=T.FG,
                           font=(fonts["ui"], 16, "bold"))
            val.pack(anchor="w")
            tk.Label(col, text=label, bg=T.SURFACE, fg=T.FG_FAINT,
                     font=(fonts["ui"], T.SIZE_TINY)).pack(anchor="w")
            self._stat_labels[key] = val

        self.bar = ProgressBar(self.body, animator=animator, height=5)
        self.bar.pack(fill="x", pady=(10, 4))
        self.free_lbl = tk.Label(self.body, text="", bg=T.SURFACE, fg=T.FG_DIM,
                                 font=(fonts["tiny"]), anchor="w", justify="left")
        self.free_lbl.pack(fill="x")

    # ------------------------------------------------------------------ data
    def set_root(self, root: Path) -> None:
        text = logic.truncate(str(root), 42)
        self.path_lbl.configure(text=text)
        try:
            Tooltip(self.path_lbl, str(root), font=(self.fonts["ui"], T.SIZE_TINY))
        except Exception:
            pass
        self.refresh(root)

    def refresh(self, root: Path) -> None:
        """Kick off a background scan (safe to call often)."""
        self.bar.start_indeterminate(1.8)
        self.free_lbl.configure(text="scanning…")
        threading.Thread(target=self._scan, args=(Path(root),), daemon=True).start()

    def _scan(self, root: Path) -> None:
        files = folders = 0
        size = 0
        try:
            for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: None):
                # never count the trash folder as part of the user's own library
                dirnames[:] = [d for d in dirnames if d != config.TRASH_DIRNAME]
                folders += len(dirnames)
                files += len(filenames)
                for fn in filenames:
                    try:
                        size += os.path.getsize(os.path.join(dirpath, fn))
                    except OSError:
                        pass
                if files > 60000:            # keep the UI snappy on huge trees
                    break
        except Exception:
            pass
        try:
            usage = shutil.disk_usage(str(root))
        except Exception:
            usage = None
        self._q.put((files, folders, size, usage))

    def poll(self) -> None:
        """Drain scan results (called from the app's animation tick)."""
        try:
            while True:
                files, folders, size, usage = self._q.get_nowait()
                self._target = {"files": files, "folders": folders, "size": float(size)}
                self.bar.stop_indeterminate()
                if usage:
                    used_pct = usage.used / max(1, usage.total)
                    self.bar.set(used_pct)
                    label, state = logic.grade_health(used_pct)
                    self.free_lbl.configure(
                        text=f"{logic.format_bytes(usage.free)} free of "
                             f"{logic.format_bytes(usage.total)} · {label}",
                        fg={"ok": T.FG_DIM, "warn": T.WARN, "error": T.ERR}[state])
                else:
                    self.free_lbl.configure(text="disk info unavailable", fg=T.FG_FAINT)
        except queue.Empty:
            return

    def tick(self, dt: float) -> None:
        """Count-up animation for the stats (driven by the app's loop)."""
        for key, lbl in self._stat_labels.items():
            shown, target = self._shown[key], self._target.get(key, 0)
            if abs(shown - target) < 0.5:
                self._shown[key] = float(target)
            else:
                self._shown[key] += (target - shown) * min(1.0, dt * 7.0)
            val = self._shown[key]
            text = logic.format_bytes(int(val)) if key == "size" else f"{int(round(val)):,}"
            if lbl.cget("text") != text:
                lbl.configure(text=text)


class QuickCard(Card):
    """Two-click actions for the things people do most."""

    def __init__(self, master, animator, fonts, actions: list[tuple[str, str, str, str]]):
        """``actions``: (glyph, label, tooltip, command-id)"""
        super().__init__(master, animator=animator, fill=T.SURFACE, radius=T.RADIUS_LG,
                         padding=T.PAD)
        tk.Label(self.body, text="QUICK ACTIONS", bg=T.SURFACE, fg=T.FG_FAINT,
                 font=(fonts["ui"], T.SIZE_TINY, "bold")).pack(anchor="w")
        grid = tk.Frame(self.body, bg=T.SURFACE)
        grid.pack(fill="x", pady=(8, 0))
        self.buttons: dict[str, RoundedButton] = {}
        for i, (glyph, label, tip, key) in enumerate(actions):
            b = RoundedButton(grid, text=label, glyph=glyph, command=None, animator=animator,
                              subtle=True, pad_x=8, pad_y=6,
                              font=(fonts["ui"], T.SIZE_SMALL), bg=T.SURFACE)
            b.grid(row=i // 2, column=i % 2, sticky="ew", padx=(0, 6), pady=3)
            grid.columnconfigure(i % 2, weight=1)
            Tooltip(b, tip, font=(fonts["ui"], T.SIZE_TINY))
            self.buttons[key] = b


class VoiceCard(Card):
    """Waveform + spoken-reply toggle."""

    def __init__(self, master, animator, fonts, on_speak_toggle: Callable[[bool], None],
                 speak_on: bool = False):
        super().__init__(master, animator=animator, fill=T.SURFACE, radius=T.RADIUS_LG,
                         padding=T.PAD)
        tk.Label(self.body, text="VOICE", bg=T.SURFACE, fg=T.FG_FAINT,
                 font=(fonts["ui"], T.SIZE_TINY, "bold")).pack(anchor="w")

        row = tk.Frame(self.body, bg=T.SURFACE)
        row.pack(fill="x", pady=(8, 2))
        self.wave = Waveform(row, animator=animator, bg=T.SURFACE, width=96, height=26)
        self.wave.pack(side="left")
        self.state_lbl = tk.Label(row, text="mic idle · F2 to talk", bg=T.SURFACE,
                                  fg=T.FG_DIM, font=(fonts["tiny"]), anchor="w",
                                  justify="left", wraplength=150)
        self.state_lbl.pack(side="left", padx=(10, 0))

        row2 = tk.Frame(self.body, bg=T.SURFACE)
        row2.pack(fill="x", pady=(8, 0))
        tk.Label(row2, text="Speak replies", bg=T.SURFACE, fg=T.FG,
                 font=(fonts["small"])).pack(side="left")
        self.sw_speak = Switch(row2, value=speak_on, command=on_speak_toggle,
                               animator=animator, bg=T.SURFACE)
        self.sw_speak.pack(side="right")

    def set_state(self, text: str, listening: bool, level: float = 0.0) -> None:
        self.state_lbl.configure(text=text, fg=T.ACCENT_HI if listening else T.FG_DIM)
        if listening:
            self.wave.start()
            self.wave.set_level(level)
        else:
            self.wave.stop()


# ==========================================================================
# help sheet
# ==========================================================================

class HelpPanel(SlidePanel):
    """Slide-over command reference — every row is runnable with one tap.

    Rows come from ``engine.COMMAND_REFERENCE``, so the help can never fall
    behind the parser: add a command there and it appears here and in the CLI.
    """

    def __init__(self, host: tk.Frame, animator, fonts, on_run: Callable[[str], None],
                 examples: Optional[dict[str, str]] = None,
                 on_close: Optional[Callable[[], None]] = None, width: int = 380):
        super().__init__(host, width=width, animator=animator)
        self.fonts = fonts
        self.on_run = on_run
        self.on_close_cb = on_close
        self.rows: list[tuple[str, RoundedButton]] = []
        self.buttons: list[RoundedButton] = []

        head = tk.Frame(self, bg=T.BG_RAISED)
        head.pack(fill="x", padx=T.PAD, pady=(T.PAD, 2))
        tk.Label(head, text="What THANS can do", bg=T.BG_RAISED, fg=T.FG,
                 font=(fonts["ui"], T.SIZE_TITLE, "bold")).pack(side="left")
        IconButton(head, glyph=T.SYM["cross"], command=self.close, animator=animator,
                   bg=T.BG_RAISED, size=30).pack(side="right")
        tk.Label(self, text="Tap any example to put it in the box (then ⏎).",
                 bg=T.BG_RAISED, fg=T.FG_DIM, font=fonts["small"]).pack(
            anchor="w", padx=T.PAD, pady=(0, 6))

        card = Card(self, animator=animator, fill=T.SURFACE, radius=T.RADIUS_LG,
                    padding=T.PAD_S)
        card.pack(fill="both", expand=True, padx=T.PAD_S, pady=(0, T.PAD))
        body = card.body

        from ..engine import COMMAND_REFERENCE
        for i, (action, example, blurb) in enumerate(COMMAND_REFERENCE):
            row = tk.Frame(body, bg=T.SURFACE)
            row.pack(fill="x", pady=3)
            glyph = {
                "list": T.SYM["list"], "mkdir": T.SYM["folder"], "touch": T.SYM["doc"],
                "delete": T.SYM["cross"], "search": T.SYM["search"],
                "open": T.SYM["play"], "organize": T.SYM["wand"], "cd": T.SYM["home"],
                "undo": T.SYM["undo"], "rename": T.SYM["keyboard"],
                "copy": T.SYM["doc"], "move": T.SYM["folder"], "help": T.SYM["sparkle"],
            }.get(action, T.SYM["sparkle"])
            b = RoundedButton(row, text=example, glyph=glyph, animator=animator,
                              command=lambda ex=example: self._run_example(ex),
                              subtle=True, pad_x=8, pad_y=5,
                              font=fonts["small"], bg=T.SURFACE)
            b.pack(fill="x")
            Tooltip(b, blurb, font=fonts["tiny"])
            if i:
                self.rows.append((action, b))
            self.buttons.append(b)
            tk.Label(row, text=blurb, bg=T.SURFACE, fg=T.FG_FAINT, font=fonts["tiny"],
                     anchor="w").pack(fill="x", padx=10)

        tk.Label(self, text=f"{logic.keys_hint()}", bg=T.BG_RAISED, fg=T.FG_FAINT,
                 font=fonts["tiny"], wraplength=width - 30, justify="left").pack(
            anchor="w", padx=T.PAD, pady=(0, T.PAD))

    def _run_example(self, example: str) -> None:
        # turn an example into something runnable: keep the first comma-separated
        # variant and drop the parts in <angle brackets> guidance shape
        first = example.split("·")[0].strip()
        if "<" in first:
            first = first.split("<")[0].rstrip()
        self.on_run(first)
        self.close()

    def close(self) -> None:
        super().close()
        if self.on_close_cb:
            self.on_close_cb()


# ==========================================================================
# settings slide-over
# ==========================================================================

class SettingsPanel(SlidePanel):
    """Right-hand settings sheet — every change is applied and saved live."""

    def __init__(self, host: tk.Frame, animator, fonts, cfg: dict,
                 on_change: Callable[[str, object], None],
                 on_pick_root: Callable[[], None],
                 on_download: Callable[[], None],
                 on_close: Optional[Callable[[], None]] = None,
                 width: int = 360):
        super().__init__(host, width=width, animator=animator)
        self.fonts = fonts
        self.cfg = dict(cfg)
        self.on_change = on_change
        self.on_close_cb = on_close
        self.widgets: dict[str, tk.Widget] = {}

        self.inner = tk.Frame(self, bg=T.BG_RAISED)
        self.inner.pack(fill="both", expand=True)

        head = tk.Frame(self.inner, bg=T.BG_RAISED)
        head.pack(fill="x", padx=T.PAD, pady=(T.PAD, 4))
        tk.Label(head, text="Settings", bg=T.BG_RAISED, fg=T.FG,
                 font=(fonts["ui"], T.SIZE_TITLE, "bold")).pack(side="left")
        IconButton(head, glyph=T.SYM["cross"], command=self.close, animator=animator,
                   primary=False, bg=T.BG_RAISED, size=30).pack(side="right")

        body = tk.Frame(self.inner, bg=T.BG_RAISED)
        body.pack(fill="both", expand=True, padx=T.PAD, pady=(6, T.PAD))

        # ---- working folder
        self._section(body, "Working folder")
        self.widgets["root"] = tk.Label(body, text=logic.truncate(str(self.cfg.get("root")), 40),
                                        bg=T.BG_RAISED, fg=T.FG, font=fonts["small"],
                                        anchor="w", justify="left", wraplength=width - 40)
        self.widgets["root"].pack(fill="x", pady=(0, 6))
        row = tk.Frame(body, bg=T.BG_RAISED)
        row.pack(fill="x", pady=(0, 10))
        RoundedButton(row, text="Change…", glyph=T.SYM["folder"], command=on_pick_root,
                      animator=animator, subtle=True, pad_x=10, pad_y=5,
                      font=fonts["small"], bg=T.BG_RAISED).pack(side="left")
        Tooltip(row.winfo_children()[-1], "All file operations stay inside this folder",
                font=fonts["tiny"])

        # ---- voice
        self._section(body, "Voice")
        self._switch_row(body, "Speak replies", "tts", bool(self.cfg.get("tts")),
                         "Read results aloud with the system voice")
        self._segment(body, "Speech rate", "tts_rate",
                      [("Slow", 150), ("Normal", 185), ("Fast", 220)],
                      int(self.cfg.get("tts_rate", 185)), "tts_rate")
        self._switch_row(body, "Animations", "motion", bool(self.cfg.get("motion", True)),
                         "Smooth motion; turn off for instant, flat UI")

        # ---- optional model
        self._section(body, "Optional offline model")
        self._switch_row(body, "Free-form parsing (LLM)", "use_llm",
                         bool(self.cfg.get("use_llm")),
                         "Understands loose phrasing. Needs a GGUF model + llama-cpp-python")
        models = self._available_models()
        self.widgets["llm_model"] = self._model_list(body, models)
        self.dl_btn = RoundedButton(body, text="Download models", glyph=T.SYM["models"],
                                    command=on_download, animator=animator, subtle=True,
                                    pad_x=10, pad_y=6, font=fonts["small"], bg=T.BG_RAISED)
        self.dl_btn.pack(anchor="w", pady=(6, 4))
        self.dl_bar = ProgressBar(body, animator=animator, height=5)
        self.dl_bar.pack(fill="x")
        self.dl_lbl = tk.Label(body, text="", bg=T.BG_RAISED, fg=T.FG_FAINT,
                               font=fonts["tiny"], anchor="w")
        self.dl_lbl.pack(fill="x", pady=(2, 0))

        # ---- safety
        self._section(body, "Safety")
        self._switch_row(body, "Delete permanently", "permanent_delete",
                         bool(self.cfg.get("permanent_delete")),
                         "Skip the trash folder — deletions cannot be undone",
                         danger=True)

        tk.Label(body, text=f"THANS knows {len(logic.TEMPLATES)} command shapes — "
                            "press F1 to see them all.",
                 bg=T.BG_RAISED, fg=T.FG_FAINT, font=fonts["tiny"], wraplength=width - 40,
                 justify="left").pack(anchor="w", pady=(14, 0))

    # ------------------------------------------------------------- helpers
    def _section(self, parent, title: str) -> None:
        tk.Frame(parent, bg=T.BORDER, height=1).pack(fill="x", pady=(10, 8))
        tk.Label(parent, text=title.upper(), bg=T.BG_RAISED, fg=T.FG_FAINT,
                 font=(self.fonts["ui"], T.SIZE_TINY, "bold")).pack(anchor="w")

    def _switch_row(self, parent, label: str, key: str, value: bool, tip: str = "",
                    danger: bool = False) -> Switch:
        row = tk.Frame(parent, bg=T.BG_RAISED)
        row.pack(fill="x", pady=5)
        lbl = tk.Label(row, text=label, bg=T.BG_RAISED,
                       fg=T.ERR if danger else T.FG, font=self.fonts["small"])
        lbl.pack(side="left")
        sw = Switch(row, value=value, animator=self.anim,
                    command=lambda v, k=key: self._changed(k, v), bg=T.BG_RAISED)
        sw.pack(side="right")
        if tip:
            Tooltip(lbl, tip, font=self.fonts["tiny"])
        self.widgets[key] = sw
        return sw

    def _segment(self, parent, label: str, key: str, options: list[tuple[str, object]],
                 value: object, cfg_key: str) -> None:
        row = tk.Frame(parent, bg=T.BG_RAISED)
        row.pack(fill="x", pady=5)
        tk.Label(row, text=label, bg=T.BG_RAISED, fg=T.FG,
                 font=self.fonts["small"]).pack(side="left")
        group = tk.Frame(row, bg=T.BG_RAISED)
        group.pack(side="right")
        for text, val in options:
            primary = (val == value)
            b = RoundedButton(group, text=text, animator=self.anim,
                              command=lambda v=val, k=cfg_key: self._changed(k, v),
                              primary=primary, subtle=not primary, pad_x=9, pad_y=4,
                              font=self.fonts["tiny"], bg=T.BG_RAISED)
            b.pack(side="left", padx=2)
        self.widgets[key] = group

    def _available_models(self) -> list[str]:
        from .. import config, model_manager
        found = [p.name for p in model_manager.all_gguf()]
        if config.DEFAULT_LLM_MODEL not in found:
            found.insert(0, config.DEFAULT_LLM_MODEL)
        return found

    def _model_list(self, parent, models: list[str]) -> tk.Frame:
        wrap = tk.Frame(parent, bg=T.BG_RAISED)
        wrap.pack(fill="x", pady=(4, 0))
        current = self.cfg.get("llm_model")
        for i, name in enumerate(models):
            from .. import config, model_manager
            installed = (config.models_dir() / name).is_file()
            label = f"{logic.truncate(name.replace('.gguf', ''), 30)}" + ("" if installed else "  (not downloaded)")
            b = RoundedButton(wrap, text=label, glyph=T.SYM["check"] if name == current else "",
                              animator=self.anim,
                              command=lambda n=name: self._changed("llm_model", n),
                              primary=(name == current), subtle=(name != current),
                              pad_x=9, pad_y=5,
                              font=self.fonts["tiny"], bg=T.BG_RAISED)
            b.pack(fill="x", pady=2)
            if not installed:
                Tooltip(b, "python scripts/download_models.py --only llm", font=self.fonts["tiny"])
        return wrap

    def _changed(self, key: str, value) -> None:
        self.cfg[key] = value
        self.on_change(key, value)

    def set_root_label(self, path: str) -> None:
        self.widgets["root"].configure(text=logic.truncate(path, 40))

    def set_download(self, text: str, fraction: Optional[float] = None) -> None:
        self.dl_lbl.configure(text=text)
        if fraction is None:
            self.dl_bar.start_indeterminate(1.5)
        else:
            self.dl_bar.set(fraction)

    # ----------------------------------------------------------- open/close
    def close(self) -> None:
        super().close()
        if self.on_close_cb:
            self.on_close_cb()

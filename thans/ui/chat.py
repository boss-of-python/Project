"""The THANS transcript: message bubbles, streaming replies, empty state.

Why a single ``tk.Text`` instead of a stack of widgets? Text selection, copy,
word wrap and scrolling all come for free, and per-message tags let each bubble
have its own colours — which in turn lets us *animate* a message as it arrives
(unique tag per message ⇒ its colour can be tweened without touching others).

Message anatomy::

    THANS ▎  rules                      ← header: accent rail + source chip
      Reply text, indented, wrapped…

                                    You ▎   ← right-aligned, user bubble
                                 list work
"""
from __future__ import annotations

import datetime as _dt
import tkinter as tk
from typing import Callable, Optional

from . import logic
from . import theme as T
from .widgets import CanvasWidget, draw_capsule, widget_bg


# --------------------------------------------------------------------------
# slim animated scrollbar
# --------------------------------------------------------------------------

class SlimScrollbar(CanvasWidget):
    """A 10 px rounded scroll thumb that fades out when the log fits."""

    W = 10

    def __init__(self, master, command=None, animator=None, bg=None):
        super().__init__(master, animator=animator, width=self.W, bg=bg or widget_bg(master))
        self.command = command
        self.anim = animator
        self._first, self._last = 0.0, 1.0
        self._alpha = 0.0            # 0 hidden → 1 visible
        self._hover = False
        self._drag_from = None
        self._hide_tw = None
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag_from", None))

    # ---- state from the Text widget
    def set(self, first, last) -> None:
        self._first, self._last = float(first), float(last)
        if self._last - self._first >= 0.999:          # everything visible
            self._fade_to(0.0, 0.25)
        else:
            self._fade_to(1.0, 0.15)
        self._draw()

    def _fade_to(self, target: float, dur: float) -> None:
        if self.anim is None:
            self._alpha = target
            self._draw()
            return
        start = self._alpha
        self._hide_tw = logic.Tween(dur, on_update=lambda v: self._set_alpha(
            logic.lerp(start, target, v)))
        self.anim.add(self._hide_tw)

    def _set_alpha(self, v):
        self._alpha = v
        self._draw()

    # ---- interaction
    def _on_enter(self, _e=None):
        self._hover = True
        self._fade_to(1.0, 0.12)

    def _on_leave(self, _e=None):
        self._hover = False
        if self._last - self._first >= 0.999:
            self._fade_to(0.0, 0.2)

    def _on_press(self, e):
        self._drag_from = (e.y, self._first)
        self._jump(e.y)

    def _on_drag(self, e):
        if self._drag_from is None or self.command is None:
            return
        h = max(1, self.winfo_height())
        span = max(0.02, self._last - self._first)
        dy = (e.y - self._drag_from[0]) / h
        self.command(max(0.0, min(1.0 - span, self._drag_from[1] + dy * (1 + span))))

    def _jump(self, y):
        if self.command is None:
            return
        h = max(1, self.winfo_height())
        span = max(0.02, self._last - self._first)
        self.command(max(0.0, min(1.0 - span, y / h - span / 2)))

    # ---- paint
    def _draw(self):
        if not self.winfo_exists():
            return
        self.delete("all")
        h = self.winfo_height()
        if h < 12 or self._alpha <= 0.01:
            return
        y0 = self._first * h
        y1 = max(y0 + 18, self._last * h)
        base = T.ACCENT_HI if self._hover else T.mix(T.FG_FAINT, T.ACCENT, 0.35)
        col = T.mix(widget_bg(self.master, T.BG), base, self._alpha)
        draw_capsule(self, 2, y0, self.W - 2, min(h, y1), col)


# --------------------------------------------------------------------------
# transcript
# --------------------------------------------------------------------------

class ChatLog(tk.Frame):
    """Scrollable conversation with streaming (typed-out) replies."""

    def __init__(self, master, animator, fonts: dict | None = None,
                 on_rerun: Optional[Callable[[str], None]] = None,
                 on_clear: Optional[Callable[[], None]] = None):
        super().__init__(master, bg=T.BG)
        self.anim = animator
        self.fonts = fonts or {}
        self.on_rerun = on_rerun
        self.on_clear = on_clear
        self.messages: list[dict] = []       # {"kind","text","time","ok","source"}
        self._n = 0
        self._last_user = ""
        self._last_reply = ""
        self._streams: list[dict] = []

        self.text = tk.Text(self, bg=T.BG, fg=T.FG, relief="flat", wrap="word",
                            state="disabled", padx=T.CHAT_PAD, pady=T.PAD_S,
                            spacing1=3, spacing2=3, spacing3=8, highlightthickness=0,
                            insertwidth=0, cursor="xterm", selectbackground=T.ACCENT_LO,
                            selectforeground="#ffffff", font=self.fonts.get("body"))
        self.bar = SlimScrollbar(self, command=self._on_scroll_request, animator=animator,
                                 bg=T.BG)
        self.text.configure(yscrollcommand=self.bar.set)
        self.bar.pack(side="right", fill="y", padx=(0, 2))
        self.text.pack(side="left", fill="both", expand=True)

        self._configure_tags()
        self._bind_events()
        self._scroll_tw = None

    # ---------------------------------------------------------------- tags
    def _configure_tags(self) -> None:
        t = self.text
        t.tag_configure("body", font=self.fonts.get("body"), foreground=T.FG,
                        lmargin1=14, lmargin2=14, rmargin=T.PAD)
        t.tag_configure("body_you", font=self.fonts.get("body"), foreground=T.USER_FG,
                        background=T.USER_BG, justify="right",
                        lmargin1=180, lmargin2=180, rmargin=T.PAD, spacing1=8, spacing3=12)
        t.tag_configure("hdr_you", font=self.fonts.get("small_bold"),
                        foreground=T.mix(T.USER_FG, T.BG, 0.45), justify="right",
                        lmargin1=180, lmargin2=180, rmargin=T.PAD, spacing1=10, spacing3=2)
        t.tag_configure("hdr_thans", font=self.fonts.get("small_bold"), foreground=T.ACCENT_HI,
                        lmargin1=14, lmargin2=14, spacing1=12, spacing3=2)
        t.tag_configure("hdr_sys", font=self.fonts.get("small_bold"), foreground=T.WARN,
                        lmargin1=14, lmargin2=14, spacing1=12, spacing3=2)
        t.tag_configure("sys", font=self.fonts.get("small"), foreground=T.SYS_FG,
                        lmargin1=14, lmargin2=14, background=T.SYS_BG, spacing3=8)
        t.tag_configure("meta", font=self.fonts.get("tiny"), foreground=T.FG_FAINT,
                        lmargin1=14, lmargin2=14)
        t.tag_configure("card", font=self.fonts.get("mono_small"), foreground=T.mix(T.FG, T.BG, 0.08),
                        background=T.SURFACE, lmargin1=T.PAD, lmargin2=T.PAD, rmargin=T.PAD,
                        spacing1=4, spacing3=4, borderwidth=0)
        t.tag_configure("rail", foreground=T.ACCENT)
        t.tag_configure("rail_ok", foreground=T.OK)
        t.tag_configure("rail_err", foreground=T.ERR)
        t.tag_configure("caret", foreground=T.ACCENT_HI)
        t.tag_configure("bullet", foreground=T.ACCENT)

    def _bind_events(self) -> None:
        # wheel: Windows/macOS use <MouseWheel>, X11 uses Button-4/5
        self.text.bind("<MouseWheel>", self._on_wheel)
        self.text.bind("<Button-4>", lambda e: self._nudge(-1))
        self.text.bind("<Button-5>", lambda e: self._nudge(1))
        self.text.bind("<Control-c>", lambda e: self._copy_selection())
        for seq in ("<Button-3>", "<Button-2>", "<Control-Button-1>"):
            self.text.bind(seq, self._menu)
        self.text.bind("<Enter>", self._on_enter)

    # ------------------------------------------------------------- scrolling
    def _on_enter(self, _e=None) -> None:
        if self.bar._last - self.bar._first < 0.999:
            self.bar._fade_to(1.0, 0.12)

    def _on_wheel(self, e):
        self._nudge(-1 if e.delta > 0 else 1, unit=e.delta / 120.0)
        return "break"

    def _nudge(self, direction: int, unit: float = 1.0):
        self.text.yview_scroll(int(direction * 3 * abs(unit)), "units")
        self.bar.set(*self.text.yview())
        return "break"

    def _on_scroll_request(self, fraction: float):
        self.text.yview_moveto(max(0.0, min(1.0, fraction)))
        self.bar.set(*self.text.yview())

    def scroll_to_bottom(self, animate: bool = True) -> None:
        """Animated 'follow the conversation' (skipped while the user reads up)."""
        if not animate or self.anim is None:
            self.text.see("end")
            self.bar.set(*self.text.yview())
            return

        self.anim.add(logic.Tween(0.24, on_update=lambda v: self._approach_bottom(v)))

    def _approach_bottom(self, v):
        first, last = self.text.yview()
        if last >= 0.999:
            return
        self.text.yview_moveto(min(1.0, first + (1.0 - last) * 0.35 * v + 0.02))
        self.bar.set(*self.text.yview())

    # --------------------------------------------------------------- writing
    def _insert(self, text: str, *tags) -> None:
        self.text.configure(state="normal")
        self.text.insert("end", text, tags)
        self.text.configure(state="disabled")

    def _stamp(self) -> str:
        return _dt.datetime.now().strftime("%H:%M")

    def add_user(self, text: str) -> None:
        self._last_user = text
        self.messages.append({"kind": "you", "text": text, "time": self._stamp()})
        self._insert("\n")
        self._insert("You ▎  ", "hdr_you")
        self._insert(f"{self._stamp()}\n", "hdr_you")
        self._insert(f"{text}\n", "body_you")
        self.scroll_to_bottom()

    def add_system(self, text: str, kind: str = "info", card: bool = False) -> None:
        """Small notice line (voice status, warnings, boot notes)."""
        glyph = {"info": T.SYM["sparkle"], "warn": T.SYM["warn"],
                 "ok": T.SYM["check"], "error": T.SYM["cross"]}.get(kind, "•")
        self.messages.append({"kind": f"sys-{kind}", "text": text, "time": self._stamp()})
        self._insert("\n")
        self._insert(f"{glyph}  {text}\n", "card" if card else "sys")
        self.scroll_to_bottom()

    def add_reply(self, text: str, ok: bool = True, source: str = "",
                  stream: bool = True, card: bool = False) -> None:
        """THANS' answer — typed out progressively when motion is on."""
        self._last_reply = text
        self.messages.append({"kind": "thans", "text": text, "time": self._stamp(),
                              "ok": ok, "source": source})
        self._insert("\n")
        self._insert("THANS ▎  ", "hdr_thans")
        meta = " · ".join(x for x in (source, self._stamp()) if x)
        self._insert(meta + "\n", "meta")
        body = "card" if card else "body"

        if not stream or self.anim is None or len(text) > 4000:
            self._insert(text.rstrip("\n") + "\n\n", body)
            self.scroll_to_bottom()
            return

        streamer = logic.Typewriter(cps=520)
        streamer.start(text)
        state = {"tw": streamer, "body": body, "start": self.text.index("end-1c")}
        self._streams.append(state)
        # the answer types itself in, with a caret at the writing point
        self._insert("▍", "body", "caret")
        self.anim.add(logic.Tween(max(0.26, len(text) / streamer.rate()),
                                  easing=logic.linear,
                                  on_update=lambda v, st=state: self._stream_step(st),
                                  on_done=lambda: self._stream_done(state)))
        self.scroll_to_bottom()

    def _stream_step(self, state: dict) -> None:
        chunk = state["tw"].advance(self.anim.dt if self.anim else 1 / 60)
        self.text.configure(state="normal")
        self.text.delete(state["start"], "end-1c")
        if chunk:
            self.text.insert(state["start"], chunk, state["body"])
        self.text.insert("end-1c", "▍", ("body", "caret"))
        self.text.configure(state="disabled")
        self.bar.set(*self.text.yview())
        self._approach_bottom(1.0)

    def _stream_done(self, state: dict) -> None:
        if state in self._streams:
            self._streams.remove(state)
        if not self.text.winfo_exists():
            return
        self.text.configure(state="normal")
        self.text.delete(state["start"], "end-1c")
        self.text.insert(state["start"], state["tw"].text.rstrip("\n") + "\n\n",
                         state["body"])
        self.text.configure(state="disabled")
        self.scroll_to_bottom()
        if self.on_reply_done:
            self.on_reply_done()

    on_reply_done: Optional[Callable[[], None]] = None

    def finish_streams(self) -> None:
        """Skip any in-flight typing (used before rerunning a command)."""
        for state in list(self._streams):
            state["tw"].elapsed = 1e9
            self._stream_done(state)

    def clear(self) -> None:
        self.finish_streams()
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
        self.messages.clear()
        self.bar.set(0.0, 1.0)

    # ----------------------------------------------------------------- menu
    def _copy_selection(self) -> str:
        try:
            sel = self.text.get("sel.first", "sel.last")
        except tk.TclError:
            return ""
        if sel:
            self.clipboard_clear()
            self.clipboard_append(sel)
        return "break"

    def _menu(self, event):
        m = tk.Menu(self, tearoff=0, bg=T.SURFACE_HI, fg=T.FG,
                    activebackground=T.ACCENT, activeforeground="#ffffff", bd=0)
        try:
            has_sel = bool(self.text.get("sel.first", "sel.last"))
        except tk.TclError:
            has_sel = False
        if has_sel:
            m.add_command(label="Copy selection", command=self._copy_selection)
        if self._last_reply:
            m.add_command(label="Copy last reply",
                          command=lambda: self._to_clip(self._last_reply))
        if self._last_user and self.on_rerun:
            m.add_command(label=f"Run again: {logic.truncate(self._last_user, 30)}",
                          command=lambda: self.on_rerun(self._last_user))
        m.add_separator()
        m.add_command(label="Copy whole chat", command=lambda: self._to_clip(
            self.text.get("1.0", "end-1c")))
        if self.on_clear:
            m.add_command(label="Clear chat", command=self.on_clear)
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()
        return "break"

    def _to_clip(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)


# --------------------------------------------------------------------------
# empty state / hero
# --------------------------------------------------------------------------

class EmptyState(tk.Frame):
    """Centered hero with tap-to-run starters, shown while the chat is empty."""

    def __init__(self, master, animator, fonts, on_starter: Callable[[str], None],
                 bg=T.BG):
        super().__init__(master, bg=bg)
        self.anim = animator
        self.fonts = fonts
        self.on_starter = on_starter
        self._labels: list[tk.Label] = []

        wrap = tk.Frame(self, bg=bg)
        wrap.place(relx=0.5, rely=0.46, anchor="center")
        self._wrap = wrap

        logo = tk.Label(wrap, text=T.SYM["sparkle"], bg=bg, fg=T.ACCENT,
                        font=(fonts.get("ui"), 26))
        logo.pack()
        self._labels.append(logo)

        title = tk.Label(wrap, text="THANS", bg=bg, fg=T.FG,
                         font=(fonts.get("ui"), 30, "bold"))
        title.pack()
        self._labels.append(title)

        sub = tk.Label(wrap, text="Offline voice & text file assistant",
                       bg=bg, fg=T.FG_DIM, font=(fonts.get("ui"), T.SIZE_BODY))
        sub.pack(pady=(2, 0))
        self._labels.append(sub)

        hi = tk.Label(wrap, text=f"{logic.greeting()} — try one of these:",
                      bg=bg, fg=T.FG_FAINT, font=(fonts.get("ui"), T.SIZE_SMALL))
        hi.pack(pady=(14, 8))
        self._labels.append(hi)

        from .widgets import RoundedButton
        chips = tk.Frame(wrap, bg=bg)
        chips.pack()
        for i, (label, command) in enumerate(logic.STARTERS):
            b = RoundedButton(chips, text=label, command=lambda c=command: self.on_starter(c),
                              animator=animator, font=(fonts.get("ui"), T.SIZE_SMALL),
                              subtle=True, bg=bg)
            b.grid(row=i // 3, column=i % 3, padx=4, pady=4)

    def reveal(self, delay: float = 0.15) -> None:
        """Rise + fade in (colour interpolation — tk has no widget alpha)."""
        if self.anim is None:
            return
        self._wrap.place_configure(rely=0.52)
        self.anim.add(logic.Tween(0.5, delay=delay, easing=logic.out_cubic,
                                  on_update=lambda v: self._rise(v)))

    def _rise(self, v: float) -> None:
        if not self.winfo_exists():
            return
        self._wrap.place_configure(rely=logic.lerp(0.52, 0.46, v))
        for i, lbl in enumerate(self._labels):
            final = (T.ACCENT, T.FG, T.FG_DIM, T.FG_FAINT)[min(i, 3)]
            lbl.configure(fg=T.mix(self["bg"], final, max(0.0, min(1.0, v * 1.6 - i * 0.12))))

    def dismiss(self) -> None:
        """Slide up and disappear once the first real command is sent."""
        if self.anim is None:
            self.destroy()
            return
        self.anim.add(logic.Tween(0.22, easing=logic.out_quart,
                                  on_update=lambda v: self._exit(v),
                                  on_done=self.destroy))

    def _exit(self, v: float) -> None:
        if not self.winfo_exists():
            return
        self.place_configure(rely=logic.lerp(0.46, 0.32, v))
        for i, lbl in enumerate(self._labels):
            final = (T.ACCENT, T.FG, T.FG_DIM, T.FG_FAINT)[min(i, 3)]
            lbl.configure(fg=T.mix(self["bg"], final, 1.0 - v))

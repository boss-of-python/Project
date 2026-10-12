"""THANS main window — tkinter, dark theme, thread-safe via a queue.

Layout:
  [title + model-status chips]
  [chat (you / THANS / system lines)]
  [input | send | mic | folder | models | settings]
  [status bar: working dir · busy · version]
"""
from __future__ import annotations

import queue
import shutil
import subprocess
import sys
import threading
import traceback
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import APP_NAME, APP_TAGLINE, __version__, config, model_manager
from .engine import Engine
from .stt import VoiceSTT
from .tts import Speaker

# ---------------------------------------------------------------- palette
BG, PANEL, PANEL2 = "#141519", "#1c1e24", "#23262e"
FG, DIM = "#e8eaf0", "#8b91a0"
ACCENT, OK, WARN, ERR = "#4f8cff", "#3fb950", "#d29922", "#f85149"
USER_C, ASST_C = "#7aa2ff", "#b7c0ff"

MONO = ("Consolas", 10) if sys.platform == "win32" else ("DejaVu Sans Mono", 10)
MONO_S = ("Consolas", 9) if sys.platform == "win32" else ("DejaVu Sans Mono", 9)


class ThansApp:
    def __init__(self, cfg: dict | None = None, text_only: bool = False):
        self.cfg = dict(cfg or config.load_config())
        self.engine = Engine(self.cfg["root"], self.cfg)
        self.stt = VoiceSTT()
        self.speaker = Speaker(self.cfg.get("tts", True), int(self.cfg.get("tts_rate", 185)))
        self.mic_on = False
        self._downloading = False
        self.history: list[str] = []
        self._hist_i: int | None = None
        self._q: "queue.Queue" = queue.Queue()
        self.text_only = text_only

        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} — {APP_TAGLINE}")
        self.root.geometry("900x580")
        self.root.minsize(640, 420)
        self.root.configure(bg=BG)
        self._style()
        self._build()
        self._refresh_chips()
        self._welcome()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll)

    # ------------------------------------------------------------------ ui
    def _style(self) -> None:
        st = ttk.Style(self.root)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure(".", background=PANEL, foreground=FG)
        st.configure("TButton", background=PANEL2, foreground=FG, padding=6,
                     borderwidth=0, focusthickness=0)
        st.map("TButton", background=[("active", "#2c303a")])
        st.configure("Accent.TButton", background=ACCENT, foreground="#ffffff", padding=8)
        st.map("Accent.TButton", background=[("active", "#3d74d9")])
        st.configure("TEntry", fieldbackground=PANEL2, foreground=FG,
                     insertcolor=FG, borderwidth=0, padding=6)

    def _build(self) -> None:
        # header
        head = tk.Frame(self.root, bg=BG)
        head.pack(fill="x", padx=14, pady=(10, 4))
        tk.Label(head, text=f"{APP_NAME}", font=("Segoe UI", 15, "bold"),
                 bg=BG, fg=FG).pack(side="left")
        tk.Label(head, text=f"  offline file assistant  ·  v{__version__}",
                 font=("Segoe UI", 9), bg=BG, fg=DIM).pack(side="left", pady=(6, 0))
        self.chips: dict[str, tk.Label] = {}
        cframe = tk.Frame(head, bg=BG)
        cframe.pack(side="right")
        for key, label in (("root", "📂 …"), ("stt", "STT —"), ("tts", "TTS —"), ("llm", "LLM —")):
            self.chips[key] = tk.Label(cframe, text=label, font=("Segoe UI", 9, "bold"),
                                       bg=PANEL, fg=DIM, padx=8, pady=3)
            self.chips[key].pack(side="left", padx=3)

        # chat
        self.chat = tk.Text(self.root, bg=PANEL, fg=FG, insertbackground=FG,
                            font=MONO, relief="flat", wrap="word", state="disabled",
                            padx=12, pady=10, spacing1=2, spacing3=2,
                            highlightthickness=0)
        self.chat.tag_configure("you", foreground=USER_C, font=MONO_S)
        self.chat.tag_configure("thans", foreground=ASST_C, font=MONO_S)
        self.chat.tag_configure("sys", foreground=DIM, font=MONO_S)
        self.chat.tag_configure("cmd", foreground="#5c6370", font=MONO_S)
        self.chat.pack(fill="both", expand=True, padx=14, pady=4)

        # input row
        row = tk.Frame(self.root, bg=BG)
        row.pack(fill="x", padx=14, pady=(2, 4))
        self.entry = tk.Entry(row, font=MONO, bg=PANEL2, fg=FG,
                              insertbackground=FG, relief="flat")
        self.entry.pack(side="left", fill="x", expand=True, ipady=8, padx=(0, 8))
        self.entry.bind("<Return>", lambda e: self._on_enter())
        self.entry.bind("<Up>", lambda e: self._on_hist(-1))
        self.entry.bind("<Down>", lambda e: self._on_hist(1))
        self.entry.focus_set()

        self.btn_send = ttk.Button(row, text="Send", style="Accent.TButton",
                                   command=self._on_enter)
        self.btn_send.pack(side="left", padx=(0, 6))
        if not self.text_only:
            self.btn_mic = tk.Button(row, text="🎤", font=("Segoe UI", 12), bd=0,
                                     bg=PANEL2, fg=FG, activebackground="#2c303a",
                                     activeforeground=FG, width=4,
                                     command=self._toggle_mic)
            self.btn_mic.pack(side="left", padx=(0, 6))
            self.root.bind("<F2>", lambda e: self._toggle_mic())
        ttk.Button(row, text="📂", command=self._pick_root).pack(side="left", padx=(0, 6))
        self.btn_dl = ttk.Button(row, text="⬇ Models", command=self._download_models)
        self.btn_dl.pack(side="left", padx=(0, 6))
        ttk.Button(row, text="⚙ Settings", command=self._settings).pack(side="left")

        # status bar
        bar = tk.Frame(self.root, bg=PANEL)
        bar.pack(fill="x", side="bottom")
        self.status = tk.Label(bar, text="ready", bg=PANEL, fg=DIM, font=("Segoe UI", 9), anchor="w")
        self.status.pack(side="left", fill="x", expand=True, padx=10, pady=4)
        tk.Label(bar, text=f"{APP_NAME} v{__version__} · offline", bg=PANEL, fg=DIM,
                 font=("Segoe UI", 9)).pack(side="right", padx=10, pady=4)

    def _welcome(self) -> None:
        s = model_manager.status(self.cfg)
        self._post("sys", f"Welcome to {APP_NAME} — type or speak a file command. "
                          f"Say 'help' for the full list.", "★ ")
        if not self.text_only and not (s["stt"] and s["stt_deps"]):
            self._post("sys", "Voice input needs the STT model: click '⬇ Models' once "
                               "(~40 MB download), or just use text commands.", "⚠ ")
        self._set_status(f"working folder: {self.engine.root}")

    # ------------------------------------------------------------ chat api
    def _post(self, kind: str, text: str, prefix: str | None = None) -> None:
        self.chat.config(state="normal")
        if prefix:
            self.chat.insert("end", prefix, kind)
        self.chat.insert("end", text + "\n\n", kind)
        self.chat.config(state="disabled")
        self.chat.see("end")

    def _set_status(self, text: str) -> None:
        self.status.config(text=text)

    def _set_mic(self, on: bool) -> None:
        self.mic_on = on
        if hasattr(self, "btn_mic"):
            self.btn_mic.config(bg=ERR if on else PANEL2)
            self.btn_mic.config(text="⏹" if on else "🎤")
        self._set_status("listening — speak, then stay quiet…" if on
                         else f"working folder: {self.engine.root}")

    def _set_busy(self, busy: bool) -> None:
        if not busy:
            return
        self._set_status("working…")

    # ------------------------------------------------------------- polling
    def _poll(self) -> None:
        try:
            while True:
                item = self._q.get_nowait()
                kind = item[0]
                if kind == "post":
                    self._post(item[1], item[2], item[3])
                elif kind == "busy":
                    self._set_busy(item[1])
                    if not item[1]:
                        self._set_status(f"working folder: {self.engine.root}")
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
        self.root.after(100, self._poll)

    def _refresh_chips(self) -> None:
        s = model_manager.status(self.cfg)
        root_name = Path(self.engine.root).name or str(self.engine.root)
        self.chips["root"].config(text=f"📂 {root_name}", fg=FG if self.engine.root.is_dir() else ERR)
        stt = s["stt"] and s["stt_deps"]
        self.chips["stt"].config(text="STT ✓" if stt else "STT ✗", fg=OK if stt else ERR)
        self.chips["tts"].config(text="TTS ✓" if s["tts"] else "TTS ✗", fg=OK if s["tts"] else ERR)
        if s["llm_enabled"] and s["llm"]:
            self.chips["llm"].config(text="LLM ✓", fg=OK)
        elif s["llm"]:
            self.chips["llm"].config(text="LLM off", fg=WARN)
        else:
            self.chips["llm"].config(text="LLM none", fg=DIM)

    # ------------------------------------------------------------ commands
    def _on_enter(self) -> None:
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self.history.append(text)
        self._hist_i = None
        self._submit(text)

    def _on_hist(self, delta: int) -> None:
        if not self.history:
            return
        self._hist_i = len(self.history) if self._hist_i is None else max(0, min(len(self.history) - 1, self._hist_i + delta))
        self.entry.delete(0, "end")
        self.entry.insert(0, self.history[self._hist_i])

    def _submit(self, text: str) -> None:
        self._post("you", text, "You › ")
        threading.Thread(target=self._worker, args=(text,), daemon=True).start()

    def _worker(self, text: str) -> None:
        self._q.put(("busy", True))
        try:
            res = self.engine.run(text)
            if res.command:
                self._q.put(("post", "cmd", f"→ {res.command}", None))
            tag = "thans" if res.ok else "sys"
            self._q.put(("post", tag, res.message, "THANS › " if res.ok else "· "))
            if self.cfg.get("tts"):
                self.speaker.say(res.message)
        except Exception:  # noqa: BLE001
            self._q.put(("post", "sys", "Internal error:\n" + traceback.format_exc(limit=4), "· "))
        finally:
            self._q.put(("busy", False))

    # ------------------------------------------------------------------ mic
    def _toggle_mic(self) -> None:
        if self.mic_on:
            self.stt.stop()
            self._q.put(("mic", False))
            return
        if not self.stt.available():
            self._post("sys", "Speech model missing — click '⬇ Models' to download it "
                               "once (~40 MB), or use text commands.", "⚠ ")
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
        d = filedialog.askdirectory(initialdir=str(self.engine.root),
                                    title="Choose the working folder THANS may manage")
        if not d:
            return
        self.cfg["root"] = d
        config.save_config(self.cfg)
        self.engine.set_root(d)
        self._refresh_chips()
        self._set_status(f"working folder: {d}")
        self._post("sys", f"All file operations are now confined to: {d}", "📂 ")

    def _download_models(self) -> None:
        if self._downloading:
            return
        if messagebox.askyesno(APP_NAME,
                               "Download offline models?\n\n• STT model (Vosk) ≈ 40 MB\n"
                               "• LLM model (Qwen2.5-0.5B) ≈ 408 MB\n\n"
                               "One-time; THANS then runs with no internet at all."):
            self._start_download()

    def _start_download(self) -> None:
        self._downloading = True
        self.btn_dl.config(state="disabled")
        self._post("sys", "Downloading offline models (one-time; needs internet)…", "⬇ ")

        def job() -> None:
            script = config.app_root() / "scripts" / "download_models.py"
            py = shutil.which("python3") or shutil.which("python") or sys.executable
            try:
                proc = subprocess.Popen(
                    [py, str(script), "--dir", str(config.models_dir())],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, cwd=str(config.app_root()))
                assert proc.stdout is not None
                for line in proc.stdout:
                    line = line.rstrip()
                    if line:
                        self._q.put(("post", "sys", line, None))
                code = proc.wait()
            except Exception as e:  # noqa: BLE001
                code = -1
                self._q.put(("post", "sys", f"Could not start downloader: {e}", None))
            self._q.put(("post", "sys", "Download finished — voice input ready." if code == 0
                                 else f"Download failed (code {code}). Check the network and retry.", None))
            self._q.put(("downloading", False))
            self._q.put(("chips",))

        threading.Thread(target=job, daemon=True).start()

    def _settings(self) -> None:
        dlg = tk.Toplevel(self.root)
        dlg.title("THANS settings")
        dlg.configure(bg=PANEL)
        dlg.resizable(False, False)
        pad = dict(padx=14, pady=6)

        tk.Label(dlg, text="Working folder (THANS can only touch this)", bg=PANEL, fg=DIM,
                 font=("Segoe UI", 9)).pack(anchor="w", **pad)
        f1 = tk.Frame(dlg, bg=PANEL)
        f1.pack(fill="x", **pad)
        var_root = tk.StringVar(value=str(self.engine.root))
        tk.Entry(f1, textvariable=var_root, font=MONO, bg=PANEL2, fg=FG,
                 insertbackground=FG, relief="flat").pack(side="left", fill="x", expand=True)

        def browse() -> None:
            d = filedialog.askdirectory(initialdir=var_root.get())
            if d:
                var_root.set(d)

        ttk.Button(f1, text="Browse", command=browse).pack(side="left", padx=(6, 0))

        var_tts = tk.BooleanVar(value=bool(self.cfg.get("tts")))
        tk.Checkbutton(dlg, text="Speak replies (TTS)", variable=var_tts,
                       bg=PANEL, fg=FG, activebackground=PANEL,
                       activeforeground=FG, selectcolor=PANEL2).pack(anchor="w", **pad)

        f2 = tk.Frame(dlg, bg=PANEL)
        f2.pack(fill="x", **pad)
        tk.Label(f2, text="Speech rate:", bg=PANEL, fg=DIM).pack(side="left")
        var_rate = tk.IntVar(value=int(self.cfg.get("tts_rate", 185)))
        ttk.Scale(f2, from_=110, to=280, variable=var_rate, orient="horizontal",
                  length=220).pack(side="left", padx=(8, 0))

        var_llm = tk.BooleanVar(value=bool(self.cfg.get("use_llm")))
        tk.Checkbutton(dlg, text="Use offline LLM for free-form commands (optional)",
                       variable=var_llm, bg=PANEL, fg=FG, activebackground=PANEL,
                       activeforeground=FG, selectcolor=PANEL2).pack(anchor="w", **pad)

        tk.Label(dlg, text="LLM model (models/*.gguf):", bg=PANEL, fg=DIM,
                 font=("Segoe UI", 9)).pack(anchor="w", **pad)
        ggufs = [p.name for p in model_manager.all_gguf()]
        cur = self.cfg.get("llm_model", "")
        if cur and cur not in ggufs:
            ggufs = [cur] + ggufs
        var_llm_model = tk.StringVar(value=cur)
        ttk.Combobox(dlg, textvariable=var_llm_model, values=ggufs or [cur],
                     state="readonly").pack(fill="x", **pad)

        var_perm = tk.BooleanVar(value=bool(self.cfg.get("permanent_delete")))
        tk.Checkbutton(dlg, text="Danger: deletes bypass the trash (permanent)",
                       variable=var_perm, bg=PANEL, fg=WARN, activebackground=PANEL,
                       activeforeground=WARN, selectcolor=PANEL2).pack(anchor="w", **pad)

        def save() -> None:
            cfg = self.cfg
            cfg["root"] = var_root.get().strip() or cfg["root"]
            cfg["tts"] = bool(var_tts.get())
            cfg["tts_rate"] = int(var_rate.get())
            cfg["use_llm"] = bool(var_llm.get())
            cfg["llm_model"] = var_llm_model.get().strip() or cfg.get("llm_model", "")
            cfg["permanent_delete"] = bool(var_perm.get())
            config.save_config(cfg)
            self.cfg = cfg
            self.engine = Engine(cfg["root"], cfg)
            self.speaker.enabled = cfg["tts"]
            self.speaker.set_rate(int(cfg["tts_rate"]))
            self._refresh_chips()
            self._set_status(f"working folder: {self.engine.root}")
            self._post("sys", "Settings saved.", "⚙ ")
            dlg.destroy()

        ttk.Button(dlg, text="Save", style="Accent.TButton", command=save).pack(pady=(10, 14))
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

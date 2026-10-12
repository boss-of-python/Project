# THANS — Offline Voice & Text File Assistant

A **100 % offline** assistant for **desktop (Python + tkinter)** and **Android
(Kivy)** that lets you **access, alter, create and organize files & folders** by
*speaking* or *typing* natural commands. No cloud, no accounts, no internet
after the one-time model download.

![THANS UI — one design language, two apps](docs/ui-preview.png)

```
You:  "create folder project reports in work"
THANS: Created folder 'work/project reports'.

You:  (voice) "organize downloads by date"
THANS: Moved 23 files into 4 folders in 'downloads'.
```

## How it works

| Layer | Technology | Model size | Internet? |
|-------|-----------|-----------|-----------|
| Speech → text | **Vosk** (small EN-US model) | ≈ 40 MB | only to download once |
| Text → speech | **pyttsx3** (OS voices: SAPI5 / NSSpeech / espeak) | 0 MB | never |
| Command parsing | **Rule parser** (instant, zero deps) — always on | 0 MB | never |
| Free-form parsing | **Optional tiny LLM** via llama.cpp (GGUF in `models/`) | ≈ 408 MB default | only to download once |
| UI | **tkinter** (Python standard library) | 0 MB | never |

The rule parser handles **every command in the reference below** without any
model, so the app is fully functional even before models are downloaded.
The small LLM (default **Qwen2.5-0.5B-Instruct Q4_K_M**) is optional sugar for
loose phrasing — it is switched off by default and can be enabled in Settings.

## The interface

A calm dark surface with one accent ramp, built entirely from canvas-drawn
widgets so it can move: bubbles slide and fade, answers *type themselves* in
behind a caret, the composer breathes while THANS works, toasts stack in the
corner, and a start screen runs the real boot steps instead of a fake
progress bar. Everything animates from a single 60 fps loop, so the app stays
smooth and never blocks on a file operation.

| | Desktop | Android |
|---|---|---|
| Layout | transcript + live dashboard (files · folders · size · free space) | transcript + hero card, thumb-reachable composer |
| Input | typing with as-you-type suggestions, Enter/Tab/↑↓, mic on `F2` | same suggestions, on-screen keyboard, mic button |
| Feedback | streaming replies, thinking dots, toasts, status pills, confetti on a tidy-up | same, tuned for touch (bigger targets, toast stack) |
| Keyboard | `F1` command sheet · `F2` voice · `F5` rescan · `Ctrl+K` clear · `Ctrl+Z` undo · `Ctrl+,` settings · `Ctrl +/-` text size | — |
| Motion | on by default, switchable off in Settings ("Animations") | derived from the same tokens/durations |

Design tokens live in **`thans/ui/theme.py`** (palette, radii, durations, type
scale, glyph sets); the phone theme (`android/thans_android/theme.py`) *derives*
from them, so both apps are always the same product. `python
scripts/render_ui_preview.py` renders the picture above straight from those
tokens — it cannot drift from the app.

## Headless & scriptable

No window, no display, no microphone needed — the same engine is available on
the command line (handy for servers, cron jobs and scripts):

```bash
python -m thans --run "organize downloads by date"        # run one command
python -m thans --run "create folder reports" --run "list" # run several in order
python -m thans --run "find invoice" --json               # one JSON object per command
python -m thans --cli --root ~/work                       # interactive prompt
```

Contract: results go to **stdout**, problems to **stderr** (prefixed `THANS: `),
and the exit code is `0` only if every command succeeded — so `thans --run … &&
next_step` works in a shell script. Headless modes never read or write your
saved config unless you pass `--root`.

## Quick start

```bash
# 1) install dependencies
python -m pip install -r requirements.txt            # core (voice UI)
python -m pip install -r requirements-llm.txt        # optional LLM

# 2) download offline models once (needs internet this one time)
python scripts/download_models.py                    # ~450 MB total

# 3) run
python -m thans
#   --root <folder>   set working root (default: your home)
#   --text-only       start without microphone
#   --no-tts          mute the spoken replies
#   --models          show which models are installed
#   --selftest        run the built-in test suite (headless)
```

Debian/Ubuntu: `sudo apt install python3-tk` first (tkinter).

## Command reference (voice or text)

| Command | Example |
|---------|---------|
| List | `list` · `show files` · `show reports in work` · `what's in downloads` · `how many files in docs` |
| Create folder | `create folder work/reports` · `make a folder called ideas in notes` |
| Create file | `create file todo.txt` · `create file memo.txt with meeting at 3 in notes` |
| Rename | `rename old.txt to new.txt` |
| Move | `move report.pdf to work` · `move a.txt into docs` |
| Copy | `copy report.pdf to backups` |
| Delete | `delete old.txt` (→ trash; say `undo` to restore) · `delete old.txt permanently` |
| Search | `find invoice` · `search for pdf files` · `find *.log` |
| Open | `open notes` (opens in default app / file manager) · `show in folder report.pdf` |
| Organize | `organize downloads` (by extension) · `organize downloads by date` |
| Navigate | `go to work` · `cd work/reports` · `cd` (back to root) |
| Safety net | `undo` (last action) · `help` |

Deletes go to `.thans_trash` inside your working root by default — nothing is
destroyed unless you explicitly say *permanently* (or enable it in Settings).
All operations are confined to the working root; THANS refuses to touch paths
outside it.

## Models folder

All models live in the dedicated **`models/`** folder (see `models/README.md`):

```
models/
├── vosk-model-small-en-us-0.15/            ← speech recognition (~40 MB)
└── Qwen2.5-0.5B-Instruct-Q4_K_M.gguf       ← optional LLM (~408 MB)
```

`python scripts/download_models.py` fetches both (progress bars, skips existing
files). Smaller or larger LLMs are selectable with `--model` — see the script's
`--list`. After the download THANS needs **no internet at all**.

## Installer

### Windows
1. `installer\windows\build_exe.bat` — builds `dist\THANS.exe` (PyInstaller)
   and, if [Inno Setup](https://jrsoftware.org/isdl.php) is installed, compiles
   `installer/windows/setup.iss` into **`installer/windows/Output/THANS-Setup-0.2.0.exe`**
   (classic wizard: pick folder, desktop shortcut, uninstaller).
   Download models first (`python scripts/download_models.py`) and they are
   bundled into the installer; otherwise the installed app offers one-click download.
2. No Inno Setup? `dist\THANS.exe` + the `models/` folder next to it is a
   working portable app — copy anywhere, double-click, done.

### Linux
```bash
installer/linux/build_exe.sh     # builds dist/THANS
installer/linux/install.sh       # installs to /opt/thans + launcher (thans.desktop)
```

### macOS
`python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt`
then `python -m thans`. (A DMG can be produced the same way with PyInstaller.)

### Android (APK)
A Kivy port of the **same app** lives in [`android/`](android/README.md).
Fastest path to the APK:

1. GitHub repo → **Actions** tab → **Build Android APK** → **Run workflow**.
2. Download the **`thans-android`** artifact when the job finishes → install the `.apk`.

Text commands work fully offline on the phone; voice input/replies use the
device's own speech service (best-effort — see `android/README.md` for the
capability matrix and local buildozer instructions).

## Project layout

```
thans/            the app (GUI, engine, parsers, actions, audio)
thans/ui/         design system: theme tokens, widget kit, transcript, panels
thans/actions/    file & folder operations (safety-checked)
models/           dedicated folder for all offline models
scripts/          download_models.py, build_installer.py
installer/        Windows (Inno Setup) and Linux installer sources
tests/            unittest suite (run: python -m thans --selftest)
PROGRESS.md       50-step build plan + live status (resumable build log)
```

## Safety model

- **Working root confinement:** every resolved path must stay inside the chosen
  root (relative, `~`, or absolute). Escapes (`../`, other drives, symlinks
  out of root) are rejected.
- **Trash first:** deletes move to `<root>/.thans_trash` and are restorable with
  `undo` (or by hand, the folder is plain).
- **Audit:** the last action is recorded so `undo` can reverse rename / move /
  copy / create / delete.
- **Config** lives in `~/.thans/config.json` — inspect it any time.

## Development

```bash
python -m thans --selftest          # full suite: parser, actions, engine, CLI, UI
python scripts/render_ui_preview.py # regenerate docs/ui-preview.png
```

The suite (190+ tests) runs **without a display**: the UI layers are exercised
through faithful test doubles of tkinter (`tests/faketk.py`) and Kivy
(`tests/fakekivy.py`) that validate option names, run the real animation loop
on a virtual clock and drive real worker threads. Android-specific checks parse
`android/thans.kv` and prove every `app.*` handler and every widget id that the
Python code touches actually exists.

## Works with

* **Windows 10/11** — portable `THANS.exe` or the Inno Setup wizard (desktop +
  Start-menu shortcuts, icon, uninstaller)
* **Linux** — PyInstaller build + `install.sh` (launcher, `.desktop` entry, icon)
* **macOS** — `pip install -r requirements.txt && python -m thans`
* **Android 5.0+** — `android/` Kivy port; APK from GitHub Actions or buildozer
* **Anything headless** — `thans --run "…"` / `thans --cli`

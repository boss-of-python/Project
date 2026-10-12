# THANS — Offline Voice & Text File Assistant

A **100 % offline** desktop assistant (Python + tkinter) that lets you **access,
alter, create and organize files & folders** by *speaking* or *typing* natural
commands. No cloud, no accounts, no internet after the one-time model download.

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
python -m thans --selftest   # headless test suite (parser, actions, engine)
```

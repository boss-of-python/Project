# THANS — Build Progress File

> **Purpose of this file:** resumable build state. If a session/agent dies mid-build,
> a new one should: (1) read this file, (2) find the first `⬜` step, (3) continue
> from there, (4) tick steps off as they complete, (5) `git commit` after every phase.

**Project:** THANS — a fully offline Python assistant that accesses, alters,
creates and organizes files & folders via **voice commands** and **text commands**,
with an optional small offline LLM for free-form phrasing.
Desktop build = tkinter UI (steps 1–50). Android build = Kivy UI reusing the same
pure-Python core (steps 51–60).

**Last update:** 2026-10-12 — Phase 9 (headless CLI + CI) and Phase 10 (UI/UX
overhaul on desktop **and** Android) complete; Android port merged to main via PR #2
**Current position:** STEP 76 / 100 — v0.2.0: scriptable CLI, animated UI, shared design tokens
**Resume rule:** do the first unchecked step (there is one: Phase 11 below); do not skip ahead; commit + push after each phase.

Legend: ⬜ not started · 🚧 in progress · ✅ done

---

## Phase 0 — Project foundation (steps 1–6)

- [x] 1.  Create repository skeleton (`thans/`, `models/`, `scripts/`, `installer/`, `tests/`)
- [x] 2.  Create `PROGRESS.md` with the 50-step plan and status tracking
- [x] 3.  Create `requirements.txt` (runtime deps) + `requirements-llm.txt` (optional LLM) + `requirements-build.txt`
- [x] 4.  Create `pyproject.toml` (packaging metadata + `thans` entry point)
- [x] 5.  Create `.gitignore` (models, venv, build artifacts, pycache)
- [x] 6.  Write `README.md` (overview, quick start, command reference, model sizes, safety notes)

## Phase 1 — Config & model management (steps 7–11)

- [x] 7.  `thans/config.py` — app paths, models dir, working root, config load/save, safety defaults
- [x] 8.  `models/README.md` — document the dedicated models folder layout
- [x] 9.  `thans/model_manager.py` — detect installed models (Vosk STT, GGUF LLM, TTS) and report status
- [x] 10. `scripts/download_models.py` — one-time offline-model downloader (Vosk small STT + GGUF LLM, stdlib only, progress bars, skip-if-present)
- [x] 11. Model status surfaced in UI chips + `--models` CLI flag

## Phase 2 — Rule-based command parser (steps 12–25)

- [x] 12. Define command schema (action + params dicts; allowed-actions whitelist)
- [x] 13. `thans/parser_rules.py` — intent registry, text normalization (fillers, punctuation, casing)
- [x] 14. `list` / `show` / "what's in X" / "how many files in X" commands
- [x] 15. `create folder X [in Y]` command
- [x] 16. `create file X [with content ...] [in Y]` command
- [x] 17. `rename A to B` command
- [x] 18. `move A to B` command (incl. "into", dest-as-folder semantics)
- [x] 19. `copy A to B` command
- [x] 20. `delete X` command (safe trash-by-default + `permanently` flag)
- [x] 21. `find` / `search for` commands (name substring + extension forms like "pdf files")
- [x] 22. `open X` / `show in folder X` commands (file-manager reveal)
- [x] 23. `organize [dir] by extension|date` command
- [x] 24. `help`, `cd`/`go to`, `undo` commands
- [x] 25. Fuzzy name resolution (case-insensitive unique match, ambiguity listing) + "in <dir>" qualifier fallback

## Phase 3 — Action engine & safety (steps 26–32)

- [x] 26. Path safety: all operations confined to allowed working root (reject escapes, `..`, absolute paths outside root)
- [x] 27. File actions: create (with content), rename, move, copy, delete
- [x] 28. Folder actions: create (nested), rename, move, copy, delete
- [x] 29. Trash + restore mechanism (`.thans_trash` inside working root, timestamped entries)
- [x] 30. Search implementation (walk, case-insensitive, ext filter, skip trash/hidden, result cap)
- [x] 31. Organize implementation (group files into subfolders by extension or by date, de-dupe names)
- [x] 32. `thans/engine.py` — parse → resolve → execute → human-readable report + undo record (single-level undo)

## Phase 4 — Tkinter GUI (steps 33–40)

- [x] 33. `thans/app.py` — main window layout, dark theme, graceful import guard
- [x] 34. Chat view (user / THANS / system message styles, auto-scroll)
- [x] 35. Text input bar — Enter handling, command history (Up/Down)
- [x] 36. Model status panel (STT/TTS/LLM chips) + one-click "download models" button
- [x] 37. Working-root picker + safety indicator in status bar
- [x] 38. Settings dialog (TTS on/off + rate, LLM on/off + model picker, permanent-delete toggle, root)
- [x] 39. Threaded command execution (worker thread + queue so UI never blocks)
- [x] 40. Status bar (current dir, busy state, version)

## Phase 5 — Offline audio (steps 41–44)

- [x] 41. `thans/stt.py` — Vosk offline speech-to-text (mic 16 kHz, int16 streaming)
- [x] 42. Mic thread with endpointing (final transcript → command pipeline), clean stop
- [x] 43. `thans/tts.py` — pyttsx3 offline text-to-speech on dedicated worker thread (queue-based, silent-fail)
- [x] 44. Voice loop wiring: listen → parse → act → speak result

## Phase 6 — Optional offline LLM (steps 45–47)

- [x] 45. `thans/parser_llm.py` — llama.cpp wrapper, strict JSON-only system prompt, action whitelist validation, JSON extraction from LLM output
- [x] 46. LLM model catalog + placement in `models/` (default Qwen2.5-0.5B-Instruct Q4_K_M ≈ 408 MB; smaller/larger alternatives documented)
- [x] 47. Fallback chain: rule parser → LLM parser (if enabled) → polite "I didn't catch that — say 'help'"

## Phase 7 — Packaging, installer & QA (steps 48–50)

- [x] 48. `scripts/build_installer.py` — PyInstaller one-file build (windowed, `--name THANS`)
- [x] 49. `installer/windows/` — `build_exe.bat` + Inno Setup `setup.iss` (desktop shortcut, optional models bundle, uninstaller)
- [x] 50. `installer/linux/` — `build_exe.sh` + `install.sh` + `thans.desktop`; full test-suite run (`--selftest`) green; final README polish

## Phase 8 — Android (Kivy) port (steps 51–60)

- [x] 51. Merge desktop build to `main` (PR #1) — repo now shows the full app
- [x] 52. `android/` buildozer project: `main.py`, `buildozer.spec` (python3.11 + kivy + pyjnius, RECORD_AUDIO), `stage_thans.sh` (single source of truth: copies `../thans` in)
- [x] 53. `android/thans.kv` — dark UI: status bar, scrolling chat (newest on top), input+SEND, MIC/HELP/CLEAR, SPEAK toggle
- [x] 54. `thans_android/app.py` — Kivy front-end reusing the SAME `thans` engine (Kivy-thread-safe via Clock, working root = P4A cwd)
- [x] 55. Headless UI validation: KV parsed by real Kivy parser, all ids + handlers verified, full simulated session through real code paths (caught & fixed missing `chat_scroll` id)
- [x] 56. `thans_android/audio.py` — TTS via `android.speech.tts.TextToSpeech` (pyjnius, fully guarded)
- [x] 57. STT via `android.speech.SpeechRecognizer` + RecognitionListener (pyjnius, guarded; offline only if device has an offline voice pack)
- [x] 58. `.github/workflows/build-apk.yml` — CI: core tests → buildozer `android debug` → **APK artifact** (`thans-android`)
- [x] 59. `android/README.md` — how to get the APK (Actions or local buildozer), capability matrix, limits
- [x] 60. Core suite still green (45/45), committed + pushed, PR #2 opened for `main`

## Phase 9 — Headless CLI, tooling & CI (steps 61–66)

- [x] 61. `thans/cli.py` — engine-driven headless runner (imports no tkinter): run one/many commands, JSON output, quiet mode, interactive `--cli` prompt
- [x] 62. Output contract: results → stdout, problems → stderr (`THANS: …`), exit code 0/1, "keep going after a failure" semantics
- [x] 63. `__main__` flags: `--run/-c` (repeatable), `--cli`, `--json`, `--quiet`, `--llm/--no-llm`, `--version`; headless modes never write the saved config
- [x] 64. `tests/test_cli.py` — in-process + real-subprocess coverage of argv, streams, exit codes, safety, recursion guard for `--selftest`
- [x] 65. `.github/workflows/tests.yml` — suite on Linux/Windows/macOS × py3.11/3.12 + CLI smoke tests + exit-code contract + UI-preview render job
- [x] 66. APK workflow hardened: pinned `cython<3` (p4a requirement), cached Android SDK/NDK, layout validation runs before the build

## Phase 10 — UI/UX overhaul (steps 67–76)

- [x] 67. `thans/ui/theme.py` — one palette + radii + durations + type scale + glyph sets; colour maths (`mix`, `ramp`, `plain`) unit-tested
- [x] 68. `thans/ui/logic.py` — pure animation engine (Tween/Animator/LoopTween, easings, typewriter, suggestions, health, greetings) — no tkinter, fully tested
- [x] 69. `thans/ui/widgets.py` — canvas-drawn kit: rounded `Card`, `RoundedButton`/`IconButton`, `Chip`, `Switch`, gradient `ProgressBar`, `Dots`, `Waveform`, `Toaster`, `SlidePanel`, `Tooltip`, `Burst`
- [x] 70. `thans/ui/chat.py` — transcript with streaming (typed-out) replies, message bubbles, slim fading scrollbar, right-click actions, animated `EmptyState` hero
- [x] 71. `thans/ui/panels.py` — boot overlay (real init steps), dashboard cards (files/folders/size/free space with count-up), quick actions, voice card, tappable `HelpPanel`, live-progress `SettingsPanel`
- [x] 72. `thans/app.py` rewritten: single 60 fps loop, responsive dashboard column, keyboard shortcuts, suggestions, toasts, confetti, geometry + settings persistence, first-run tour
- [x] 73. `tests/faketk.py` + `tests/test_ui_app.py` — 59 headless UI tests that drive the real window (boot, commands, streaming, settings, voice wiring, widgets)
- [x] 74. Android UI rebuilt on the same tokens: `android/thans.kv` (boot splash, chips, bubbles, pills, composer, hero), `widgets.py`, `theme.py` derived from the desktop palette, icon + presplash
- [x] 75. `tests/fakekivy.py` + `tests/test_android_app.py` — static KV↔code validation + 36 behavioural tests (boot, bubbles, toasts, mic, speech, prefs) with no GL/display
- [x] 76. `scripts/render_ui_preview.py` → `docs/ui-preview.png` (rendered from the real tokens); README/PROGRESS/android docs updated; installer branding (`.ico`, `.desktop` icon, wizard icon)

---

## Changelog

| Date | Step(s) | Note |
|------|---------|------|
| 2026-10-12 | — | Plan created (50 steps). Build starting. |
| 2026-10-12 | 1–6 | Phase 0 committed: skeleton, requirements, pyproject, .gitignore, README. |
| 2026-10-12 | 7–10 | Phase 1: config, model_manager, models/README, download_models.py. |
| 2026-10-12 | 12–25 | Phase 2: rule parser — all 13 intent families, fuzzy names, fillers. |
| 2026-10-12 | 26–32 | Phase 3: actions + engine (root confinement, trash, undo). 45/45 tests pass. |
| 2026-10-12 | 33–40 | Phase 4: tkinter GUI (chat, chips, mic, settings, threaded worker). |
| 2026-10-12 | 41–44 | Phase 5: Vosk STT + pyttsx3 TTS + voice loop wiring. |
| 2026-10-12 | 45–47 | Phase 6: optional llama.cpp LLM parser + whitelist validation + fallback chain. |
| 2026-10-12 | 48–50 | Phase 7: PyInstaller build script, Windows (Inno Setup) + Linux installers. Full suite green. |
| 2026-10-12 | 51 | Desktop build merged to `main` (PR #1) — now visible in the repo. |
| 2026-10-12 | 52–60 | Phase 8: Android (Kivy) port reusing the core; headless-validated; CI builds the APK artifact. PR #2 opened. |
| 2026-10-12 | 61–66 | Phase 9 (v0.2.0): headless CLI (`--run`/`--cli`/`--json`), stdout/stderr + exit-code contract, cross-OS CI, APK workflow hardened. |
| 2026-10-12 | 67–76 | Phase 10: UI/UX overhaul — shared design tokens, animated desktop window, Kivy UI rebuilt to match, 95 new headless UI tests, preview renderer, installer branding. |

## Phase 11 — Next (steps 77–100, not started)

- [ ] 77. Undo **history**: keep an undo stack (not just the last action) and show it in the dashboard
- [ ] 78. Folder **watch** (inotify/FSEvents polling) with a live "what changed" digest in the transcript
- [ ] 79. Batch **rename** (pattern → `photo_001.jpg`) exposed as `rename all .jpg in pics to …`
- [ ] 80. Zip / unzip commands (`zip reports`, `unzip archive.zip`) with progress
- [ ] 81. Desktop **tray icon** + global hotkey to summon the window and start listening
- [ ] 82. Duplicate-file finder (`find duplicates in downloads`) with a safe, trashed cleanup
- [ ] 83. Storage report card (largest folders, oldest files) under the dashboard
- [ ] 84. Android: SAF/`MANAGE_EXTERNAL_STORAGE` opt-in so the phone can manage real shared folders
- [ ] 85. Android: floating bubble (overlay) shortcut for voice commands from any app
- [ ] 86. i18n of the parser + UI strings (start with Spanish, Hindi, Tamil)
- [ ] 87. Voice wake word ("hey thans") via a tiny offline keyword spotter
- [ ] 88. Undo of `organize` (record every move so a whole tidy-up can be reversed)
- [ ] 89. Command palettes/presets: user-defined shortcuts ("tidy my desktop")
- [ ] 90. Plugin API: drop a Python file in `~/.thans/plugins/` to add an action
- [ ] 91. Optional encrypted trash + "shred" (secure overwrite) command
- [ ] 92. Export the transcript (txt/md) and copy a command as a shell one-liner
- [ ] 93. Accessibility pass: screen-reader labels, high-contrast theme, 200% scaling
- [ ] 94. Light theme alongside the dark one (tokens already centralised)
- [ ] 95. Telemetry-free crash report file (`~/.thans/last_error.log`) with one-click copy
- [ ] 96. Benchmarks: parser throughput + action latency in CI (fail on regression)
- [ ] 97. Packaged `.dmg` / Flatpak / MSIX builds
- [ ] 98. Model manager UI: switch STT/LLM models, verify checksums, delete models
- [ ] 99. Watch-folder automations ("when a PDF lands in scans, move it to docs")
- [ ] 100. 1.0 polish: onboarding tour, release page, signed installers

## Known decisions (so future sessions don't re-litigate)

- **Name:** THANS. **UI:** tkinter (stdlib) with a small dark theme.
- **STT:** Vosk `vosk-model-small-en-us-0.15` (≈ 40 MB) — fully offline.
- **TTS:** `pyttsx3` (system voices: SAPI5 on Windows, espeak/NSSpeech elsewhere) — zero download.
- **LLM (optional):** `llama-cpp-python` + GGUF in `models/`. Default **Qwen2.5-0.5B-Instruct Q4_K_M (≈ 408 MB)** — best tiny model for strict-JSON command extraction. App works 100 % without it (rule parser covers all documented commands).
- **Safety:** all ops confined to one working root; deletes go to trash by default; single-level undo; config in `~/.thans/config.json`.
- **Python ≥ 3.10.** Tests run via `python -m unittest` (no pytest dependency).
- **Design system:** one palette/type/motion source in `thans/ui/theme.py`; Android derives from it. Animations are switchable (`motion` setting) and every widget is canvas-drawn (no image assets, works on any tkinter).
- **Two test doubles, no display needed:** `tests/faketk.py` (tkinter) and `tests/fakekivy.py` (Kivy) let the UI suites run in CI/containers; they validate option names, ids and the real animation loop rather than mocking behaviour away.
- **Headless-first engine:** `thans/cli.py` never imports tkinter, so servers and cron jobs can drive the same safe engine; `--json` + exit codes are the stable scripting interface.
- **Glyph policy:** emoji on Windows/macOS, DejaVu-safe geometric symbols elsewhere; `theme.plain()` downgrades pictographs before they hit a monospace surface (no tofu boxes on Linux).
- **Android:** Kivy UI reuses the same pure-Python `thans` core (staged in at build time). Vosk/sounddevice/pyttsx3/llama are desktop-only (no Android builds); the phone uses Android's own `SpeechRecognizer`/`TextToSpeech` via pyjnius, so voice is best-effort (offline only with an on-device offline voice pack) and the LLM is off. Text commands are the guaranteed-fully-offline path on Android. Working root = the app's private storage dir (P4A cwd) — the only storage Android allows without broad permissions. APK is produced by the GitHub Actions workflow (`thans-android` artifact) or a local `buildozer android debug`.

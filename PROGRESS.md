# THANS — Build Progress File

> **Purpose of this file:** resumable build state. If a session/agent dies mid-build,
> a new one should: (1) read this file, (2) find the first `⬜` step, (3) continue
> from there, (4) tick steps off as they complete, (5) `git commit` after every phase.

**Project:** THANS — a fully offline Python assistant that accesses, alters,
creates and organizes files & folders via **voice commands** and **text commands**,
with an optional small offline LLM for free-form phrasing.
Desktop build = tkinter UI (steps 1–50). Android build = Kivy UI reusing the same
pure-Python core (steps 51–60).

**Last update:** 2026-10-12 — Phase 9 complete (fixed runtime UI/Android/CI issues); starting Phase 10–12 (impressive animations & minimalistic UX for Desktop + Android)
**Current position:** STEP 65 / 85 — PR #1 & #2 merged to main; Phase 9 complete; Phase 10 in progress
**Resume rule:** do the first unchecked step; do not skip ahead; commit + push after each phase.

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

## Phase 9 — Finish & Fix Previous Work (steps 61–65)

- [x] 61. Fix Desktop `ThansApp` window-close protocol (`self.root.protocol`) & `cd ..` / `go back` / `undo` for `organize`
- [x] 62. Fix Android Kivy runtime API calls (`Builder.load_file`, `BoxLayout.add_widget`, `ScrollView.scroll_y`, wrapped label sizing, `canvas.before` backgrounds)
- [x] 63. Add Android 6+ runtime `RECORD_AUDIO` permission request, friendly error mapping, and live partial/RMS speech callbacks in `thans_android/audio.py` & `thans/stt.py`
- [x] 64. Fix `.github/workflows/build-apk.yml` and `android/buildozer.spec` (`virtualenv`, `cython<3`, C/JNI system headers, buildozer cache) so APK CI builds cleanly
- [x] 65. Update `PROGRESS.md` for merged PR #2 and Phase 9 completion

## Phase 10 — Shared UX Intelligence & Animation Engine (steps 66–70)

- [ ] 66. `thans/ui_helpers.py` — real-time intent preview (`preview_intent`), smart command & filename autocomplete (`autocomplete`), quick-action chip catalog
- [ ] 67. `thans/ui_helpers.py` — live directory snapshot (`dir_snapshot`), diff tracking for visual highlight animations, smart file-type icons, human-readable sizes, breadcrumb path segments, and `.thans_trash` counter
- [ ] 68. `thans/animations.py` — color interpolation (`lerp_hex`, `lerp_rgba`), cubic/sine easing curves, 60fps multi-wave sonic orb/waveform geometry generator (`compute_wave_points`), streaming text chunker, and pulse decay math
- [ ] 69. Extend `thans/config.py` with UI/UX preferences (`theme`: dark/light, `animations`: on/off, `sidebar`: open/closed)
- [ ] 70. Unit tests (`tests/test_ui_helpers.py`) covering intent preview, autocomplete, snapshots/diffs, breadcrumbs, and animation math

## Phase 11 — Impressive Minimalistic Desktop UI/UX (Windows & Linux) (steps 71–78)

- [ ] 71. Minimalistic design system (`thans/app.py`) with Dark & Light themes, smooth theme cross-fade transition, and refined typography
- [ ] 72. Animated **Sonic Visualizer Canvas** in header (60fps multi-ribbon sine waves + glowing orb reacting to Idle, Listening, Thinking, Speaking, and Success/Error states)
- [ ] 73. Interactive **Breadcrumb Bar** (`🏠 root › folder › subfolder`) + **Trash Badge (`♻️ N`)** + one-click **Undo (`↩`)** & **Theme Toggle (`🌙/☀️`)**
- [ ] 74. Collapsible **Live File Workspace Sidebar** with instant filter box, smart file icons, file sizes, double-click to navigate/open, single-click context action bar (`Open`, `Rename`, `Move`, `Trash`), and **animated emerald highlight pulses** on newly created/modified items
- [ ] 75. **Live Intent Preview Bar** & clickable **Quick-Action Chips** above the input bar (real-time parsed action badge as you type + `Tab` autocomplete for commands & filenames)
- [ ] 76. **Animated Chat Stream** with role badges, command pills, smooth streaming text reveal, and slide-in toast notifications
- [ ] 77. Keyboard shortcuts (`Ctrl+K` / `/` focus command bar, `Tab` autocomplete, `Ctrl+Z` undo, `Ctrl+L` clear chat, `Ctrl+B` toggle sidebar, `F2` mic toggle) & modernized Settings modal
- [ ] 78. Headless Desktop UI test suite (`tests/test_desktop_ui.py`) validating widget creation, animations, sidebar interactions, theme transitions, and command flow

## Phase 12 — Impressive Minimalistic Android APK UI/UX (steps 79–85)

- [ ] 79. Modern minimalistic Kivy layout (`android/thans.kv`) with rounded card surfaces (`RoundedRectangle`), elevation, dark/light theme support, and responsive `dp`/`sp` scaling
- [ ] 80. Animated **Sonic Wave & Status Header** with interactive **Breadcrumb Path Bar** (`⬆ Up` + current folder pill) and **Trash/Undo** quick action
- [ ] 81. Touch-intuitive **Segmented View (`💬 Assistant` | `📁 Files`)** so mobile users can both chat and visually browse/tap folders & files offline
- [ ] 82. **Live Intent Preview Pill** + horizontal scrollable **Quick-Action Chips** (`📁 List`, `➕ Folder`, `📝 File`, `✨ Organize`, `🔍 Find`, `↩ Undo`, `❓ Help`) for effortless thumb-driven UX
- [ ] 83. Smooth Kivy widget animations (`kivy.animation.Animation` for card fade/slide-in, button press feedback, sonic wave bars, and file change highlights)
- [ ] 84. Headless Android Kivy test suite (`tests/test_android_ui.py`) validating real KV parsing, widget tree build, view switching, animations, live preview, and end-to-end command sessions
- [ ] 85. Final documentation polish (`README.md`, `android/README.md`, `PROGRESS.md`), full test run, commit & push

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
| 2026-10-12 | 52–60 | Phase 8: Android (Kivy) port reusing the core; headless-validated; CI builds the APK artifact. PR #2 opened & merged. |
| 2026-10-12 | 61–65 | Phase 9: Fixed Android/Desktop runtime calls, runtime mic permissions, `undo` for `organize`, `cd ..`, and APK CI dependencies/caching. |

## Known decisions (so future sessions don't re-litigate)

- **Name:** THANS. **UI:** tkinter (stdlib) with a small dark theme.
- **STT:** Vosk `vosk-model-small-en-us-0.15` (≈ 40 MB) — fully offline.
- **TTS:** `pyttsx3` (system voices: SAPI5 on Windows, espeak/NSSpeech elsewhere) — zero download.
- **LLM (optional):** `llama-cpp-python` + GGUF in `models/`. Default **Qwen2.5-0.5B-Instruct Q4_K_M (≈ 408 MB)** — best tiny model for strict-JSON command extraction. App works 100 % without it (rule parser covers all documented commands).
- **Safety:** all ops confined to one working root; deletes go to trash by default; single-level undo; config in `~/.thans/config.json`.
- **Python ≥ 3.10.** Tests run via `python -m unittest` (no pytest dependency).
- **Android:** Kivy UI reuses the same pure-Python `thans` core (staged in at build time). Vosk/sounddevice/pyttsx3/llama are desktop-only (no Android builds); the phone uses Android's own `SpeechRecognizer`/`TextToSpeech` via pyjnius, so voice is best-effort (offline only with an on-device offline voice pack) and the LLM is off. Text commands are the guaranteed-fully-offline path on Android. Working root = the app's private storage dir (P4A cwd) — the only storage Android allows without broad permissions. APK is produced by the GitHub Actions workflow (`thans-android` artifact) or a local `buildozer android debug`.

# THANS — Build Progress File

> **Purpose of this file:** resumable build state. If a session/agent dies mid-build,
> a new one should: (1) read this file, (2) find the first `⬜` step, (3) continue
> from there, (4) tick steps off as they complete, (5) `git commit` after every phase.

**Project:** THANS — a fully offline Python/tkinter assistant that accesses, alters,
creates and organizes files & folders via **voice commands** and **text commands**,
with an optional small offline LLM for free-form phrasing.

**Last update:** 2026-10-12 — ALL 50 STEPS COMPLETE ✅  (45/45 tests green, end-to-end demo verified)
**Current position:** STEP 50 / 50 — build complete
**Resume rule:** do the first unchecked step; do not skip ahead; commit after each phase.

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

## Known decisions (so future sessions don't re-litigate)

- **Name:** THANS. **UI:** tkinter (stdlib) with a small dark theme.
- **STT:** Vosk `vosk-model-small-en-us-0.15` (≈ 40 MB) — fully offline.
- **TTS:** `pyttsx3` (system voices: SAPI5 on Windows, espeak/NSSpeech elsewhere) — zero download.
- **LLM (optional):** `llama-cpp-python` + GGUF in `models/`. Default **Qwen2.5-0.5B-Instruct Q4_K_M (≈ 408 MB)** — best tiny model for strict-JSON command extraction. App works 100 % without it (rule parser covers all documented commands).
- **Safety:** all ops confined to one working root; deletes go to trash by default; single-level undo; config in `~/.thans/config.json`.
- **Python ≥ 3.10.** Tests run via `python -m unittest` (no pytest dependency).

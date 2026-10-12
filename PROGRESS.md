# THANS — Build Progress File

> **Purpose of this file:** resumable build state. If a session/agent dies mid-build,
> a new one should: (1) read this file, (2) find the first `⬜` step, (3) continue
> from there, (4) tick steps off as they complete, (5) `git commit` after every phase.

**Project:** THANS — a fully offline Python/tkinter assistant that accesses, alters,
creates and organizes files & folders via **voice commands** and **text commands**,
with an optional small offline LLM for free-form phrasing.

**Last update:** 2026-10-12 — plan created, build starting (step 1)
**Current position:** STEP 1 / 50
**Resume rule:** do the first unchecked step; do not skip ahead; commit after each phase.

Legend: ⬜ not started · 🚧 in progress · ✅ done

---

## Phase 0 — Project foundation (steps 1–6)

- [ ] 1.  Create repository skeleton (`thans/`, `models/`, `scripts/`, `installer/`, `tests/`)
- [ ] 2.  Create `PROGRESS.md` with the 50-step plan and status tracking
- [ ] 3.  Create `requirements.txt` (runtime deps) + `requirements-llm.txt` (optional LLM) + `requirements-build.txt`
- [ ] 4.  Create `pyproject.toml` (packaging metadata + `thans` entry point)
- [ ] 5.  Create `.gitignore` (models, venv, build artifacts, pycache)
- [ ] 6.  Write `README.md` (overview, quick start, command reference, model sizes, safety notes)

## Phase 1 — Config & model management (steps 7–11)

- [ ] 7.  `thans/config.py` — app paths, models dir, working root, config load/save, safety defaults
- [ ] 8.  `models/README.md` — document the dedicated models folder layout
- [ ] 9.  `thans/model_manager.py` — detect installed models (Vosk STT, GGUF LLM, TTS) and report status
- [ ] 10. `scripts/download_models.py` — one-time offline-model downloader (Vosk small STT + GGUF LLM, stdlib only, progress bars, skip-if-present)
- [ ] 11. Model status surfaced in UI chips + `--models` CLI flag

## Phase 2 — Rule-based command parser (steps 12–25)

- [ ] 12. Define command schema (action + params dicts; allowed-actions whitelist)
- [ ] 13. `thans/parser_rules.py` — intent registry, text normalization (fillers, punctuation, casing)
- [ ] 14. `list` / `show` / "what's in X" / "how many files in X" commands
- [ ] 15. `create folder X [in Y]` command
- [ ] 16. `create file X [with content ...] [in Y]` command
- [ ] 17. `rename A to B` command
- [ ] 18. `move A to B` command (incl. "into", dest-as-folder semantics)
- [ ] 19. `copy A to B` command
- [ ] 20. `delete X` command (safe trash-by-default + `permanently` flag)
- [ ] 21. `find` / `search for` commands (name substring + extension forms like "pdf files")
- [ ] 22. `open X` / `show in folder X` commands (file-manager reveal)
- [ ] 23. `organize [dir] by extension|date` command
- [ ] 24. `help`, `cd`/`go to`, `undo` commands
- [ ] 25. Fuzzy name resolution (case-insensitive unique match, ambiguity listing) + "in <dir>" qualifier fallback

## Phase 3 — Action engine & safety (steps 26–32)

- [ ] 26. Path safety: all operations confined to allowed working root (reject escapes, `..`, absolute paths outside root)
- [ ] 27. File actions: create (with content), rename, move, copy, delete
- [ ] 28. Folder actions: create (nested), rename, move, copy, delete
- [ ] 29. Trash + restore mechanism (`.thans_trash` inside working root, timestamped entries)
- [ ] 30. Search implementation (walk, case-insensitive, ext filter, skip trash/hidden, result cap)
- [ ] 31. Organize implementation (group files into subfolders by extension or by date, de-dupe names)
- [ ] 32. `thans/engine.py` — parse → resolve → execute → human-readable report + undo record (single-level undo)

## Phase 4 — Tkinter GUI (steps 33–40)

- [ ] 33. `thans/app.py` — main window layout, dark theme, graceful import guard
- [ ] 34. Chat view (user / THANS / system message styles, auto-scroll)
- [ ] 35. Text input bar — Enter handling, command history (Up/Down)
- [ ] 36. Model status panel (STT/TTS/LLM chips) + one-click "download models" button
- [ ] 37. Working-root picker + safety indicator in status bar
- [ ] 38. Settings dialog (TTS on/off + rate, LLM on/off + model picker, permanent-delete toggle, root)
- [ ] 39. Threaded command execution (worker thread + queue so UI never blocks)
- [ ] 40. Status bar (current dir, busy state, version)

## Phase 5 — Offline audio (steps 41–44)

- [ ] 41. `thans/stt.py` — Vosk offline speech-to-text (mic 16 kHz, int16 streaming)
- [ ] 42. Mic thread with endpointing (final transcript → command pipeline), clean stop
- [ ] 43. `thans/tts.py` — pyttsx3 offline text-to-speech on dedicated worker thread (queue-based, silent-fail)
- [ ] 44. Voice loop wiring: listen → parse → act → speak result

## Phase 6 — Optional offline LLM (steps 45–47)

- [ ] 45. `thans/parser_llm.py` — llama.cpp wrapper, strict JSON-only system prompt, action whitelist validation, JSON extraction from LLM output
- [ ] 46. LLM model catalog + placement in `models/` (default Qwen2.5-0.5B-Instruct Q4_K_M ≈ 408 MB; smaller/larger alternatives documented)
- [ ] 47. Fallback chain: rule parser → LLM parser (if enabled) → polite "I didn't catch that — say 'help'"

## Phase 7 — Packaging, installer & QA (steps 48–50)

- [ ] 48. `scripts/build_installer.py` — PyInstaller one-file build (windowed, `--name THANS`)
- [ ] 49. `installer/windows/` — `build_exe.bat` + Inno Setup `setup.iss` (desktop shortcut, optional models bundle, uninstaller)
- [ ] 50. `installer/linux/` — `build_exe.sh` + `install.sh` + `thans.desktop`; full test-suite run (`--selftest`) green; final README polish

---

## Changelog

| Date | Step(s) | Note |
|------|---------|------|
| 2026-10-12 | — | Plan created (50 steps). Build starting. |

## Known decisions (so future sessions don't re-litigate)

- **Name:** THANS. **UI:** tkinter (stdlib) with a small dark theme.
- **STT:** Vosk `vosk-model-small-en-us-0.15` (≈ 40 MB) — fully offline.
- **TTS:** `pyttsx3` (system voices: SAPI5 on Windows, espeak/NSSpeech elsewhere) — zero download.
- **LLM (optional):** `llama-cpp-python` + GGUF in `models/`. Default **Qwen2.5-0.5B-Instruct Q4_K_M (≈ 408 MB)** — best tiny model for strict-JSON command extraction. App works 100 % without it (rule parser covers all documented commands).
- **Safety:** all ops confined to one working root; deletes go to trash by default; single-level undo; config in `~/.thans/config.json`.
- **Python ≥ 3.10.** Tests run via `python -m unittest` (no pytest dependency).

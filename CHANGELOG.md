# Changelog

## 0.2.0 — 2026-10-12

Deployment-ready audit of the offline desktop + Android assistant.

### Security
- Confine **every** resolved path (list / open / delete / search / organize / undo)
  to the working root. `../`, absolute paths and outbound symlinks are rejected.
- Undo, trash and restore now re-check confinement before touching the disk.

### Bug fixes
- Vosk model detection now accepts the official `am/final.mdl` layout (the
  downloader no longer looks for a non-existent `model.bin` and then aborts).
- Default GGUF filename matches the Hugging Face download
  (`qwen2.5-0.5b-instruct-q4_k_m.gguf`); lookup is case-insensitive.
- `unique_dest` keeps the extension (`report (1).pdf`) and starts at `(1)`.
- PyInstaller `--icon` / `--onedir` flags are passed to PyInstaller, not to
  the Python interpreter.
- Android `SpeechRecognizer` listener is a real `PythonJavaClass` implementing
  every `RecognitionListener` method; TTS uses the API-21 `speak(..., Bundle, id)`
  signature.
- Windows / Linux installer scripts fail the build if `--selftest` fails.

### Packaging
- `android/buildozer.spec` pins Kivy 2.3.0, NDK 25b, API 33.
- GitHub Actions APK workflow runs on `main` and `arena/**`, uploads the
  `thans-android` artifact, and (on push) commits `releases/THANS-android.apk`.
- MIT `LICENSE` added.

## 0.1.0

Initial offline assistant (rule parser, trash, desktop UI, Android port).

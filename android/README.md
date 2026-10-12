# THANS for Android

The **same offline assistant** on your phone: the exact same `thans` core
(rule parser, safe action engine, trash + undo) with a Kivy touch UI.

| Capability | Android | Notes |
|---|---|---|
| Text commands (full set) | ✅ always | offline, zero models |
| Voice input (MIC button) | ⚠️ best-effort | uses the device's speech service (Android `SpeechRecognizer`); fully offline only if the device has an offline voice pack (Google: *Settings → Google → Offline voice*) |
| Spoken replies (SPEAK) | ✅ | system TextToSpeech |
| Working folder | app's private storage | `os.getcwd()` (P4A files dir) — the only storage Android apps may manage without broad permissions |
| LLM free-form parsing | ❌ | desktop-only (no llama.cpp NDK recipe); the rule parser covers every documented command, so nothing essential is lost |
| Delete-to-trash / undo | ✅ | trash lives in the app folder |

## Get the APK — option A: GitHub Actions (no local tools)

1. In your repo, open the **Actions** tab → **Build Android APK** → **Run workflow**.
   (The workflow also runs automatically on pushes to `main` that touch `android/` or `thans/`.)
2. When the job finishes (≈ 20–45 min — it downloads the Android SDK on a
   fresh runner), open the job → **artifacts** → download **`thans-android`**.
3. Install the `.apk` (allow "install unknown apps" for your browser/file app).

## Get the APK — option B: build locally

```bash
# Linux (easiest); Windows/macOS need the Android SDK + NDK first
sudo apt install -y git zip unzip openjdk-17-jdk python3-pip autoconf libtool pkg-config
python3 -m pip install --upgrade pip
python3 -m pip install buildozer cython

cd android
./stage_thans.sh        # copies the shared core ../thans into this project
buildozer android debug # → android/bin/*.apk   (first run downloads SDK ~1 GB)
```

Then `adb install bin/THANS-0.1-....apk` or copy the file to the phone.

## Project layout

```
android/
├── main.py               buildozer entry point
├── buildozer.spec        packaging config (kivy + pyjnius, mic permission)
├── stage_thans.sh        copies the shared core package in (build step)
├── thans.kv              UI layout (Kivy language)
├── thans_android/
│   ├── app.py            chat UI + engine wiring (Kivy thread-safe)
│   └── audio.py          guarded SpeechRecognizer / TextToSpeech bridge
└── thans/                ← staged copy of the core package (git-ignored)
```

## Try it

After install: press **HELP** for the command list, then type (or speak) things like
`create folder work`, `create file todo.txt with buy milk in work`,
`move todo.txt to work`, `organize work`, `delete work`, `undo`.

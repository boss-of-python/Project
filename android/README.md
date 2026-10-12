# THANS for Android

The **same offline assistant** on your phone: the exact same `thans` core
(rule parser, safe action engine, trash + undo) with a Kivy touch UI.

| Capability | Android | Notes |
|---|---|---|
| Text commands (full set) | ✅ always | offline, zero models |
| Live Intent Preview & `⚡ Complete` | ✅ always | real-time action badge & filename autocomplete as you type |
| Dual-Tab UI (`💬 Chat` + `📁 Files`) | ✅ always | animated chat cards + visual touch file explorer with one-tap `♻️` trash |
| Sonic Wave Visualizer & Themes | ✅ always | animated equalizer bar (reacts to mic RMS & state) + Dark/Light themes (`☀️/🌙`) |
| Voice input (`🎤 MIC` button) | ⚠️ best-effort | uses Android `SpeechRecognizer` (runtime mic permission & live partial transcript); fully offline if the device has an offline voice pack (*Settings → Google → Offline voice*) |
| Spoken replies (`SPEAK`) | ✅ | system TextToSpeech |
| Working folder | app's private storage | `os.getcwd()` (P4A files dir) — the only storage Android apps may manage without broad permissions |
| LLM free-form parsing | ❌ | desktop-only (no llama.cpp NDK recipe); the rule parser covers every documented command |
| Delete-to-trash / undo | ✅ | trash lives in the app folder; reversible via `↩ Undo` (including `organize`) |

## Look and feel

The phone UI shares the desktop palette, type scale and motion language from
`thans/animations.py` and `thans/ui_helpers.py`. There is one design system
in the repository — the Android app imports those modules directly.

* **Transcript:** message bubbles ease in; errors are tinted red.
* **Composer:** as-you-type intent preview, a mic button, and Send.
* **Files tab:** tap a folder to enter it, tap a file to rename, `♻️` to trash.
* **Touch targets:** ≥ 44 dp for every button.

## Tests

```bash
python -m thans --selftest                 # from the repo root
python -m unittest tests.test_android_ui -v
```

These run **without a display, without GL and without Kivy installed**: the
Android tests stub Kivy, parse `thans.kv`, and verify that every `app.*`
reference exists on the app class and every id used by Python is declared in
the layout. The same job runs in CI before the APK build.

## Get the APK — option A: GitHub Actions (no local tools)

1. In your repo, open the **Actions** tab → **Build Android APK** → **Run workflow**.
   (The workflow also runs on pushes to `main` / `arena/**` that touch `android/` or `thans/`.)
2. When the job finishes (≈ 20–45 min on a fresh runner), open the job →
   **artifacts** → download **`thans-android`**.
3. A copy is also committed to [`releases/THANS-android.apk`](../releases/THANS-android.apk)
   when the workflow runs on a push.
4. Install the `.apk` (allow "install unknown apps" for your browser/file app).

## Get the APK — option B: build locally

```bash
# Linux (easiest); Windows/macOS need the Android SDK + NDK first
sudo apt install -y git zip unzip openjdk-17-jdk python3-pip autoconf libtool pkg-config
python3 -m pip install --upgrade pip
python3 -m pip install "buildozer==1.5.0" "cython==0.29.36"

scripts/build_apk.sh          # selftest + stage + buildozer android debug
# → android/bin/*.apk
```

Then `adb install android/bin/*.apk` or copy the file to the phone.

## Project layout

```
android/
├── main.py               buildozer entry point
├── buildozer.spec        packaging config (kivy 2.3 + pyjnius, NDK 25b, mic permission)
├── stage_thans.sh        copies the shared core package in (build step)
├── thans.kv              UI layout (Kivy language)
├── thans_android/
│   ├── app.py            chat UI + engine wiring (Kivy thread-safe)
│   ├── audio.py          guarded SpeechRecognizer / TextToSpeech bridge
│   └── assets/           icon + presplash
└── thans/                ← staged copy of the core package (git-ignored)
```

## Try it

After install: press **HELP** for the command list, then type (or speak) things like
`create folder work`, `create file todo.txt with buy milk in work`,
`move todo.txt to work`, `organize work`, `delete work`, `undo`.

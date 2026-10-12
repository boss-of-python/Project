# THANS for Android

The **same offline assistant** on your phone: the exact same `thans` core
(rule parser, safe action engine, trash + undo) with a Kivy touch UI.

| Capability | Android | Notes |
|---|---|---|
| Text commands (full set) | ✅ always | offline, zero models |
| Live Intent Preview & `⚡ Complete` | ✅ always | real-time action badge & filename autocomplete as you type |
| Dual-Tab UI (`💬 Chat` + `📁 Files`) | ✅ always | animated chat cards + visual touch file explorer with one-tap `♻️` trash |
| Sonic Wave Visualizer & Themes | ✅ always | animated equalizer bar (reacts to mic RMS & state) + Dark/Light themes (`☀️/🌙`) |
| Voice input (`🎤 MIC` button) | ⚠️ best-effort | uses Android `SpeechRecognizer` (with runtime mic permission & live partial transcript); fully offline if the device has an offline voice pack (*Settings → Google → Offline voice*) |
| Spoken replies (`SPEAK`) | ✅ | system TextToSpeech |
| Working folder | app's private storage | `os.getcwd()` (P4A files dir) — the only storage Android apps may manage without broad permissions |
| LLM free-form parsing | ❌ | desktop-only (no llama.cpp NDK recipe); the rule parser covers every documented command, so nothing essential is lost |
| Delete-to-trash / undo | ✅ | trash lives in the app folder; reversible via `↩ Undo` (including `organize`) |

## Look and feel

The phone UI is the desktop app, adapted for thumbs — same palette, type scale
and motion language, all taken from `thans_android/theme.py`, which *derives*
its colours from the desktop design tokens (`thans/ui/theme.py`). There is
literally one palette in the repository.

* **Boot:** the mark and wordmark grow in over a gradient sweep while the engine
  really starts (no fake progress bar).
* **Transcript:** message bubbles grow+ease in, newest on top; THANS bubbles
  carry a `source` tag (`rules`) and errors are tinted red with a toast.
* **Composer:** as-you-type suggestion pills (`logic.suggest` — the same code the
  desktop uses), a mic button whose ring breathes while listening, and a Send
  button that lights up.
* **Hero card:** first-run card with three tap-to-fill starters; it fades out
  once you send your first command.
* **Feedback:** toasts stack under the header and dismiss themselves; the busy
  sweep + thinking dots appear only while a command runs.
* **Touch targets:** ≥ 44 dp for every button; the mic is bottom-right where a
  thumb rests, and Android's back button stops listening instead of leaving.

## Tests

```bash
python -m unittest tests.test_android_app -v   # from the repo root
```

These run **without a display, without GL and without Kivy installed**: a fake
Kivy (`tests/fakekivy.py`) provides widgets, properties, canvas instructions,
animations and a virtual clock, while the *static* checks parse `thans.kv` and
verify that every `app.*` reference exists on the app class and every id used by
Python is declared in the layout. The same job runs in CI before the APK build,
so a broken layout fails the build instead of the phone.

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

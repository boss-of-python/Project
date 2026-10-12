[app]
title = THANS
package.name = thans
package.domain = org.thans
source.dir = .
source.include_exts = py,kv,json,md,txt,png
source.exclude_dirs = tests,bin,.buildozer
version = 0.2.0

# Android needs only pure-Python core + Kivy UI + pyjnius for the (optional)
# on-device speech/TTS bridge. No vosk/sounddevice/pyttsx3 — those are desktop-only.
requirements = python3,kivy,pyjnius,android

icon.filename = %(source.dir)s/thans_android/assets/icon.png
presplash.filename = %(source.dir)s/thans_android/assets/presplash.png
android.presplash_color = #0d0f14

orientation = portrait
fullscreen = 0

# microphone access (voice commands are best-effort; text always works)
android.permissions = RECORD_AUDIO
android.api = 33
android.minapi = 21
android.ndk = 25b
android.ndk_api = 21
android.archs = arm64-v8a
android.accept_sdk_license = True
android.allow_backup = True
p4a.branch = master

[buildozer]
log_level = 2
warn_on_root = 0

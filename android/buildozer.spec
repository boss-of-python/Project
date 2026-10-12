[app]
title = THANS
package.name = thans
package.domain = org.thans
source.dir = .
source.include_exts = py,pvs,kv,json,md,txt
version = 0.1.0

# Android needs only pure-Python core + Kivy UI + pyjnius for the (optional)
# on-device speech/TTS bridge. No vosk/sounddevice/pyttsx3 — those are desktop-only.
requirements = python3,kivy,pyjnius,android

orientation = portrait
fullscreen = 0
landscape = 0

# microphone access (voice commands are best-effort; text always works)
android.permissions = RECORD_AUDIO
android.api = 33
android.minapi = 21
android.archs = arm64-v8a,armeabi-v7a
android.accept_sdk_license = true

[buildozer]
log_level = info
warn_on_root = 0

"""Best-effort on-device audio for Android (pyjnius → platform APIs).

* TTS: android.speech.tts.TextToSpeech (works on virtually every device).
* STT: android.speech.SpeechRecognizer (the device's speech service —
  offline only if the device has an offline voice pack installed, e.g.
  Google: Settings → Google → Settings → Offline voice).

Everything is guarded: if any part is missing the app keeps working as a
text assistant. Desktop uses Vosk/pyttsx3 instead; this module exists only
for Android (imported by thans_android.app).
"""
from __future__ import annotations

import os
import re

ANDROID = "ANDROID_DATA" in os.environ or "ANDROID_ROOT" in os.environ

_ctx = None
_tts = None
_sr = None
_listener = None


def _context():
    global _ctx
    if _ctx is None:
        from jnius import autoclass
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        _ctx = PythonActivity.mActivity
    return _ctx


# ---------------------------------------------------------------- TTS
def tts_available() -> bool:
    global _tts
    if not ANDROID:
        return False
    if _tts is None:
        try:
            from jnius import autoclass
            TextToSpeech = autoclass("android.speech.tts.TextToSpeech")
            _tts = TextToSpeech(_context(), None)
            try:
                _tts.setSpeechRate(1.05)
            except Exception:
                pass
        except Exception:
            _tts = False
    return bool(_tts)


def speak(text: str) -> None:
    if not tts_available():
        return
    try:
        t = re.sub(r"[#*`>|_]+", " ", text or "")
        t = re.sub(r"\s+", " ", t).strip()[:300]
        if t:
            _tts.speak(t, 0, None)
    except Exception:
        pass


# ---------------------------------------------------------------- STT
def stt_available() -> bool:
    """True when the device actually has a recognition service (cheap check)."""
    if not ANDROID:
        return False
    try:
        from jnius import autoclass
        SpeechRecognizer = autoclass("android.speech.SpeechRecognizer")
        return bool(SpeechRecognizer.isRecognitionAvailable(_context()))
    except Exception:
        return False


def _make_listener(on_result):
    """Python implementation of android.speech.RecognitionListener (jnius)."""
    from jnius import JavaClass, autoclass

    RecognitionListener = autoclass("android.speech.RecognitionListener")

    class L(JavaClass):  # noqa: N801 - jnius requires Java-style names
        __javainterfaces__ = ["android.speech.RecognitionListener"]

        def onBeginningOfSpeech(self):
            pass

        def onBufferReceived(self, buffer):
            pass

        def onEndOfSpeech(self):
            pass

        def onError(self, error):
            on_result(None, f"error {error}")

        def onEvent(self, event_type, params):
            pass

        def onPartialResults(self, bundle):
            pass

        def onResults(self, bundle):
            text = None
            try:
                matches = bundle.getCharSequenceArrayList("android.speech.extra.RESULTS")
                if matches is not None:
                    text = matches.get(0)
            except Exception:
                text = None
            on_result(text, None)

        def onRmsChanged(self, rms):
            pass

    return L()


def start_listening(on_result) -> bool:
    """Request speech recognition. on_result(text, error) — Android thread."""
    global _sr, _listener
    if not ANDROID:
        on_result(None, "not Android")
        return False
    try:
        from jnius import autoclass
        Intent = autoclass("android.content.Intent")
        SpeechRecognizer = autoclass("android.speech.SpeechRecognizer")
        if not SpeechRecognizer.isRecognitionAvailable(_context()):
            on_result(None, "no recognition service on device")
            return False
        stop_listening()
        _sr = SpeechRecognizer.createSpeechRecognizer(_context())
        _listener = _make_listener(on_result)  # keep a reference (no GC)
        _sr.setRecognitionListener(_listener)
        intent = Intent("android.intent.action.RECOGNIZE_SPEECH")
        intent.putExtra("android.speech.extra.LANGUAGE_MODEL",
                        "android.speech.extra.LANGUAGE_MODEL_FREE_FORM")
        _sr.startListening(intent)
        return True
    except Exception as e:  # noqa: BLE001
        on_result(None, f"init failed: {e}")
        return False


def stop_listening() -> None:
    global _sr
    if _sr is not None:
        try:
            _sr.stopListening()
            _sr.destroy()
        except Exception:
            pass
        _sr = None

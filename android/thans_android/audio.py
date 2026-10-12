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
from typing import Callable, Optional

ANDROID = "ANDROID_DATA" in os.environ or "ANDROID_ROOT" in os.environ

_ctx = None
_tts = None
_tts_ready = False
_sr = None
_listener = None

# Friendly descriptions for android.speech.SpeechRecognizer error constants
SPEECH_ERRORS: dict[int, str] = {
    1: "network timeout",
    2: "network unavailable (check offline voice pack)",
    3: "audio recording error",
    4: "speech server error",
    5: "client side error",
    6: "no speech heard — try again",
    7: "didn't catch that — try speaking clearly",
    8: "recognizer busy",
    9: "microphone permission needed",
}


def _context():
    global _ctx
    if _ctx is None:
        from jnius import autoclass
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        _ctx = PythonActivity.mActivity
    return _ctx


def ensure_mic_permission() -> bool:
    """Ensure RECORD_AUDIO runtime permission is granted on Android 6.0+."""
    if not ANDROID:
        return False
    try:
        from android.permissions import Permission, check_permission, request_permissions
        if not check_permission(Permission.RECORD_AUDIO):
            request_permissions([Permission.RECORD_AUDIO])
            return False
        return True
    except Exception:
        # If android.permissions helper is unavailable, allow SpeechRecognizer to try
        return True


# ---------------------------------------------------------------- TTS
def _make_tts_init():
    """Python implementation of TextToSpeech.OnInitListener (jnius).

    TextToSpeech only accepts speak() after its async init finishes; without
    this callback the first (and often every) speak() call is silently lost.
    """
    from jnius import JavaClass

    class T(JavaClass):  # noqa: N801 - jnius requires Java-style names
        __javainterfaces__ = ["android.speech.tts.TextToSpeech$OnInitListener"]

        def onInit(self, status):
            global _tts, _tts_ready
            if status == 0 and _tts is not None:  # TEXT_TO_SPEECH_SUCCESS
                try:
                    _tts.setSpeechRate(1.05)
                except Exception:
                    pass
                _tts_ready = True
            else:
                _tts = False  # mark unavailable for good

    return T()


def tts_available() -> bool:
    global _tts
    if not ANDROID:
        return False
    if _tts is None:
        try:
            from jnius import autoclass
            TextToSpeech = autoclass("android.speech.tts.TextToSpeech")
            _tts = TextToSpeech(_context(), _make_tts_init())
        except Exception:
            _tts = False
    return bool(_tts)  # device has a TTS engine (init may still be running)


def speak(text: str) -> None:
    if not tts_available() or not _tts_ready:
        return  # speak() before async init completes is dropped by Android
    try:
        t = re.sub(r"[#*`>|_]+", " ", text or "")
        t = re.sub(r"\s+", " ", t).strip()[:300]
        if t:
            _tts.speak(t, 0, None)
    except Exception:
        pass


# ---------------------------------------------------------------- STT
def _make_listener(
    on_result: Callable[[Optional[str], Optional[str]], None],
    on_partial: Optional[Callable[[str], None]] = None,
    on_rms: Optional[Callable[[float], None]] = None,
):
    """Python implementation of android.speech.RecognitionListener (jnius)."""
    from jnius import JavaClass, autoclass

    autoclass("android.speech.RecognitionListener")

    class L(JavaClass):  # noqa: N801 - jnius requires Java-style names
        __javainterfaces__ = ["android.speech.RecognitionListener"]

        def onBeginningOfSpeech(self):
            pass

        def onBufferReceived(self, buffer):
            pass

        def onEndOfSpeech(self):
            pass

        def onError(self, error):
            code = int(error) if isinstance(error, (int, float)) else -1
            msg = SPEECH_ERRORS.get(code, f"error {error}")
            on_result(None, msg)

        def onEvent(self, event_type, params):
            pass

        def onPartialResults(self, bundle):
            if on_partial is None:
                return
            try:
                matches = bundle.getCharSequenceArrayList("android.speech.extra.RESULTS")
                if matches is not None and matches.size() > 0:
                    partial = str(matches.get(0) or "").strip()
                    if partial:
                        on_partial(partial)
            except Exception:
                pass

        def onResults(self, bundle):
            text = None
            try:
                matches = bundle.getCharSequenceArrayList("android.speech.extra.RESULTS")
                if matches is not None and matches.size() > 0:
                    text = str(matches.get(0) or "").strip()
            except Exception:
                text = None
            on_result(text, None)

        def onRmsChanged(self, rms):
            if on_rms is not None:
                try:
                    on_rms(float(rms))
                except Exception:
                    pass

    return L()


def start_listening(
    on_result: Callable[[Optional[str], Optional[str]], None],
    on_partial: Optional[Callable[[str], None]] = None,
    on_rms: Optional[Callable[[float], None]] = None,
) -> bool:
    """Request speech recognition. on_result(text, error) — Android thread."""
    global _sr, _listener
    if not ANDROID:
        on_result(None, "not Android")
        return False
    if not ensure_mic_permission():
        on_result(None, "microphone permission requested — tap MIC again once allowed")
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
        _listener = _make_listener(on_result, on_partial=on_partial, on_rms=on_rms)
        _sr.setRecognitionListener(_listener)
        intent = Intent("android.intent.action.RECOGNIZE_SPEECH")
        intent.putExtra("android.speech.extra.LANGUAGE_MODEL",
                        "android.speech.extra.LANGUAGE_MODEL_FREE_FORM")
        intent.putExtra("android.speech.extra.PARTIAL_RESULTS", True)
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

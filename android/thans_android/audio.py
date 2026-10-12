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
        if not t:
            return
        # API 21+ speak(CharSequence, queueMode, Bundle, utteranceId)
        try:
            from jnius import autoclass
            Bundle = autoclass("android.os.Bundle")
            _tts.speak(t, 0, Bundle(), "thans-utterance")
        except Exception:
            _tts.speak(t, 0, None)
    except Exception:
        pass


# ---------------------------------------------------------------- STT
def _make_listener(
    on_result: Callable[[Optional[str], Optional[str]], None],
    on_partial: Optional[Callable[[str], None]] = None,
    on_rms: Optional[Callable[[float], None]] = None,
):
    """Python implementation of android.speech.RecognitionListener (jnius).

    Must be a ``PythonJavaClass`` (not ``JavaClass``) so pyjnius actually
    implements the Java interface. Every RecognitionListener method is
    declared — missing ones crash the recognizer on some Android versions.
    """
    from jnius import PythonJavaClass, java_method

    class Listener(PythonJavaClass):
        __javainterfaces__ = ["android/speech/RecognitionListener"]
        __javacontext__ = "app"

        def __init__(self):
            super().__init__()
            self._on_result = on_result
            self._on_partial = on_partial
            self._on_rms = on_rms

        @java_method("()V")
        def onBeginningOfSpeech(self):
            pass

        @java_method("([B)V")
        def onBufferReceived(self, buffer):
            pass

        @java_method("()V")
        def onEndOfSpeech(self):
            pass

        @java_method("(I)V")
        def onError(self, error):
            try:
                code = int(error)
            except (TypeError, ValueError):
                code = -1
            msg = SPEECH_ERRORS.get(code, f"error {error}")
            self._on_result(None, msg)

        @java_method("(ILandroid/os/Bundle;)V")
        def onEvent(self, event_type, params):
            pass

        @java_method("(Landroid/os/Bundle;)V")
        def onPartialResults(self, bundle):
            if self._on_partial is None or bundle is None:
                return
            try:
                matches = bundle.getStringArrayList("android.speech.extra.RESULTS")
                if matches is None:
                    matches = bundle.getCharSequenceArrayList("android.speech.extra.RESULTS")
                if matches is not None and matches.size() > 0:
                    partial = str(matches.get(0) or "").strip()
                    if partial:
                        self._on_partial(partial)
            except Exception:
                pass

        @java_method("(Landroid/os/Bundle;)V")
        def onReadyForSpeech(self, params):
            pass

        @java_method("(Landroid/os/Bundle;)V")
        def onResults(self, bundle):
            text = None
            try:
                if bundle is not None:
                    matches = bundle.getStringArrayList("android.speech.extra.RESULTS")
                    if matches is None:
                        matches = bundle.getCharSequenceArrayList("android.speech.extra.RESULTS")
                    if matches is not None and matches.size() > 0:
                        text = str(matches.get(0) or "").strip()
            except Exception:
                text = None
            self._on_result(text, None)

        @java_method("(F)V")
        def onRmsChanged(self, rms):
            if self._on_rms is None:
                return
            try:
                self._on_rms(float(rms))
            except Exception:
                pass

    return Listener()


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
        intent = Intent("android.speech.action.RECOGNIZE_SPEECH")
        intent.putExtra("android.speech.extra.LANGUAGE_MODEL",
                        "android.speech.extra.LANGUAGE_MODEL_FREE_FORM")
        intent.putExtra("android.speech.extra.PARTIAL_RESULTS", True)
        intent.putExtra("android.speech.extra.MAX_RESULTS", 3)
        _sr.startListening(intent)
        return True
    except Exception as e:  # noqa: BLE001
        on_result(None, f"init failed: {e}")
        return False


def stop_listening() -> None:
    global _sr, _listener
    if _sr is not None:
        try:
            _sr.stopListening()
        except Exception:
            pass
        try:
            _sr.cancel()
        except Exception:
            pass
        try:
            _sr.destroy()
        except Exception:
            pass
        _sr = None
    _listener = None

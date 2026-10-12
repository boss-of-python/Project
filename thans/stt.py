"""Offline speech-to-text via Vosk (microphone → text, fully offline).

Model: models/vosk-model-small-en-us-0.15 (downloaded once by
scripts/download_models.py). Endpointing: Vosk finalises a transcript on
trailing silence, which maps nicely to short file commands.
"""
from __future__ import annotations

from array import array
import json
import math
import threading
import time
from typing import Callable, Optional

from . import model_manager

SAMPLE_RATE = 16000
BLOCK_SIZE = 4000          # 0.25 s of 16 kHz audio for snappy live feedback
MAX_RECORD_SECONDS = 30    # hard cap per utterance


def _pcm16_rms(raw: bytes) -> float:
    """Compute normalized RMS amplitude [0.0, 1.0] from int16 PCM bytes."""
    if not raw or len(raw) < 2:
        return 0.0
    try:
        samples = array("h")
        samples.frombytes(raw[: len(raw) - (len(raw) % 2)])
        if not samples:
            return 0.0
        # Sample every 4th frame for speed
        step = max(1, len(samples) // 256)
        sub = samples[::step]
        mean_sq = sum(s * s for s in sub) / len(sub)
        rms = math.sqrt(mean_sq) / 8000.0
        return max(0.0, min(1.0, rms))
    except Exception:
        return 0.0


class VoiceSTT:
    """Push-to-talk (toggle) microphone recognition with live partial & RMS callbacks."""

    def __init__(self) -> None:
        self.model_dir = model_manager.vosk_model_dir()
        self.recording = False
        self._model = None
        self._rec = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------- state
    def available(self) -> bool:
        self.model_dir = model_manager.vosk_model_dir()
        return self.model_dir is not None

    def _ensure_engine(self) -> None:
        if self._rec is not None:
            return
        from vosk import KaldiRecognizer, Model
        self._model = Model(str(self.model_dir))
        self._rec = KaldiRecognizer(self._model, SAMPLE_RATE)

    # ---------------------------------------------------------- control
    def start(
        self,
        on_final: Callable[[str], None],
        on_state: Optional[Callable[[str], None]] = None,
        on_partial: Optional[Callable[[str], None]] = None,
        on_level: Optional[Callable[[float], None]] = None,
    ) -> bool:
        """Start recording in a background thread. Returns False if not ready."""
        if self.recording or not self.available():
            return False
        self._stop.clear()
        self.recording = True

        def state(msg: str) -> None:
            if on_state:
                on_state(msg)

        def worker() -> None:
            try:
                import sounddevice as sd
            except Exception as e:  # noqa: BLE001
                self.recording = False
                hint = " (Linux: sudo apt install libportaudio2)" if isinstance(e, OSError) else ""
                state(f"sounddevice unavailable: {e}{hint}")
                return
            try:
                self._ensure_engine()
            except Exception as e:  # noqa: BLE001
                self.recording = False
                state(f"STT engine error: {e}")
                return
            try:
                last_partial = ""
                with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=BLOCK_SIZE,
                                       dtype="int16", channels=1) as stream:
                    started = time.time()
                    while not self._stop.is_set():
                        if time.time() - started > MAX_RECORD_SECONDS:
                            break
                        data, _overflowed = stream.read(BLOCK_SIZE)
                        raw = bytes(data)
                        if on_level is not None:
                            on_level(_pcm16_rms(raw))
                        if self._rec.AcceptWaveform(raw):
                            text = (json.loads(self._rec.Result()).get("text") or "").strip()
                            if text:
                                self.recording = False
                                on_final(text)
                                return
                        elif on_partial is not None:
                            part = (json.loads(self._rec.PartialResult()).get("partial") or "").strip()
                            if part and part != last_partial:
                                last_partial = part
                                on_partial(part)
            except Exception as e:  # noqa: BLE001
                state(f"Microphone error: {e}")
            finally:
                self.recording = False
                if on_level is not None:
                    on_level(0.0)
                state("mic stopped")

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()
        state("listening…")
        return True

    def stop(self) -> None:
        self._stop.set()

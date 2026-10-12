"""Offline text-to-speech via pyttsx3 (OS voices: SAPI5 / NSSpeech / espeak).

Runs on a dedicated worker thread so the UI never blocks; silently disables
itself if no system TTS backend is available.
"""
from __future__ import annotations

import queue
import re
import threading
from typing import Optional


class Speaker:
    def __init__(self, enabled: bool = True, rate: int = 185):
        self.enabled = bool(enabled)
        self.rate = int(rate)
        self.available = False
        self._q: "queue.Queue" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        if self.enabled:
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def _loop(self) -> None:
        try:
            import pyttsx3
            engine = pyttsx3.init()
            try:
                engine.setProperty("rate", self.rate)
            except Exception:
                pass
            self.available = True
        except Exception:
            self.available = False
            return
        while True:
            item = self._q.get()
            if item is None:
                break
            if isinstance(item, tuple) and item and item[0] == "__rate__":
                try:
                    engine.setProperty("rate", int(item[1]))
                except Exception:
                    pass
                continue
            try:
                engine.say(item)
                engine.runAndWait()
            except Exception:
                continue

    def say(self, text: str) -> None:
        """Non-blocking: queue a cleaned, truncated chunk of text."""
        if not self.enabled or not text:
            return
        t = re.sub(r"[#*`>|_\[\]()]+", " ", text)
        t = re.sub(r"\s+", " ", t).strip()
        if not t:
            return
        # Keep the queue bounded: if the TTS worker ever dies, `say()` calls
        # must not accumulate without limit.
        try:
            if self._q.qsize() >= 50:
                self._q.get_nowait()  # drop the oldest, keep the freshest
        except queue.Empty:
            pass
        self._q.put(t[:400])

    def set_rate(self, rate: int) -> None:
        self.rate = int(rate)
        self._q.put(("__rate__", int(rate)))

    def stop(self) -> None:
        self._q.put(None)

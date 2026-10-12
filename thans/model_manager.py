"""Detect which offline models are installed in the dedicated ``models/`` dir.

The UI chips, the CLI (``--models``) and the one-click downloader all read
their state from here, so model presence is never assumed.
"""
from __future__ import annotations

from pathlib import Path

from . import config


def vosk_model_dir() -> Path | None:
    """Return the Vosk STT model dir if installed, else None."""
    p = config.models_dir() / config.VOSK_MODEL_NAME
    return p if (p / "model.bin").exists() else None


def llm_model_path(cfg: dict | None = None) -> Path | None:
    """Return the configured GGUF LLM file if it exists, else None."""
    name = (cfg or {}).get("llm_model") or config.DEFAULT_LLM_MODEL
    p = config.models_dir() / name
    return p if p.is_file() else None


def all_gguf() -> list[Path]:
    return sorted(config.models_dir().glob("*.gguf"))


def tts_available() -> bool:
    """pyttsx3 imports (system TTS backend present)."""
    try:
        import pyttsx3  # noqa: F401
        return True
    except Exception:
        return False


def stt_deps_available() -> bool:
    try:
        import sounddevice  # noqa: F401
        return True
    except Exception:
        return False


def llm_deps_available() -> bool:
    try:
        import llama_cpp  # noqa: F401
        return True
    except Exception:
        return False


def status(cfg: dict | None = None) -> dict:
    """One-shot status map used by UI chips and ``--models``."""
    cfg = cfg or config.load_config()
    vosk = vosk_model_dir()
    llm = llm_model_path(cfg)
    stt_ok = vosk is not None
    llm_ok = llm is not None and llm_deps_available()
    return {
        "models_dir": str(config.models_dir()),
        "stt": stt_ok,
        "stt_model": str(vosk) if vosk else None,
        "stt_deps": stt_deps_available(),
        "tts": tts_available(),
        "llm": llm_ok,
        "llm_model": str(llm) if llm else None,
        "llm_deps": llm_deps_available(),
        "llm_enabled": bool(cfg.get("use_llm")),
        "gguf_count": len(all_gguf()),
    }


def status_lines(cfg: dict | None = None) -> list[str]:
    """Human-readable status (used by ``python -m thans --models``)."""
    s = status(cfg)
    mark = lambda ok: "OK " if ok else "MISSING"  # noqa: E731
    lines = [f"Models dir: {s['models_dir']}"]
    lines.append(f"  STT  (Vosk)      : {mark(s['stt'])}  {s['stt_model'] or ''}")
    if not s["stt"] and not s["stt_deps"]:
        lines.append("                   (sounddevice not installed — pip install sounddevice)")
    lines.append(f"  TTS  (system)    : {mark(s['tts'])}")
    lines.append(f"  LLM  (llama.cpp) : {mark(s['llm'])}  {'(enabled)' if s['llm_enabled'] else '(disabled)'}  {s['llm_model'] or ''}")
    if not s["llm"] and s["llm_model"]:
        lines.append("                   (model file missing — python scripts/download_models.py --only llm)")
    if not s["llm_deps"]:
        lines.append("                   (llama-cpp-python not installed — optional, rule parser still works)")
    lines.append('Download missing models:  python scripts/download_models.py')
    return lines

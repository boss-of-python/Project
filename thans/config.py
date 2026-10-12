"""Central configuration: paths, defaults, load/save.

Everything THANS needs to know about *where things live* is in this module:
  - the dedicated ``models/`` folder (STT model, optional LLM GGUF)
  - the user config file (``~/.thans/config.json``)
  - the working root that confines every file operation
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

APP_NAME = "THANS"
APP_VERSION = "0.2.0"  # keep in sync with thans/__init__.__version__

#: Name of the hidden trash folder created inside the working root.
TRASH_DIRNAME = ".thans_trash"

#: Default offline models (filenames inside ``models/``).
VOSK_MODEL_NAME = "vosk-model-small-en-us-0.15"
DEFAULT_LLM_MODEL = "Qwen2.5-0.5B-Instruct-Q4_K_M.gguf"

DEFAULTS: dict[str, Any] = {
    "root": str(Path.home()),        # working root (all ops confined to this)
    "tts": True,                     # speak replies
    "tts_rate": 185,                 # words per minute
    "use_llm": False,                # optional offline LLM parser
    "llm_model": DEFAULT_LLM_MODEL,  # GGUF filename inside models/
    "permanent_delete": False,       # if True, 'delete' skips the trash
    "theme": "dark",                 # "dark" | "light"
    "animations": True,              # 60fps sonic wave & smooth UI transitions
    "sidebar": True,                 # live file workspace inspector open
}


def app_root() -> Path:
    """Directory that contains the ``thans`` package (or the frozen exe dir)."""
    if getattr(sys, "frozen", False):  # PyInstaller onefile/onedir
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def models_dir() -> Path:
    """Dedicated folder where all offline models live."""
    return Path(os.environ.get("THANS_MODEL_DIR") or (app_root() / "models"))


def user_data_dir() -> Path:
    base = Path(os.environ.get("THANS_DATA_DIR") or (Path.home() / ".thans"))
    base.mkdir(parents=True, exist_ok=True)
    return base


def config_path() -> Path:
    return user_data_dir() / "config.json"


def load_config() -> dict[str, Any]:
    """Merge stored config over defaults (missing file → pure defaults)."""
    cfg = dict(DEFAULTS)
    p = config_path()
    if p.exists():
        try:
            stored = json.loads(p.read_text(encoding="utf-8"))
            for k in DEFAULTS:
                if k in stored:
                    cfg[k] = stored[k]
        except (json.JSONDecodeError, OSError):
            pass  # corrupt config → fall back to defaults
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    p = config_path()
    p.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def resolve_root(raw: str | Path) -> Path:
    """Expand + resolve a user-supplied working root."""
    p = Path(str(raw).strip()).expanduser()
    return p.resolve()

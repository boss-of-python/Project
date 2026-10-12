"""Cross-platform plumbing shared by the desktop GUI and the Android port.

Pure stdlib — safe to import anywhere (Windows / Linux / macOS / Android),
including inside a PyInstaller-frozen executable.

  * ``find_downloader``  — locate ``scripts/download_models.py`` plus a Python
    interpreter that can run it (the script itself is stdlib-only).
  * ``resolve_workdir``  — pick a guaranteed-writable working directory
    (Android: the app's internal files dir, with sane fallbacks).
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Optional

from . import config

DOWNLOAD_SCRIPT_NAME = "download_models.py"


# --------------------------------------------------------------------------
# Model-downloader discovery (desktop "⬇ Models" button)
# --------------------------------------------------------------------------


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def find_downloader(root: Optional[Path] = None) -> tuple[Path, str]:
    """Return ``(script_path, python_interpreter)`` for the model downloader.

    The downloader is stdlib-only, so *any* local Python 3.10+ can run it.
    Resolution order for the interpreter:
      * unfrozen (running from source): the current interpreter — always works
      * frozen (installed EXE):  python3 → python → py (Windows launcher)

    Raises FileNotFoundError / RuntimeError with an actionable message.
    """
    candidates: list[Path] = []
    env = os.environ.get("THANS_DOWNLOAD_SCRIPT")
    if env:
        candidates.append(Path(env))
    base = Path(root) if root is not None else config.app_root()
    candidates.append(base / "scripts" / DOWNLOAD_SCRIPT_NAME)

    script = next((c for c in candidates if c.is_file()), None)
    if script is None:
        raise FileNotFoundError(
            f"'{DOWNLOAD_SCRIPT_NAME}' was not found (looked in: "
            + ", ".join(str(c) for c in candidates)
            + "). Copy the 'scripts' folder next to the executable and retry."
        )

    if not _is_frozen():
        return script, sys.executable

    for name in ("python3", "python", "py"):
        found = shutil.which(name)
        if found:
            return script, found
    raise RuntimeError(
        "No system Python found to run the model downloader. "
        "Install Python 3.10+ (https://www.python.org) and retry, or run "
        f"'{script}' manually from a terminal."
    )


# --------------------------------------------------------------------------
# Working-directory resolution (Android & general)
# --------------------------------------------------------------------------


def _is_writable(p: Path) -> bool:
    try:
        p.mkdir(parents=True, exist_ok=True)
        probe = p / ".thans_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def resolve_workdir(preferred: Optional[str] = None) -> str:
    """Pick a guaranteed-writable working directory.

    On Android the process CWD is the app's internal files directory
    (private, persistent, writable). The writability probe makes the rest of
    the app safe even if the environment is unusual (read-only mount, etc.).
    """
    candidates: list[Path] = []
    if preferred:
        candidates.append(Path(preferred).expanduser())
    candidates.append(Path(os.getcwd()))
    candidates.append(Path(os.path.expanduser("~")))
    candidates.append(Path(tempfile.gettempdir()) / "thans")
    for c in candidates:
        if _is_writable(c):
            return str(c)
    return str(Path(os.getcwd()))


# --------------------------------------------------------------------------
# Dependency availability (used by UI chips & installers)
# --------------------------------------------------------------------------


def native_package_available(pkg: str) -> bool:
    """True if an (optional) native package is importable in this env."""
    try:
        return importlib.util.find_spec(pkg) is not None
    except (ImportError, ValueError):
        return False

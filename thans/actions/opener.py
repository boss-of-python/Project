"""Open items with the OS default app / file manager (works offline)."""
from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

from .common import find_item, rel


def open_item(root: Path, current: Path, path: str, reveal: bool = False):
    p = find_item(current, path)
    system = platform.system()
    try:
        if system == "Windows":
            if reveal:
                subprocess.Popen(["explorer", f"/select,{p}"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            else:
                os.startfile(p)  # type: ignore[attr-defined]
        elif system == "Darwin":
            subprocess.Popen(["open", str(p.parent if (reveal and p.is_file()) else p)])
        else:
            subprocess.Popen(["xdg-open", str(p.parent if (reveal and p.is_file()) else p)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:  # noqa: BLE001 - no display / no handler installed
        raise OSError(f"could not open '{p.name}': {e}") from e
    if reveal:
        return True, f"Showing '{rel(p, root)}' in the file manager.", None
    return True, f"Opening '{rel(p, root)}'.", None

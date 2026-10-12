"""Organize a folder: group loose files into subfolders by extension or date."""
from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

from .common import NotFoundError, find_item, rel, unique_dest


def organize(root: Path, current: Path, path: str | None = None, mode: str = "extension"):
    d = find_item(current, path) if path else current
    if not d.is_dir():
        raise NotFoundError(f"'{path}' is not a folder.")

    moved: dict[str, int] = {}
    moves_record: list[tuple[str, str]] = []
    created_dirs: list[str] = []
    for f in sorted(d.iterdir(), key=lambda p: p.name.casefold()):
        if not f.is_file() or f.name.startswith("."):
            continue
        if mode == "date":
            key = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m")
        else:
            key = f.suffix.lstrip(".").lower() or "other"
        key = re.sub(r"[^a-z0-9._-]", "_", key) or "other"
        target = d / key
        if not target.exists():
            target.mkdir(exist_ok=True)
            created_dirs.append(str(target))
        dest = unique_dest(target, f.name)
        shutil.move(str(f), str(dest))
        moves_record.append((str(dest), str(f)))
        moved[key] = moved.get(key, 0) + 1

    if not moved:
        return True, f"'{rel(d, root)}' already looks organized — nothing to move.", None

    total = sum(moved.values())
    summary = ", ".join(f"{k}/ ({n})" for k, n in sorted(moved.items()))
    record = {"action": "organize", "moves": moves_record, "dirs": created_dirs}
    return (True, f"Moved {total} file{'s' if total != 1 else ''} in '{rel(d, root)}' → {summary}.", record)

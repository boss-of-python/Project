"""File & folder operations. Every function is confined to the working root.

All functions return ``(ok, message, record)`` where ``record`` is a dict the
engine stores for single-level undo (resolved absolute paths as strings).
"""
from __future__ import annotations

import shutil
from pathlib import Path

from .common import NotFoundError, ensure_inside, find_item, rel, safe_path, to_trash


def _dest_path(root: Path, current: Path, dest: str, s: Path) -> Path:
    """Resolve a destination: an existing folder means 'into that folder'."""
    dp = safe_path(root, current, dest)
    if dp.is_dir():
        dp = dp / s.name
    elif dest.rstrip().endswith(("/", "\\")):
        dp = dp / s.name
        dp.parent.mkdir(parents=True, exist_ok=True)
    return dp


def _ensure_parent(dp: Path, dest: str, root: Path) -> None:
    if dp.parent.exists():
        return
    if dest.rstrip().endswith(("/", "\\")):
        dp.parent.mkdir(parents=True, exist_ok=True)
    else:
        bare = dest.rstrip("/\\")
        raise NotFoundError(f"destination folder '{rel(dp.parent, root)}' does not exist. "
                            f"Tip: say 'move {bare}/' to create it, or 'create folder {bare}' first.")


# --------------------------------------------------------------------------
# create
# --------------------------------------------------------------------------


def create_folder(root: Path, current: Path, name: str, in_dir: str | None = None):
    base = safe_path(root, current, in_dir or ".")
    if not base.is_dir():
        raise NotFoundError(f"folder '{in_dir}' does not exist.")
    d = safe_path(root, base, name)
    if d.exists():
        raise ValueError(f"'{rel(d, root)}' already exists.")
    d.mkdir(parents=True, exist_ok=False)
    return True, f"Created folder '{rel(d, root)}'.", {"action": "mkdir", "created": str(d)}


def create_file(root: Path, current: Path, name: str, content: str | None = None, in_dir: str | None = None):
    base = safe_path(root, current, in_dir or ".")
    if not base.is_dir():
        raise NotFoundError(f"folder '{in_dir}' does not exist.")
    d = safe_path(root, base, name)
    if d.exists():
        raise ValueError(f"'{rel(d, root)}' already exists.")
    d.parent.mkdir(parents=True, exist_ok=True)
    body = (content or "").strip("\n")
    d.write_text(body + ("\n" if body else ""), encoding="utf-8")
    return True, f"Created file '{rel(d, root)}'.", {"action": "touch", "created": str(d)}


# --------------------------------------------------------------------------
# list
# --------------------------------------------------------------------------


def list_dir(root: Path, current: Path, path: str | None = None, count_only: bool = False):
    d = find_item(current, path, root=root) if path else ensure_inside(root, current)
    if not d.is_dir():
        raise NotFoundError(f"'{path}' is not a folder.")
    entries = sorted(d.iterdir(), key=lambda p: (p.is_file(), p.name.casefold()))
    files = [e for e in entries if e.is_file()]
    folders = [e for e in entries if e.is_dir()]
    if count_only:
        return True, f"'{rel(d, root)}' has {len(folders)} folders and {len(files)} files.", None
    if not entries:
        return True, f"'{rel(d, root)}' is empty.", None
    lines = []
    for e in entries[:30]:
        lines.append(("📁 " if e.is_dir() else "📄 ") + e.name)
    if len(entries) > 30:
        lines.append(f"… and {len(entries) - 30} more")
    lines.append(f"({len(folders)} folders, {len(files)} files)")
    return True, "\n".join(lines), None


# --------------------------------------------------------------------------
# rename / move / copy / delete
# --------------------------------------------------------------------------


def rename_item(root: Path, current: Path, src: str, dest: str):
    s = find_item(current, src, root=root)
    # a plain new name (no '/') stays next to the original item
    base_for_dest = s.parent if ("/" not in dest and "\\" not in dest) else current
    dp = _dest_path(root, base_for_dest, dest, s)
    if dp.exists():
        raise ValueError(f"'{rel(dp, root)}' already exists.")
    dp.parent.mkdir(parents=True, exist_ok=True)
    s.rename(dp)
    return True, f"Renamed '{rel(s, root)}' → '{rel(dp, root)}'.", {"action": "rename", "src": str(s), "dest": str(dp)}


def move_item(root: Path, current: Path, src: str, dest: str):
    s = find_item(current, src, root=root)
    dp = _dest_path(root, current, dest, s)
    if dp.exists():
        raise ValueError(f"'{rel(dp, root)}' already exists.")
    _ensure_parent(dp, dest, root)
    shutil.move(str(s), str(dp))
    return True, f"Moved '{rel(s, root)}' → '{rel(dp, root)}'.", {"action": "move", "src": str(s), "dest": str(dp)}


def copy_item(root: Path, current: Path, src: str, dest: str):
    s = find_item(current, src, root=root)
    dp = _dest_path(root, current, dest, s)
    if dp.exists():
        raise ValueError(f"'{rel(dp, root)}' already exists.")
    _ensure_parent(dp, dest, root)
    if s.is_dir():
        shutil.copytree(str(s), str(dp))
    else:
        shutil.copy2(str(s), str(dp))
    return True, f"Copied '{rel(s, root)}' → '{rel(dp, root)}'.", {"action": "copy", "src": str(s), "dest": str(dp)}


def delete_item(root: Path, current: Path, path: str, permanent: bool = False):
    p = find_item(current, path, root=root)
    label = rel(p, root)
    if permanent:
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
        return True, f"Permanently deleted '{label}'.", {"action": "delete", "original": str(p), "permanent": True}
    t = to_trash(root, p)
    return (True, f"Moved '{label}' to trash (.thans_trash). Say 'undo' to bring it back.",
            {"action": "delete", "original": str(p), "trashed": str(t), "permanent": False})

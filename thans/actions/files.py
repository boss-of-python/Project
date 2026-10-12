"""File & folder operations. Every function is confined to the working root.

All functions return ``(ok, message, record)`` where ``record`` is a dict the
engine stores for single-level undo (resolved absolute paths as strings).
"""
from __future__ import annotations

import shutil
from pathlib import Path

from .common import NotFoundError, find_item, rel, safe_path, to_trash, trash_dir


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
    d = find_item(current, path) if path else current
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
    s = find_item(current, src)
    # a plain new name (no '/') stays next to the original item
    base_for_dest = s.parent if ("/" not in dest and "\\" not in dest) else current
    dp = _dest_path(root, base_for_dest, dest, s)
    if dp.exists():
        raise ValueError(f"'{rel(dp, root)}' already exists.")
    dp.parent.mkdir(parents=True, exist_ok=True)
    s.rename(dp)
    return True, f"Renamed '{rel(s, root)}' → '{rel(dp, root)}'.", {"action": "rename", "src": str(s), "dest": str(dp)}


def move_item(root: Path, current: Path, src: str, dest: str):
    s = find_item(current, src)
    dp = _dest_path(root, current, dest, s)
    if dp.exists():
        raise ValueError(f"'{rel(dp, root)}' already exists.")
    _ensure_parent(dp, dest, root)
    shutil.move(str(s), str(dp))
    return True, f"Moved '{rel(s, root)}' → '{rel(dp, root)}'.", {"action": "move", "src": str(s), "dest": str(dp)}


def copy_item(root: Path, current: Path, src: str, dest: str):
    s = find_item(current, src)
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
    p = find_item(current, path)
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


# --------------------------------------------------------------------------
# preview / trash / status
# --------------------------------------------------------------------------


def read_file_preview(root: Path, current: Path, path: str, max_chars: int = 2400):
    p = find_item(current, path)
    if p.is_dir():
        return list_dir(root, current, path)
    label = rel(p, root)
    try:
        raw = p.read_bytes()
    except OSError as e:
        raise OSError(f"could not read '{label}': {e}") from e
    size = len(raw)
    if not size:
        return True, f"📄 '{label}' is empty (0 B).", None
    if b"\x00" in raw[:512]:
        return True, f"📄 '{label}' is a binary file ({size} bytes) — say 'open {p.name}' to open it.", None
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    snippet = text[:max_chars].rstrip("\n")
    more = f"\n… (truncated, {size} bytes total)" if len(text) > max_chars else ""
    header = f"📄 {label} ({len(lines)} line{'s' if len(lines) != 1 else ''}, {size} B):"
    return True, f"{header}\n{snippet}{more}", None


def manage_trash(root: Path, mode: str = "list"):
    t = trash_dir(root)
    if not t.is_dir():
        return True, "Trash (.thans_trash) is empty.", None
    items = sorted(t.iterdir(), key=lambda p: p.name, reverse=True)
    if not items:
        return True, "Trash (.thans_trash) is empty.", None
    if mode == "empty":
        count = len(items)
        for item in items:
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                try:
                    item.unlink()
                except OSError:
                    pass
        return True, f"Emptied trash ({count} item{'s' if count != 1 else ''} removed).", None
    lines = [f"🗑 Trash contains {len(items)} item{'s' if len(items) != 1 else ''}:"]
    for item in items[:20]:
        orig_name = item.name.split("__", 1)[-1] if "__" in item.name else item.name
        kind = "📁" if item.is_dir() else "📄"
        lines.append(f"  {kind} {orig_name}  ({item.name})")
    if len(items) > 20:
        lines.append(f"  … and {len(items) - 20} more")
    lines.append("Say 'undo' to restore the most recent action, or 'empty trash' to clear.")
    return True, "\n".join(lines), None


def workspace_status(root: Path, current: Path, undo_count: int = 0):
    cur_rel = rel(current, root)
    entries = [e for e in current.iterdir() if not e.name.startswith(".") and e.name != ".thans_trash"] if current.is_dir() else []
    folders = sum(1 for e in entries if e.is_dir())
    files = sum(1 for e in entries if e.is_file())
    t = trash_dir(root)
    trashed = len(list(t.iterdir())) if t.is_dir() else 0
    return (
        True,
        f"📂 Current folder: '{cur_rel}' (inside root '{root.name or root}')\n"
        f"   • {folders} folder{'s' if folders != 1 else ''}, {files} file{'s' if files != 1 else ''} here\n"
        f"   • Trash: {trashed} item{'s' if trashed != 1 else ''}\n"
        f"   • Undo stack: {undo_count} action{'s' if undo_count != 1 else ''} ready",
        None,
    )

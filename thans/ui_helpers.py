"""Shared UX intelligence for THANS (Desktop tkinter + Android Kivy).

Provides:
  * Real-time intent preview as the user types (`preview_intent`)
  * Smart command & filename autocomplete (`autocomplete`)
  * Live directory snapshot & diff detection for animations (`dir_snapshot`)
  * Smart file icons, human-readable sizes, breadcrumbs, and quick-action chips
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import config
from .actions.common import rel
from .parser_rules import normalize, parse as parse_rules

# --------------------------------------------------------------------------
# Quick-Action Chips (shared across Desktop & Android)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class QuickChip:
    label: str
    command: str
    execute_now: bool  # True = run immediately; False = pre-fill input & focus


QUICK_CHIPS: tuple[QuickChip, ...] = (
    QuickChip("📁 List", "list", True),
    QuickChip("➕ Folder", "create folder ", False),
    QuickChip("📝 File", "create file ", False),
    QuickChip("✨ Organize", "organize", True),
    QuickChip("🔍 Find", "find ", False),
    QuickChip("↩ Undo", "undo", True),
    QuickChip("❓ Help", "help", True),
)

# --------------------------------------------------------------------------
# Smart File Icons & Formatting
# --------------------------------------------------------------------------

_EXT_ICONS: dict[str, str] = {
    "pdf": "📕",
    "txt": "📝", "md": "📝", "rtf": "📝", "doc": "📝", "docx": "📝", "odt": "📝",
    "csv": "📊", "xls": "📊", "xlsx": "📊", "json": "📊", "xml": "📊", "yaml": "📊", "yml": "📊",
    "png": "🖼", "jpg": "🖼", "jpeg": "🖼", "gif": "🖼", "webp": "🖼", "svg": "🖼", "bmp": "🖼", "ico": "🖼",
    "mp3": "🎵", "wav": "🎵", "ogg": "🎵", "flac": "🎵", "m4a": "🎵", "aac": "🎵", "opus": "🎵",
    "mp4": "🎬", "mkv": "🎬", "avi": "🎬", "mov": "🎬", "webm": "🎬",
    "zip": "📦", "rar": "📦", "7z": "📦", "tar": "📦", "gz": "📦",
    "py": "🐍", "js": "💻", "ts": "💻", "html": "💻", "css": "💻", "sh": "💻", "bat": "💻",
}


def file_icon(path: Path, is_dir: Optional[bool] = None) -> str:
    """Return an intuitive icon for a folder or file based on its extension."""
    d = path.is_dir() if is_dir is None else is_dir
    if d:
        return "📁"
    ext = path.suffix.lstrip(".").lower()
    return _EXT_ICONS.get(ext, "📄")


def format_size(num_bytes: int) -> str:
    """Format byte size into compact human-readable form (e.g. '14.2 KB')."""
    n = max(0, int(num_bytes))
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024.0:.1f} KB"
    if n < 1024 * 1024 * 1024:
        return f"{n / (1024.0 * 1024.0):.1f} MB"
    return f"{n / (1024.0 * 1024.0 * 1024.0):.1f} GB"


# --------------------------------------------------------------------------
# Directory Snapshot, Breadcrumbs & Diff Detection
# --------------------------------------------------------------------------


@dataclass
class DirEntry:
    name: str
    path: Path
    rel_path: str
    is_dir: bool
    icon: str
    size_bytes: int
    size_label: str
    mtime: float
    is_changed: bool = False


@dataclass
class DirSnapshot:
    root: Path
    current: Path
    rel_current: str
    breadcrumbs: list[tuple[str, str]]  # [(display_name, cd_target), ...]
    can_go_up: bool
    entries: list[DirEntry] = field(default_factory=list)
    folder_count: int = 0
    file_count: int = 0
    trash_count: int = 0
    changed_names: set[str] = field(default_factory=set)


def build_breadcrumbs(root: Path, current: Path) -> list[tuple[str, str]]:
    """Return clickable breadcrumb pairs: [(label, cd_target_path), ...]."""
    root_r = root.resolve()
    cur_r = current.resolve()
    root_label = root_r.name or str(root_r)
    crumbs: list[tuple[str, str]] = [(f"🏠 {root_label}", "~")]
    try:
        rel_parts = cur_r.relative_to(root_r).parts
    except ValueError:
        return crumbs
    accum: list[str] = []
    for part in rel_parts:
        accum.append(part)
        crumbs.append((part, "/".join(accum)))
    return crumbs


def count_trash(root: Path) -> int:
    """Count items currently inside .thans_trash."""
    t = root / config.TRASH_DIRNAME
    if not t.is_dir():
        return 0
    try:
        return sum(1 for _ in t.iterdir())
    except OSError:
        return 0


def dir_snapshot(
    root: Path,
    current: Path,
    prev: Optional[DirSnapshot] = None,
    filter_query: str = "",
    limit: int = 120,
) -> DirSnapshot:
    """Capture the state of ``current`` and compute diffs against ``prev``."""
    root_r = root.resolve()
    cur_r = current.resolve() if current.exists() else root_r
    rel_cur = rel(cur_r, root_r)
    crumbs = build_breadcrumbs(root_r, cur_r)
    can_up = cur_r != root_r

    prev_map: dict[str, tuple[bool, int]] = {}
    same_dir = prev is not None and prev.current.resolve() == cur_r
    if same_dir and prev is not None:
        for e in prev.entries:
            prev_map[e.name] = (e.is_dir, e.size_bytes)

    raw_entries: list[Path] = []
    if cur_r.is_dir():
        try:
            raw_entries = [
                p for p in cur_r.iterdir()
                if not p.name.startswith(".") and p.name != config.TRASH_DIRNAME
            ]
        except OSError:
            raw_entries = []

    raw_entries.sort(key=lambda p: (not p.is_dir(), p.name.casefold()))

    folder_count = 0
    file_count = 0
    entries: list[DirEntry] = []
    changed_names: set[str] = set()
    q = (filter_query or "").strip().lower()

    for p in raw_entries:
        try:
            is_d = p.is_dir()
            st = p.stat()
            sz = 0 if is_d else int(st.st_size)
            mt = float(st.st_mtime)
        except OSError:
            continue

        if is_d:
            folder_count += 1
            try:
                sub_n = sum(1 for c in p.iterdir() if not c.name.startswith("."))
                sz_lbl = f"{sub_n} item{'s' if sub_n != 1 else ''}" if sub_n else "empty"
            except OSError:
                sz_lbl = "folder"
        else:
            file_count += 1
            sz_lbl = format_size(sz)

        is_chg = False
        if same_dir:
            old = prev_map.get(p.name)
            if old is None or old != (is_d, sz):
                is_chg = True
                changed_names.add(p.name)

        if q and q not in p.name.lower():
            continue

        if len(entries) < limit:
            entries.append(
                DirEntry(
                    name=p.name,
                    path=p,
                    rel_path=rel(p, root_r),
                    is_dir=is_d,
                    icon=file_icon(p, is_d),
                    size_bytes=sz,
                    size_label=sz_lbl,
                    mtime=mt,
                    is_changed=is_chg,
                )
            )

    return DirSnapshot(
        root=root_r,
        current=cur_r,
        rel_current=rel_cur,
        breadcrumbs=crumbs,
        can_go_up=can_up,
        entries=entries,
        folder_count=folder_count,
        file_count=file_count,
        trash_count=count_trash(root_r),
        changed_names=changed_names,
    )


# --------------------------------------------------------------------------
# Real-Time Intent Preview & Smart Autocomplete
# --------------------------------------------------------------------------

_ACTION_META: dict[str, tuple[str, str]] = {
    "list": ("📁", "List directory contents"),
    "mkdir": ("📁+", "Create new folder"),
    "touch": ("📝+", "Create new file"),
    "rename": ("✏️", "Rename item"),
    "move": ("➔", "Move item"),
    "copy": ("📋", "Copy item"),
    "delete": ("♻️", "Move to trash"),
    "search": ("🔍", "Search files"),
    "open": ("↗", "Open item"),
    "organize": ("✨", "Organize folder"),
    "cd": ("🧭", "Navigate folder"),
    "undo": ("↩", "Undo last action"),
    "help": ("❓", "Show command reference"),
}

_PARTIAL_HINTS: list[tuple[tuple[str, ...], str, str, str]] = [
    (("create f", "make f", "new f", "create"), "📁+", "Create folder or file", "create folder <name> [in <dir>]  ·  create file <name> [with <text>]"),
    (("move", "shift", "put"), "➔", "Move item", "move <item> to <folder>"),
    (("rename", "change name"), "✏️", "Rename item", "rename <old_name> to <new_name>"),
    (("copy", "duplicate"), "📋", "Copy item", "copy <item> to <folder>"),
    (("delete", "remove", "trash"), "♻️", "Safe delete (to .thans_trash)", "delete <item>  (or 'delete <item> permanently')"),
    (("find", "search"), "🔍", "Search workspace", "find <name>  ·  search for pdf files  ·  find *.log"),
    (("organize", "org"), "✨", "Auto-organize files", "organize [folder] [by extension | by date]"),
    (("go", "cd", "navigate", "up", "back"), "🧭", "Navigate workspace", "go to <folder>  ·  go back  ·  cd (back to root)"),
    (("open", "show in", "reveal"), "↗", "Open or reveal", "open <item>  ·  show in folder <item>"),
    (("list", "ls", "show", "what", "how many"), "📁", "Inspect folder", "list  ·  what's in <folder>  ·  how many files in <folder>"),
]

_COMMAND_STARTERS: tuple[str, ...] = (
    "create folder ",
    "create file ",
    "move ",
    "rename ",
    "copy ",
    "delete ",
    "find ",
    "search for ",
    "organize ",
    "go to ",
    "go back",
    "open ",
    "show in folder ",
    "what's in ",
    "how many files in ",
    "list",
    "undo",
    "help",
)


@dataclass
class IntentPreview:
    state: str            # "idle" | "matched" | "partial" | "unknown"
    action: str = ""
    icon: str = "✨"
    title: str = ""
    subtitle: str = ""
    suggestions: list[str] = field(default_factory=list)


def _describe_matched(cmd: dict, current: Optional[Path]) -> tuple[str, str, str]:
    action = cmd["action"]
    p = cmd.get("params") or {}
    icon, label = _ACTION_META.get(action, ("✨", action))

    if action == "mkdir":
        target = p.get("path") or ""
        where = f"in '{p['in_dir']}'" if p.get("in_dir") else "in current folder"
        return icon, f"Create folder '{target}'", f"Will create {where}"
    if action == "touch":
        target = p.get("path") or ""
        where = f"in '{p['in_dir']}'" if p.get("in_dir") else "in current folder"
        has_txt = "with text content" if p.get("content") else "empty file"
        return icon, f"Create file '{target}'", f"{has_txt} · {where}"
    if action in ("move", "copy", "rename"):
        src, dest = p.get("src") or "", p.get("dest") or ""
        verb = {"move": "Move", "copy": "Copy", "rename": "Rename"}[action]
        sub = "Ready to execute"
        if current and current.is_dir() and src:
            exists = any(e.name.casefold().startswith(src.casefold()) for e in current.iterdir() if not e.name.startswith("."))
            sub = f"✓ Found match for '{src}'" if exists else f"Searching for '{src}' in workspace"
        return icon, f"{verb} '{src}' → '{dest}'", sub
    if action == "delete":
        target = p.get("path") or ""
        perm = bool(p.get("permanent"))
        icon = "⚠️" if perm else "♻️"
        sub = "Permanent deletion (bypasses trash)" if perm else "Safe: moves to .thans_trash (restorable via 'undo')"
        return icon, f"Delete '{target}'", sub
    if action == "organize":
        target = p.get("path") or "current folder"
        mode = p.get("mode") or "extension"
        return icon, f"Organize '{target}' by {mode}", "Groups loose files into neat subfolders (reversible with 'undo')"
    if action == "search":
        q = p.get("query") or ""
        return icon, f"Search for '{q}'", "Case-insensitive scan across working folder"
    if action == "cd":
        target = p.get("path") or "~"
        dest_lbl = "working root" if target == "~" else ("parent folder" if target == ".." else f"'{target}'")
        return icon, f"Navigate to {dest_lbl}", "Changes active folder context"
    if action == "list":
        target = p.get("path") or "current folder"
        mode_lbl = "Count items in" if p.get("count") else "List contents of"
        return icon, f"{mode_lbl} {target}", "Instant offline directory listing"
    if action == "open":
        target = p.get("path") or ""
        mode_lbl = "Reveal in file manager" if p.get("reveal") else "Open"
        return icon, f"{mode_lbl}: '{target}'", "Launches system handler"
    if action == "undo":
        return icon, "Undo last action", "Reverses your most recent file or folder change"
    if action == "help":
        return icon, "Show command guide", "Lists all voice & text commands"
    return icon, label, "Press Enter to run"


def preview_intent(text: str, current: Optional[Path] = None) -> IntentPreview:
    """Compute a live, zero-latency preview of what THANS will do for ``text``."""
    raw = (text or "").strip()
    if not raw:
        return IntentPreview(
            state="idle",
            icon="✨",
            title="Ready for voice or text command",
            subtitle="Type naturally or tap a quick chip below · Press Tab to autocomplete",
        )

    cmd = parse_rules(raw)
    if cmd is not None:
        icon, title, subtitle = _describe_matched(cmd, current)
        return IntentPreview(
            state="matched",
            action=cmd["action"],
            icon=icon,
            title=title,
            subtitle=subtitle,
        )

    norm = normalize(raw)
    for prefixes, icon, title, template in _PARTIAL_HINTS:
        if any(norm.startswith(px) or px.startswith(norm) for px in prefixes):
            return IntentPreview(
                state="partial",
                icon=icon,
                title=title,
                subtitle=f"Syntax: {template}",
            )

    return IntentPreview(
        state="unknown",
        icon="💡",
        title="Keep typing a command…",
        subtitle="Try: 'create folder work', 'move a.txt to work', 'organize', 'find pdf', 'undo'",
    )


def autocomplete(text: str, current: Optional[Path] = None) -> str:
    """Complete a partial command starter or a filename in ``current``."""
    raw = text or ""
    stripped = raw.strip()
    if not stripped:
        return "list"

    low = stripped.lower()
    # 1) Complete command starter if still typing the verb
    for starter in _COMMAND_STARTERS:
        if starter.startswith(low) and starter.strip() != low:
            return starter

    # 2) Complete trailing token against files/folders in current directory
    if current is not None and current.is_dir():
        parts = raw.rsplit(" ", 1)
        prefix, tail = (parts[0] + " ", parts[1]) if len(parts) == 2 else ("", parts[0])
        tail_low = tail.strip().lower()
        if tail_low:
            try:
                candidates = sorted(
                    (
                        p.name
                        for p in current.iterdir()
                        if not p.name.startswith(".") and p.name != config.TRASH_DIRNAME
                    ),
                    key=lambda s: s.casefold(),
                )
                for name in candidates:
                    if name.lower().startswith(tail_low) and name.lower() != tail_low:
                        return prefix + name
            except OSError:
                pass

    return raw

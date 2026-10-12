"""Shared UX, animation math, workspace inspector & smart input helpers.

Used by BOTH the desktop (tkinter) app and the Android (Kivy) app so that
visual polish, live command previews, breadcrumbs, file icons, and quick
actions stay 100 % consistent across platforms and remain testable headlessly.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from . import config
from .actions.common import rel, trash_dir
from .parser_rules import parse as parse_rules

# --------------------------------------------------------------------------
# Color & animation math (pure Python, zero GUI deps)
# --------------------------------------------------------------------------


def clamp(val: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(val)))


def lerp(a: float, b: float, t: float) -> float:
    t = clamp(t, 0.0, 1.0)
    return a + (b - a) * t


def ease_out_cubic(t: float) -> float:
    t = clamp(t, 0.0, 1.0)
    return 1.0 - (1.0 - t) ** 3


def ease_in_out_sine(t: float) -> float:
    t = clamp(t, 0.0, 1.0)
    return -(math.cos(math.pi * t) - 1.0) / 2.0


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = (hex_color or "#000000").lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) != 6:
        return (0, 0, 0)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = (max(0, min(255, int(v))) for v in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def lerp_color(c1: str, c2: str, t: float) -> str:
    """Smoothly blend two '#rrggbb' colors at factor t in [0..1]."""
    r1, g1, b1 = hex_to_rgb(c1)
    r2, g2, b2 = hex_to_rgb(c2)
    return rgb_to_hex((
        int(round(lerp(r1, r2, t))),
        int(round(lerp(g1, g2, t))),
        int(round(lerp(b1, b2, t))),
    ))


def hex_to_kivy_rgba(hex_color: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    r, g, b = hex_to_rgb(hex_color)
    return (round(r / 255.0, 4), round(g / 255.0, 4), round(b / 255.0, 4), clamp(alpha))


def wave_heights(phase: float, count: int = 9, mode: str = "idle") -> list[float]:
    """Compute normalized bar heights in [0.12..1.0] for the animated wave header."""
    bars: list[float] = []
    center = (count - 1) / 2.0
    for i in range(max(1, count)):
        dist = abs(i - center) / max(1.0, center)
        envelope = 1.0 - 0.48 * (dist ** 1.4)
        if mode == "listening":
            raw = (
                0.55
                + 0.30 * math.sin(phase * 3.8 + i * 0.85)
                + 0.15 * math.cos(phase * 6.1 - i * 1.3)
            )
            h = clamp(raw * envelope, 0.18, 1.0)
        elif mode == "busy":
            sweep = math.sin(phase * 4.5 - i * 0.65)
            h = clamp((0.48 + 0.42 * sweep) * envelope, 0.16, 0.95)
        elif mode in ("success", "error"):
            pulse = 0.55 + 0.35 * math.sin(phase * 3.0 + i * 0.45)
            h = clamp(pulse * envelope, 0.20, 0.92)
        else:  # idle gentle breathing
            breath = 0.22 + 0.08 * math.sin(phase * 1.4 + i * 0.55)
            h = clamp(breath * envelope, 0.12, 0.36)
        bars.append(round(h, 4))
    return bars


# --------------------------------------------------------------------------
# Minimalist themes (Desktop & Android)
# --------------------------------------------------------------------------

THEMES: dict[str, dict[str, str]] = {
    "obsidian": {
        "name": "Obsidian",
        "bg": "#0d0f14",
        "panel": "#141821",
        "panel2": "#1c2230",
        "panel3": "#252d3f",
        "border": "#262f42",
        "fg": "#eef1f7",
        "dim": "#8b95a8",
        "muted": "#5a6478",
        "accent": "#5b8cff",
        "accent_hover": "#749eff",
        "accent_soft": "#192542",
        "ok": "#3dd68c",
        "warn": "#f5a623",
        "err": "#ff5c6c",
        "user": "#7eb0ff",
        "asst": "#d5deff",
    },
    "midnight": {
        "name": "Midnight",
        "bg": "#09101d",
        "panel": "#101a2e",
        "panel2": "#172540",
        "panel3": "#203254",
        "border": "#24385e",
        "fg": "#edf4ff",
        "dim": "#8ba3c7",
        "muted": "#566e91",
        "accent": "#38bdf8",
        "accent_hover": "#67cef9",
        "accent_soft": "#122b47",
        "ok": "#34d399",
        "warn": "#fbbf24",
        "err": "#fb7185",
        "user": "#7dd3fc",
        "asst": "#dbeafe",
    },
    "daylight": {
        "name": "Daylight",
        "bg": "#f4f6fb",
        "panel": "#ffffff",
        "panel2": "#eaeff7",
        "panel3": "#dce4f2",
        "border": "#d5deec",
        "fg": "#161d2a",
        "dim": "#5b677d",
        "muted": "#8793a8",
        "accent": "#2563eb",
        "accent_hover": "#1d4ed8",
        "accent_soft": "#dbeafe",
        "ok": "#059669",
        "warn": "#d97706",
        "err": "#e11d48",
        "user": "#1d4ed8",
        "asst": "#1e293b",
    },
}

THEME_ORDER = ["obsidian", "midnight", "daylight"]


def get_theme(name: str | None = None) -> dict[str, str]:
    key = (name or "obsidian").lower()
    return dict(THEMES.get(key) or THEMES["obsidian"])


# --------------------------------------------------------------------------
# File icons, sizes & workspace snapshot
# --------------------------------------------------------------------------

_ICON_BY_EXT = {
    "pdf": "📕", "txt": "📄", "md": "📝", "rtf": "📄", "doc": "📘", "docx": "📘",
    "xls": "📊", "xlsx": "📊", "csv": "📊", "ppt": "📙", "pptx": "📙",
    "png": "🖼", "jpg": "🖼", "jpeg": "🖼", "gif": "🖼", "webp": "🖼", "svg": "🖼", "bmp": "🖼",
    "mp3": "🎵", "wav": "🎵", "ogg": "🎵", "flac": "🎵", "m4a": "🎵", "aac": "🎵",
    "mp4": "🎬", "mkv": "🎬", "avi": "🎬", "mov": "🎬", "webm": "🎬",
    "zip": "📦", "rar": "📦", "7z": "📦", "tar": "📦", "gz": "📦",
    "py": "🐍", "js": "💻", "ts": "💻", "json": "⚙", "yml": "⚙", "yaml": "⚙",
    "html": "🌐", "css": "🎨", "sh": "⚡", "bat": "⚡", "log": "📋",
}


def file_icon(p: Path) -> str:
    try:
        if p.is_dir():
            return "📁"
    except OSError:
        pass
    ext = p.suffix.lstrip(".").lower()
    return _ICON_BY_EXT.get(ext, "📄")


def human_size(num_bytes: int) -> str:
    n = max(0, int(num_bytes))
    if n < 1024:
        return f"{n} B"
    for unit in ("KB", "MB", "GB", "TB"):
        n_f = n / 1024.0
        if n_f < 1024.0 or unit == "TB":
            return f"{n_f:.1f} {unit}" if n_f < 10 else f"{int(round(n_f))} {unit}"
        n = int(n_f)
    return f"{n} B"


def breadcrumbs(root: Path, current: Path) -> list[tuple[str, str]]:
    """Return [(display_label, cd_target), ...] from root down to current."""
    root_r = root.resolve()
    cur_r = current.resolve()
    root_name = root_r.name or str(root_r)
    crumbs: list[tuple[str, str]] = [(f"🏠 {root_name}", "~")]
    try:
        rel_parts = cur_r.relative_to(root_r).parts
    except ValueError:
        return crumbs
    acc: list[str] = []
    for part in rel_parts:
        acc.append(part)
        crumbs.append((part, "/".join(acc)))
    return crumbs


def describe_undo_record(rec: dict | None, root: Path) -> str:
    if not rec:
        return ""
    a = rec.get("action", "")
    if a == "mkdir":
        return f"Undo create folder '{rel(Path(rec['created']), root)}'"
    if a == "touch":
        return f"Undo create file '{rel(Path(rec['created']), root)}'"
    if a in ("rename", "move", "copy"):
        return f"Undo {a} '{Path(rec['dest']).name}'"
    if a == "delete":
        orig = Path(rec.get("original") or rec.get("path", ""))
        return f"Restore '{orig.name}'"
    if a == "organize":
        n = len(rec.get("moves") or [])
        return f"Undo organize ({n} files)"
    return f"Undo {a}"


def workspace_snapshot(
    root: Path,
    current: Path,
    undo_stack: list[dict] | None = None,
    limit: int = 80,
) -> dict[str, Any]:
    """Inspect current folder & workspace state for sidebar / chips rendering."""
    root_r = root.resolve()
    cur_r = current.resolve() if current.exists() else root_r
    stack = undo_stack or []

    items: list[dict[str, Any]] = []
    folders = 0
    files = 0
    if cur_r.is_dir():
        try:
            raw_entries = [
                e for e in cur_r.iterdir()
                if not e.name.startswith(".") and e.name != config.TRASH_DIRNAME
            ]
        except OSError:
            raw_entries = []
        raw_entries.sort(key=lambda p: (not p.is_dir(), p.name.casefold()))
        for e in raw_entries:
            is_d = e.is_dir()
            if is_d:
                folders += 1
            else:
                files += 1
            if len(items) < limit:
                size_s = ""
                if not is_d:
                    try:
                        size_s = human_size(e.stat().st_size)
                    except OSError:
                        size_s = ""
                else:
                    try:
                        sub_n = sum(
                            1 for c in e.iterdir()
                            if not c.name.startswith(".") and c.name != config.TRASH_DIRNAME
                        )
                        size_s = f"{sub_n} item{'s' if sub_n != 1 else ''}"
                    except OSError:
                        size_s = "folder"
                items.append({
                    "name": e.name,
                    "rel": rel(e, root_r),
                    "is_dir": is_d,
                    "icon": file_icon(e),
                    "size": size_s,
                    "primary_cmd": f"go to {e.name}" if is_d else f"read {e.name}",
                })

    t_dir = trash_dir(root_r)
    try:
        trash_count = len(list(t_dir.iterdir())) if t_dir.is_dir() else 0
    except OSError:
        trash_count = 0

    return {
        "root_name": root_r.name or str(root_r),
        "rel_path": rel(cur_r, root_r),
        "can_go_up": cur_r != root_r,
        "breadcrumbs": breadcrumbs(root_r, cur_r),
        "folders": folders,
        "files": files,
        "trash_count": trash_count,
        "undo_count": len(stack),
        "undo_label": describe_undo_record(stack[-1] if stack else None, root_r),
        "items": items,
    }


# --------------------------------------------------------------------------
# Live Intent Preview, Autocomplete & Quick Actions
# --------------------------------------------------------------------------

COMMAND_CATALOG: list[dict[str, str]] = [
    {"label": "📋 List files", "cmd": "list", "fill": "list", "desc": "Show folders and files in the current folder"},
    {"label": "📁 + New folder", "cmd": "", "fill": "create folder ", "desc": "Create a new folder (e.g. create folder work)"},
    {"label": "📄 + New file", "cmd": "", "fill": "create file ", "desc": "Create a file with optional text (e.g. create file todo.txt with buy milk)"},
    {"label": "👁 Preview file", "cmd": "", "fill": "read ", "desc": "Read / preview a text file right inside the chat"},
    {"label": "✏ Rename item", "cmd": "", "fill": "rename ", "desc": "Rename a file or folder (e.g. rename old.txt to new.txt)"},
    {"label": "📦 Move item", "cmd": "", "fill": "move ", "desc": "Move an item into a folder (e.g. move report.pdf to work)"},
    {"label": "📑 Copy item", "cmd": "", "fill": "copy ", "desc": "Duplicate a file or folder (e.g. copy notes.txt to backup)"},
    {"label": "✨ Organize by type", "cmd": "organize", "fill": "organize", "desc": "Group loose files into folders by file extension"},
    {"label": "📅 Organize by date", "cmd": "organize files by date", "fill": "organize files by date", "desc": "Group loose files into YYYY-MM folders by modified date"},
    {"label": "🔍 Search files", "cmd": "", "fill": "find ", "desc": "Find files by name or extension (e.g. find invoice, search for pdf files)"},
    {"label": "🗑 Delete to trash", "cmd": "", "fill": "delete ", "desc": "Safely move an item to .thans_trash (restorable via undo)"},
    {"label": "♻ View trash", "cmd": "show trash", "fill": "show trash", "desc": "See items currently in .thans_trash"},
    {"label": "🧹 Empty trash", "cmd": "empty trash", "fill": "empty trash", "desc": "Permanently clear all items in .thans_trash"},
    {"label": "📊 Workspace status", "cmd": "status", "fill": "status", "desc": "Show current path, item counts, trash & undo stack"},
    {"label": "⬆ Go up a folder", "cmd": "go back", "fill": "go back", "desc": "Navigate to the parent folder"},
    {"label": "🏠 Go to root", "cmd": "cd", "fill": "cd", "desc": "Return to the top of the working root"},
    {"label": "↶ Undo last action", "cmd": "undo", "fill": "undo", "desc": "Reverse the most recent file/folder action"},
    {"label": "❓ Help & reference", "cmd": "help", "fill": "help", "desc": "Display the full command reference"},
]

_SYNTAX_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("create folder", "make folder", "new folder", "mkdir"), "create folder <name> [in <folder>]"),
    (("create file", "make file", "new file", "touch"), "create file <name> [with <text>] [in <folder>]"),
    (("create", "make", "new"), "create folder <name>  ·  create file <name> with <text>"),
    (("rename", "change name"), "rename <old-name> to <new-name>"),
    (("move", "shift", "put"), "move <item> to <destination-folder>"),
    (("copy", "duplicate"), "copy <item> to <destination-folder>"),
    (("delete", "remove", "trash"), "delete <item>  (goes to trash; add 'permanently' to skip trash)"),
    (("find", "search"), "find <name>  ·  search for <ext> files  ·  find *.log"),
    (("organize",), "organize [folder] [by extension | by date]"),
    (("read", "preview", "cat", "view"), "read <filename>  (previews file text in chat)"),
    (("open", "reveal", "show in"), "open <item>  ·  show in folder <item>"),
    (("go", "cd", "navigate"), "go to <folder>  ·  go back  ·  cd (back to root)"),
]


def _human_action_summary(cmd: dict) -> str:
    a = cmd.get("action", "")
    p = cmd.get("params") or {}
    if a == "list":
        target = p.get("path") or "current folder"
        return f"Count items in '{target}'" if p.get("count") else f"List contents of {target}"
    if a == "mkdir":
        where = f" inside '{p['in_dir']}'" if p.get("in_dir") else ""
        return f"Create folder '{p.get('path')}'{where}"
    if a == "touch":
        where = f" in '{p['in_dir']}'" if p.get("in_dir") else ""
        with_txt = " with text" if p.get("content") else ""
        return f"Create file '{p.get('path')}'{with_txt}{where}"
    if a == "rename":
        return f"Rename '{p.get('src')}' → '{p.get('dest')}'"
    if a == "move":
        return f"Move '{p.get('src')}' → '{p.get('dest')}'"
    if a == "copy":
        return f"Copy '{p.get('src')}' → '{p.get('dest')}'"
    if a == "delete":
        mode = "permanently" if p.get("permanent") else "to .thans_trash (undoable)"
        return f"Delete '{p.get('path')}' {mode}"
    if a == "search":
        return f"Search workspace for '{p.get('query')}'"
    if a == "organize":
        target = p.get("path") or "current folder"
        mode = p.get("mode") or "extension"
        return f"Organize {target} by {mode}"
    if a == "open":
        return f"Reveal '{p.get('path')}' in folder" if p.get("reveal") else f"Open '{p.get('path')}'"
    if a == "read":
        return f"Preview contents of '{p.get('path')}'"
    if a == "trash":
        return "Empty all items in .thans_trash" if p.get("mode") == "empty" else "Show items in .thans_trash"
    if a == "status":
        return "Show workspace summary & counts"
    if a == "cd":
        path = p.get("path") or "~"
        if path == "~":
            return "Return to working root folder"
        if path == "..":
            return "Navigate up to parent folder"
        return f"Navigate into folder '{path}'"
    if a == "undo":
        return "Undo the most recent action"
    if a == "help":
        return "Show command reference"
    return f"Run {a}"


def live_intent_preview(text: str, current: Path | None = None) -> dict[str, str]:
    """Return a real-time interpretation badge for the user's current input."""
    raw = (text or "").strip()
    if not raw:
        return {
            "state": "idle",
            "badge": "READY",
            "text": "Type or speak a command, or click any quick action pill.",
            "completion": "",
        }

    comp = autocomplete(raw, current) or ""
    cmd = parse_rules(raw)
    if cmd is not None:
        return {
            "state": "valid",
            "action": cmd["action"],
            "badge": "✓ READY",
            "text": _human_action_summary(cmd),
            "completion": comp if comp.lower() != raw.lower() else "",
        }

    low = raw.lower()
    for prefixes, hint in _SYNTAX_HINTS:
        if any(low.startswith(pref) or pref.startswith(low) for pref in prefixes):
            return {
                "state": "hint",
                "badge": "💡 SYNTAX",
                "text": hint,
                "completion": comp if comp.lower() != raw.lower() else "",
            }

    return {
        "state": "freeform",
        "badge": "✨ ASSIST",
        "text": "Press Enter to run, or type 'help' to see all commands.",
        "completion": comp if comp.lower() != raw.lower() else "",
    }


_TEMPLATE_COMPLETIONS = [
    "create folder ",
    "create file ",
    "rename ",
    "move ",
    "copy ",
    "delete ",
    "organize ",
    "organize files by date",
    "find ",
    "search for ",
    "read ",
    "open ",
    "go to ",
    "go back",
    "show trash",
    "empty trash",
    "status",
    "undo",
    "help",
]


def autocomplete(text: str, current: Path | None = None) -> str | None:
    """Suggest a completion for ``text`` using command templates and real files in ``current``."""
    if not text or not text.strip():
        return None
    raw = text
    low = raw.lower()

    # 1. If the user is typing the last token and it matches a file/folder in `current`
    if current is not None and current.is_dir():
        try:
            entries = sorted(
                [
                    e.name for e in current.iterdir()
                    if not e.name.startswith(".") and e.name != config.TRASH_DIRNAME
                ],
                key=str.casefold,
            )
        except OSError:
            entries = []

        # Check after common prepositions or action verbs
        for sep in (" to ", " in ", " into ", " ", "/"):
            idx = low.rfind(sep)
            if idx != -1:
                prefix_part = raw[: idx + len(sep)]
                tail = raw[idx + len(sep):]
                if tail:
                    tail_low = tail.lower()
                    for name in entries:
                        if name.lower().startswith(tail_low) and name.lower() != tail_low:
                            return prefix_part + name
                break

    # 2. Match command templates
    for tmpl in _TEMPLATE_COMPLETIONS:
        if tmpl.startswith(low) and tmpl != low:
            return tmpl

    return None


def quick_actions(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    """Return contextual quick-action pills based on current workspace state."""
    pills: list[dict[str, str]] = [
        {"label": "📋 List", "cmd": "list", "kind": "run"},
        {"label": "📁 +Folder", "cmd": "create folder ", "kind": "fill"},
        {"label": "📄 +File", "cmd": "create file ", "kind": "fill"},
    ]
    if snapshot.get("files", 0) > 0:
        pills.append({"label": "✨ Organize", "cmd": "organize", "kind": "run"})
        pills.append({"label": "👁 Preview", "cmd": "read ", "kind": "fill"})
    pills.extend([
        {"label": "🔍 Find", "cmd": "find ", "kind": "fill"},
        {"label": "✏ Rename", "cmd": "rename ", "kind": "fill"},
        {"label": "📦 Move", "cmd": "move ", "kind": "fill"},
    ])
    if snapshot.get("can_go_up"):
        pills.append({"label": "⬆ Up", "cmd": "go back", "kind": "run"})
    if snapshot.get("undo_count", 0) > 0:
        pills.append({"label": "↶ Undo", "cmd": "undo", "kind": "run"})
    if snapshot.get("trash_count", 0) > 0:
        pills.append({"label": f"🗑 Trash ({snapshot['trash_count']})", "cmd": "show trash", "kind": "run"})
    pills.append({"label": "❓ Help", "cmd": "help", "kind": "run"})
    return pills

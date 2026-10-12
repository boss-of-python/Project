"""Offline search: name substring or extension, case-insensitive, capped."""
from __future__ import annotations

import os
import re
from pathlib import Path

from .common import find_item, rel

KNOWN_EXTS = {
    "pdf", "txt", "md", "rtf", "odt", "epub",
    "doc", "docx", "xls", "xlsx", "ppt", "pptx", "csv",
    "json", "xml", "html", "htm", "yml", "yaml", "ini", "cfg", "conf", "env", "log",
    "png", "jpg", "jpeg", "gif", "webp", "svg", "bmp", "tiff", "tif", "ico", "heic",
    "mp3", "wav", "ogg", "flac", "m4a", "aac", "opus",
    "mp4", "mkv", "avi", "mov", "webm",
    "zip", "rar", "7z", "tar", "gz",
    "py", "js", "ts", "java", "c", "cpp", "h", "cs", "go", "rs", "sh", "bat", "ps1",
    "apk", "exe", "iso", "dmg", "pkg", "deb", "rpm",
}


def find(root: Path, current: Path, query: str, limit: int = 40, where: str | None = None):
    """Search under ``current`` (or the ``where`` sub-folder, e.g. "in docs").

    ``query`` forms:
      * ``invoice``       → name substring
      * ``pdf`` / ``pdf files`` / ``.pdf`` / ``*.pdf`` → extension match
    """
    q = (query or "").strip().lower().lstrip("*")
    if not q:
        raise ValueError("Search for what? e.g. 'find invoice' or 'search for pdf files'.")

    ext = None
    if q.startswith("."):
        ext = q[1:]
    else:
        m = re.match(r"^([a-z0-9]{1,8})(?: files?|s?)?$", q)
        if m and m.group(1) in KNOWN_EXTS:
            ext = m.group(1)
        elif q in KNOWN_EXTS:
            ext = q

    base = current
    if where:
        try:
            base = find_item(current, where, root=root)
        except (OSError, ValueError):
            base = current
        if not base.is_dir():
            base = current
    hits: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(base):
        dp = Path(dirpath)
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != ".thans_trash"]
        if len(hits) >= limit:
            break
        for fn in sorted(filenames):
            if fn.startswith("."):
                continue
            if ext is not None:
                if not fn.lower().endswith("." + ext):
                    continue
            elif q not in fn.lower():
                continue
            hits.append(dp / fn)
            if len(hits) >= limit:
                break

    if not hits:
        what = f"with extension .{ext}" if ext else f"matching '{query}'"
        return True, f"Nothing {what} found under '{rel(base, root)}'.", None

    lines = [f"Found {len(hits)} result{'s' if len(hits) != 1 else ''} under '{rel(base, root)}' (showing up to {limit}):"]
    lines += ["📄 " + rel(h, root) for h in hits]
    return True, "\n".join(lines), None

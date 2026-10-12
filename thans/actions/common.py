"""Shared helpers: path safety, name resolution, trash, unique destinations."""
from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

from .. import config


class UnsafePathError(ValueError):
    """A path would escape the working root — blocked."""


class NotFoundError(ValueError):
    """Item/folder not found (message lists neighbours to help the user)."""


class AmbiguousError(ValueError):
    """Multiple items match the given name."""


# --------------------------------------------------------------------------
# safety
# --------------------------------------------------------------------------


def safe_path(root: Path, current: Path, raw: str) -> Path:
    """Resolve ``raw`` (relative to ``current``, ``~``, or absolute) and ensure
    the result stays inside ``root``. Raises UnsafePathError otherwise."""
    raw = (raw or "").strip().strip('"').strip("'").strip()
    if not raw:
        raise ValueError("No name given.")
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = current / p
    p = p.resolve()
    root_r = root.resolve()
    if p != root_r and root_r not in p.parents:
        raise UnsafePathError(f"'{raw}' is outside the working root.")
    return p


def trash_dir(root: Path) -> Path:
    return root / config.TRASH_DIRNAME


def rel(p: Path, root: Path) -> str:
    """Display-friendly path relative to the working root."""
    try:
        r = p.resolve().relative_to(root.resolve()).as_posix()
        return r or "."
    except ValueError:
        return str(p)


# --------------------------------------------------------------------------
# trash (safe delete)
# --------------------------------------------------------------------------


def to_trash(root: Path, p: Path) -> Path:
    t = trash_dir(root)
    t.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = t / f"{stamp}__{p.name}"
    i = 1
    while dest.exists():
        i += 1
        dest = t / f"{stamp}__{p.name}.{i}"
    shutil.move(str(p), str(dest))
    return dest


def restore(root: Path, trashed: Path, original: Path) -> None:
    if not trashed.exists():
        raise NotFoundError("the trashed entry is no longer there.")
    if original.exists():
        raise ValueError(f"'{original.name}' already exists at its old place.")
    original.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(trashed), str(original))


# --------------------------------------------------------------------------
# name resolution (fuzzy, voice-friendly)
# --------------------------------------------------------------------------


def find_item(base: Path, name: str) -> Path:
    """Resolve a human name inside ``base``:
    exact → case-insensitive → unique prefix → unique substring → "name in dir".
    Raises NotFoundError/AmbiguousError with helpful neighbour lists."""
    name = (name or "").strip()
    if not name:
        raise ValueError("No name given.")
    direct = base / name
    if direct.exists():
        return direct
    if not base.is_dir():
        raise NotFoundError(f"folder '{base.name}' does not exist.")
    entries = sorted(base.iterdir(), key=lambda p: p.name.casefold())
    low = name.casefold()
    exact = [e for e in entries if e.name.casefold() == low]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise AmbiguousError(f"there are several '{name}' here — be more specific.")
    prefix = [e for e in entries if e.name.casefold().startswith(low)]
    if len(prefix) == 1:
        return prefix[0]
    if len(low) >= 3:
        sub = [e for e in entries if low in e.name.casefold()]
        if len(sub) == 1:
            return sub[0]
    # shallow miss → unique exact (case-insensitive) match up to 2 levels down
    found: list[Path] = []

    def _walk(d: Path, depth: int) -> None:
        if depth > 2:
            return
        try:
            children = list(d.iterdir())
        except OSError:
            return
        for e in children:
            if e.name.startswith(".") or e.name == config.TRASH_DIRNAME:
                continue
            if e.is_file() and e.name.casefold() == low:
                found.append(e)
            elif e.is_dir():
                _walk(e, depth + 1)

    _walk(base, 1)
    if len(found) == 1:
        return found[0]
    if len(found) > 1:
        raise AmbiguousError(f"there are several '{name}' below here — say which folder.")
    m = re.match(r"^(?P<m>.+?) in (?P<d>.+)$", name)
    if m:
        try:
            d = find_dir(base, m.group("d"))
            cand = d / m.group("m").strip()
            if cand.exists():
                return cand
        except NotFoundError:
            pass
    sample = ", ".join(e.name for e in entries[:10])
    more = f" (and {len(entries) - 10} more)" if len(entries) > 10 else ""
    raise NotFoundError(f"'{name}' not found in '{base.name}'. Nearby: {sample or '(empty)'}{more}")


def find_dir(base: Path, name: str) -> Path:
    """Resolve a directory by name (exact → case-insensitive → unique prefix)."""
    name = (name or "").strip()
    if not name or name in ("~", "."):
        return base
    direct = base / name
    if direct.is_dir():
        return direct
    low = name.casefold()
    exact = [e for e in base.iterdir() if e.is_dir() and e.name.casefold() == low]
    if len(exact) == 1:
        return exact[0]
    prefix = [e for e in base.iterdir() if e.is_dir() and e.name.casefold().startswith(low)]
    if len(prefix) == 1:
        return prefix[0]
    m = re.match(r"^(?P<m>.+?) in (?P<d>.+)$", name)
    if m:
        try:
            d = find_dir(base, m.group("d"))
            cand = d / m.group("m").strip()
            if cand.is_dir():
                return cand
        except NotFoundError:
            pass
    raise NotFoundError(f"folder '{name}' not found in '{base.name}'.")


def unique_dest(parent: Path, name: str) -> Path:
    """``parent/name`` or ``name (1)``, ``name (2)``… until free."""
    d = parent / name
    if not d.exists():
        return d
    i = 1
    while d.exists():
        i += 1
        d = parent / f"{name} ({i})"
    return d

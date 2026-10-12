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


def _looks_outside(name: str) -> bool:
    """True if ``name`` is absolute, drive-qualified, or contains ``..``.

    Path.is_absolute() is False on Windows for POSIX-style ``/etc/passwd``,
    so we also treat a leading slash/backslash or ``C:`` as an escape.
    """
    raw = Path(name)
    if raw.is_absolute() or ".." in raw.parts:
        return True
    if name[:1] in "/\\":
        return True
    if len(name) >= 2 and name[1] == ":" and name[0].isalpha():
        return True
    return False


def ensure_inside(root: Path, p: Path, *, label: str | None = None) -> Path:
    """Resolve ``p`` and raise UnsafePathError unless it stays inside ``root``.

    Symlinks are followed: a link planted inside the root that points outside
    is treated as an escape and blocked.
    """
    try:
        resolved = p.resolve()
    except OSError as e:
        raise UnsafePathError(f"cannot resolve '{p}': {e}") from e
    root_r = root.resolve()
    if resolved != root_r and root_r not in resolved.parents:
        shown = label if label is not None else str(p)
        raise UnsafePathError(f"'{shown}' is outside the working root.")
    return resolved


def safe_path(root: Path, current: Path, raw: str) -> Path:
    """Resolve ``raw`` (relative to ``current``, ``~``, or absolute) and ensure
    the result stays inside ``root``. Raises UnsafePathError otherwise."""
    raw = (raw or "").strip().strip('"').strip("'").strip()
    if not raw:
        raise ValueError("No name given.")
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = current / p
    return ensure_inside(root, p, label=raw)


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
    p = ensure_inside(root, p)
    t = trash_dir(root)
    t.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = t / f"{stamp}__{p.name}"
    i = 1
    while dest.exists():
        i += 1
        dest = t / f"{stamp}__{p.name}.{i}"
    dest = ensure_inside(root, dest)
    shutil.move(str(p), str(dest))
    return dest


def restore(root: Path, trashed: Path, original: Path) -> None:
    trashed = ensure_inside(root, trashed)
    original = ensure_inside(root, original)
    if not trashed.exists():
        raise NotFoundError("the trashed entry is no longer there.")
    if original.exists():
        raise ValueError(f"'{original.name}' already exists at its old place.")
    original.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(trashed), str(original))


# --------------------------------------------------------------------------
# name resolution (fuzzy, voice-friendly)
# --------------------------------------------------------------------------


def find_item(base: Path, name: str, root: Path | None = None) -> Path:
    """Resolve a human name inside ``base``:
    exact → case-insensitive → unique prefix → unique substring → "name in dir".
    Raises NotFoundError/AmbiguousError with helpful neighbour lists.

    Every returned path is confined to ``root`` (or ``base`` if ``root`` is
    omitted), so ``../``, absolute paths and outbound symlinks cannot escape.
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("No name given.")
    confine = root if root is not None else base
    if _looks_outside(name):
        return safe_path(confine, base, name)
    direct = base / name
    if direct.exists():
        return ensure_inside(confine, direct, label=name)
    if not base.is_dir():
        raise NotFoundError(f"folder '{base.name}' does not exist.")
    entries = sorted(base.iterdir(), key=lambda p: p.name.casefold())
    low = name.casefold()
    exact = [e for e in entries if e.name.casefold() == low]
    if len(exact) == 1:
        return ensure_inside(confine, exact[0], label=name)
    if len(exact) > 1:
        raise AmbiguousError(f"there are several '{name}' here — be more specific.")
    prefix = [e for e in entries if e.name.casefold().startswith(low)]
    if len(prefix) == 1:
        return ensure_inside(confine, prefix[0], label=name)
    if len(low) >= 3:
        sub = [e for e in entries if low in e.name.casefold()]
        if len(sub) == 1:
            return ensure_inside(confine, sub[0], label=name)
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
        return ensure_inside(confine, found[0], label=name)
    if len(found) > 1:
        raise AmbiguousError(f"there are several '{name}' below here — say which folder.")
    m = re.match(r"^(?P<m>.+?) in (?P<d>.+)$", name)
    if m:
        try:
            d = find_dir(base, m.group("d"), root=root)
            cand = d / m.group("m").strip()
            if cand.exists():
                return ensure_inside(confine, cand, label=name)
        except NotFoundError:
            pass
    sample = ", ".join(e.name for e in entries[:10])
    more = f" (and {len(entries) - 10} more)" if len(entries) > 10 else ""
    raise NotFoundError(f"'{name}' not found in '{base.name}'. Nearby: {sample or '(empty)'}{more}")


def find_dir(base: Path, name: str, root: Path | None = None) -> Path:
    """Resolve a directory by name (exact → case-insensitive → unique prefix)."""
    name = (name or "").strip()
    confine = root if root is not None else base
    if not name or name in ("~", "."):
        return ensure_inside(confine, base, label=name or ".")
    if _looks_outside(name):
        p = safe_path(confine, base, name)
        if not p.is_dir():
            raise NotFoundError(f"folder '{name}' not found in '{base.name}'.")
        return p
    direct = base / name
    if direct.is_dir():
        return ensure_inside(confine, direct, label=name)
    low = name.casefold()
    exact = [e for e in base.iterdir() if e.is_dir() and e.name.casefold() == low]
    if len(exact) == 1:
        return ensure_inside(confine, exact[0], label=name)
    prefix = [e for e in base.iterdir() if e.is_dir() and e.name.casefold().startswith(low)]
    if len(prefix) == 1:
        return ensure_inside(confine, prefix[0], label=name)
    m = re.match(r"^(?P<m>.+?) in (?P<d>.+)$", name)
    if m:
        try:
            d = find_dir(base, m.group("d"), root=root)
            cand = d / m.group("m").strip()
            if cand.is_dir():
                return ensure_inside(confine, cand, label=name)
        except NotFoundError:
            pass
    raise NotFoundError(f"folder '{name}' not found in '{base.name}'.")


def unique_dest(parent: Path, name: str) -> Path:
    """``parent/name`` or ``stem (1).ext``, ``stem (2).ext``… until free."""
    d = parent / name
    if not d.exists():
        return d
    p = Path(name)
    stem, suffix = p.stem, p.suffix
    i = 1
    while True:
        candidate = parent / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            return candidate
        i += 1

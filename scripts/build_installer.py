#!/usr/bin/env python3
"""Build the THANS one-file executable with PyInstaller.

    python scripts/build_installer.py            # build dist/THANS(.exe)
    python scripts/build_installer.py --onedir   # faster cold start (folder dist)

The models are NOT embedded in the exe (keeps it small). On Windows the
Inno Setup script bundles the models/ folder next to the exe; on Linux the
install script copies it alongside the binary.

Native packages imported lazily at runtime (vosk, sounddevice, llama_cpp,
pyttsx3 drivers) are collected explicitly — PyInstaller only bundles modules
it can see statically, and a missed one would silently disable voice/TTS in
the installed app.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# native/optional packages the app imports lazily (inside functions) —
# PyInstaller cannot see them statically, so we must collect them explicitly.
_LAZY_NATIVE_PACKAGES = ("vosk", "sounddevice", "llama_cpp")

# pyttsx3 imports its OS driver at runtime (pyttsx3.init()); the driver
# modules are dynamic imports PyInstaller misses.
_PYTTSX3_DRIVERS = ("sapi5", "espeak", "espeak2", "flite", "nss", "nsss", "dtk")


def build_args(onedir: bool = False, root: Path | None = None) -> list[str]:
    """Assemble the PyInstaller argv (unit-testable without building)."""
    from thans.platforms import native_package_available

    root = Path(root) if root is not None else ROOT
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--windowed",
        "--name", "THANS",
        "--paths", str(root),
        "--hidden-import", "thans.animations",
        "--hidden-import", "thans.ui_helpers",
        "--hidden-import", "thans.cli",
        "--hidden-import", "thans.platforms",
        str(root / "thans" / "__main__.py"),
    ]
    # NOTE: extra flags must go AFTER the "PyInstaller" token — inserting
    # before "-m" makes CPython abort with "unknown option".
    inserts: list[str] = []
    if onedir:
        inserts.append("--onedir")
    icon = root / "installer" / "thans.ico"
    if icon.exists():
        inserts += ["--icon", str(icon)]
    args[args.index("PyInstaller") + 1:args.index("PyInstaller") + 1] = inserts

    for pkg in _LAZY_NATIVE_PACKAGES:
        if native_package_available(pkg):
            args += ["--collect-all", pkg]

    if native_package_available("pyttsx3"):
        for driver in _PYTTSX3_DRIVERS:
            args += ["--hidden-import", f"pyttsx3.drivers.{driver}"]

    return args


def main() -> int:
    onedir = "--onedir" in sys.argv
    args = build_args(onedir=onedir)

    print("Building THANS with PyInstaller…")
    print("$ " + " ".join(args))
    code = subprocess.call(args, cwd=ROOT)
    if code != 0:
        print("PyInstaller failed.")
        return code
    exe = ROOT / "dist" / ("THANS" if sys.platform != "win32" else "THANS.exe")
    if exe.exists():
        size_mb = exe.stat().st_size / 1048576
        print(f"\n✓ Built: {exe}  ({size_mb:.1f} MB)")
        print("  Tip: run `python scripts/download_models.py` first and keep")
        print("  the models/ folder next to the executable (or let the app")
        print("  offer the one-click download on first run).")
    else:
        print("\nBuild finished but dist output not found — check dist/.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

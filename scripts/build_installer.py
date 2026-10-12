#!/usr/bin/env python3
"""Build the THANS one-file executable with PyInstaller.

    python scripts/build_installer.py            # build dist/THANS(.exe)
    python scripts/build_installer.py --onedir   # faster cold start (folder dist)

The models are NOT embedded in the exe (keeps it small). On Windows the
Inno Setup script bundles the models/ folder next to the exe; on Linux the
install script copies it alongside the binary.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    onedir = "--onedir" in sys.argv
    # entry point is thans/__main__.py; the package is found via --paths
    args = [sys.executable, "-m", "PyInstaller",
            "--noconfirm", "--clean", "--windowed",
            "--name", "THANS",
            "--paths", str(ROOT),
            "--hidden-import", "thans.animations",
            "--hidden-import", "thans.ui_helpers",
            "thans/__main__.py"]
    if onedir:
        args.insert(1, "--onedir")
    icon = ROOT / "installer" / "thans.ico"
    if icon.exists():
        args[1:1] = ["--icon", str(icon)]

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

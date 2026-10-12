"""THANS entry point.

    python -m thans               launch the GUI
    python -m thans --models      show installed offline models
    python -m thans --selftest    run the headless test suite
    python -m thans --root DIR    choose the working folder
    python -m thans --text-only   no microphone
    python -m thans --no-tts      mute spoken replies
"""
from __future__ import annotations

import argparse
import sys


def _selftest() -> int:
    import unittest
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    suite = unittest.defaultTestLoader.discover(str(root / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="thans",
                                 description="THANS — fully offline voice & text file assistant")
    ap.add_argument("--root", help="working folder (default: your home)")
    ap.add_argument("--text-only", action="store_true", help="start without microphone UI")
    ap.add_argument("--no-tts", action="store_true", help="mute spoken replies")
    ap.add_argument("--models", action="store_true", help="show installed offline models and exit")
    ap.add_argument("--selftest", action="store_true", help="run the built-in test suite and exit")
    a = ap.parse_args(argv)

    if a.selftest:
        return _selftest()

    from . import config
    cfg = config.load_config()

    if a.models:
        from . import model_manager
        print("\n".join(model_manager.status_lines(cfg)))
        return 0

    if a.root:
        cfg["root"] = a.root
    if a.no_tts:
        cfg["tts"] = False
    config.save_config(cfg)

    try:
        from .app import ThansApp
    except ImportError:
        print("tkinter is required for the THANS UI.")
        print("  Debian/Ubuntu:  sudo apt install python3-tk")
        print("  Fedora:         sudo dnf install python3-tkinter")
        print("  Windows/macOS:  the standard python.org install already includes it.")
        return 1

    app = ThansApp(cfg=cfg, text_only=a.text_only)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

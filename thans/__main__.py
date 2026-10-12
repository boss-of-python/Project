"""THANS entry point.

    python -m thans                          launch the desktop GUI
    python -m thans --run "list downloads"   run one command, headless (repeatable)
    python -m thans --cli                    interactive headless prompt
    python -m thans --models                 show installed offline models
    python -m thans --selftest               run the headless test suite
    python -m thans --version                print the version

Common options:
    --root DIR      working folder (never saved by the headless modes)
    --json          one JSON object per command (machine-readable output)
    --quiet         no output, only the exit code
    --llm/--no-llm  force the optional offline LLM parser on/off for this run
    --text-only     start the GUI without microphone UI
    --no-tts        mute spoken replies in the GUI
"""
from __future__ import annotations

import argparse

from . import APP_NAME, __version__


def _selftest() -> int:
    import os
    import unittest
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    suite = unittest.defaultTestLoader.discover(str(root / "tests"))
    # Guard: tests/test_cli.py spawns `--selftest` in a subprocess, which would
    # recurse forever. The marker makes that nested run skip the spawner tests.
    os.environ["THANS_SELFTEST"] = "1"
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="thans",
        description=f"{APP_NAME} — fully offline voice & text file assistant",
        epilog="examples:\n"
               "  thans --run \"organize downloads by date\"\n"
               "  thans --run \"create folder reports\" --run \"list\" --root ~/work\n"
               "  thans --run \"find invoice\" --json\n"
               "  thans --cli --root ~/work\n",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", help="working folder (default: the one saved in the config)")
    ap.add_argument("--cli", action="store_true",
                    help="interactive headless prompt (no tkinter)")
    ap.add_argument("--run", "-c", action="append", default=None, metavar="COMMAND",
                    dest="commands",
                    help="run a command headlessly and exit (repeatable; keeps running after a failure)")
    ap.add_argument("--json", action="store_true",
                    help="print one JSON object per command instead of prose")
    ap.add_argument("--quiet", action="store_true",
                    help="print nothing; the exit code is the result")
    ap.add_argument("--llm", dest="llm", action="store_true", default=None,
                    help="force the optional offline LLM parser on for this run")
    ap.add_argument("--no-llm", dest="llm", action="store_false",
                    help="force the LLM parser off for this run")
    ap.add_argument("--text-only", action="store_true", help="start the GUI without microphone UI")
    ap.add_argument("--no-tts", action="store_true", help="mute spoken replies in the GUI")
    ap.add_argument("--models", action="store_true", help="show installed offline models and exit")
    ap.add_argument("--selftest", action="store_true", help="run the built-in test suite and exit")
    ap.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    return ap


def main(argv: list[str] | None = None) -> int:
    from . import use_utf8_output
    use_utf8_output()                         # legacy consoles (Windows cp1252)
    a = _parser().parse_args(argv)

    if a.selftest:
        return _selftest()

    from . import config
    cfg = config.load_config()

    if a.models:
        from . import model_manager
        print("\n".join(model_manager.status_lines(cfg)))
        return 0

    # ---------------------------------------------------------- headless
    if a.commands or a.cli:
        from . import cli
        engine = cli.make_engine(root=a.root, cfg=cfg, use_llm=a.llm)
        try:
            code = 0
            if a.commands:
                code = cli.run_lines(engine, a.commands, as_json=a.json, quiet=a.quiet)
            if a.cli:
                code = cli.repl(engine, as_json=a.json, quiet=a.quiet) or code
            return code
        except BrokenPipeError:
            # the consumer (e.g. `| head -1`) closed the pipe — exit quietly
            cli.silence_broken_pipe()
            return 0

    # --------------------------------------------------------------- gui
    if a.root:
        cfg["root"] = a.root
    if a.no_tts:
        cfg["tts"] = False
    try:
        config.save_config(cfg)
    except OSError as e:
        print(f"{APP_NAME}: warning: could not save settings ({e}); "
              "they will not persist this run.")

    try:
        from .app import ThansApp
    except ImportError:
        print("tkinter is required for the THANS UI.")
        print("  Debian/Ubuntu:  sudo apt install python3-tk")
        print("  Fedora:         sudo dnf install python3-tkinter")
        print("  Windows/macOS:  the standard python.org install already includes it.")
        print("  Headless machine? Use:  thans --cli   or   thans --run \"<command>\"")
        return 1

    try:
        app = ThansApp(cfg=cfg, text_only=a.text_only)
        app.run()
    except Exception as e:  # noqa: BLE001 — e.g. TclError "no display name"
        if type(e).__name__ in ("TclError", "TclInitError") or "display" in str(e).lower():
            print(f"{APP_NAME} could not open a display: {e}")
            print("No graphical session available — run headless instead:")
            print("  thans --cli                 interactive prompt")
            print('  thans --run "list"          one-shot command')
            return 1
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Headless THANS — the same engine, no GUI.

Designed for scripts, cron jobs and terminals:

    python -m thans --run "organize downloads by date"
    python -m thans --run "create folder reports" --run "list"
    python -m thans --run "find invoice" --json
    python -m thans --cli                # interactive prompt, no tkinter

Output contract (safe to depend on):
  * one line per command on **stdout** for successes,
  * failures go to **stderr** prefixed with ``THANS: ``,
  * ``--json`` switches both streams to one JSON object per line,
  * exit code ``0`` = every command succeeded, ``1`` = at least one failed,
  * ``--quiet`` prints nothing (only the exit code matters).

Nothing here imports tkinter, so it runs on headless servers and in CI.
Commands are matched by ``parser_rules`` first; the optional offline LLM is
only used when ``--llm`` is passed and a GGUF model is installed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable, TextIO

from . import APP_NAME, __version__, config, use_utf8_output  # noqa: F401  (re-export)
from .engine import HELP_TEXT, Engine

PROMPT = "thans:{}> "
BANNER = (
    f"{APP_NAME} {__version__} — offline file assistant (headless mode)\n"
    "Type 'help' for the command list, 'exit' (or Ctrl-D) to quit."
)


def make_engine(root: str | Path | None = None,
                cfg: dict | None = None,
                use_llm: bool | None = None,
                permanent_delete: bool | None = None) -> Engine:
    """Build an :class:`Engine` without touching the stored config file."""
    cfg = dict(cfg if cfg is not None else config.load_config())
    if root:
        cfg["root"] = str(root)
    if use_llm is not None:
        cfg["use_llm"] = bool(use_llm)
    if permanent_delete is not None:
        cfg["permanent_delete"] = bool(permanent_delete)
    try:
        return Engine(cfg.get("root") or config.resolve_root(Path.home()), cfg)
    except OSError as e:                       # unreadable / missing root
        raise SystemExit(f"{APP_NAME}: working folder problem: {e}")


def _payload(result) -> dict:
    return {
        "ok": bool(result.ok),
        "command": result.command,
        "source": result.source,
        "message": result.message,
    }


def emit(result, as_json: bool = False, quiet: bool = False,
         out: TextIO | None = None, err: TextIO | None = None) -> bool:
    """Print one result; returns ``result.ok``."""
    out = out if out is not None else sys.stdout
    err = err if err is not None else sys.stderr
    if quiet and not as_json:
        return bool(result.ok)
    if as_json:
        stream = out if result.ok else err
        stream.write(json.dumps(_payload(result), ensure_ascii=False) + "\n")
        stream.flush()
        return bool(result.ok)
    if result.ok:
        out.write(result.message.rstrip("\n") + "\n")
        out.flush()
    else:
        err.write(f"{APP_NAME}: {result.message}".rstrip("\n") + "\n")
        err.flush()
    return bool(result.ok)


def run_lines(engine: Engine, commands: Iterable[str], as_json: bool = False,
              quiet: bool = False, out: TextIO | None = None,
              err: TextIO | None = None) -> int:
    """Run commands in order; return the process exit code (0 = all ok)."""
    code = 0
    for text in commands:
        text = (text or "").strip()
        if not text:
            continue
        if not emit(engine.run(text), as_json, quiet, out, err):
            code = 1
    return code


def repl(engine: Engine, as_json: bool = False, quiet: bool = False,
         out: TextIO | None = None, err: TextIO | None = None) -> int:
    """Interactive headless prompt until EOF / ``exit``. Returns an exit code."""
    out = out if out is not None else sys.stdout
    err = err if err is not None else sys.stderr
    if not quiet:
        print(BANNER, file=out)
        print(f"Working folder: {engine.root}", file=out)

    while True:
        where = engine.current
        try:
            label = where.relative_to(engine.root).as_posix() or "."
        except ValueError:                     # current dir moved out of root
            label = str(where)
        prompt = PROMPT.format(label)
        interactive = sys.stdin.isatty()
        try:
            if interactive:                    # keeps readline editing/history
                line = input(prompt)
            else:                              # piped input: prompt goes to our stream
                out.write(prompt)
                out.flush()
                line = sys.stdin.readline()
                if line == "":                 # EOF
                    print("", file=out)
                    return 0
        except EOFError:
            print("", file=out)
            return 0
        except KeyboardInterrupt:              # Ctrl-C clears the line
            print("", file=out)
            continue
        text = line.strip()
        if not text:
            continue
        if text.lower() in ("exit", "quit", ":q", ":quit"):
            return 0
        if text.lower() in ("help", "?"):
            print(HELP_TEXT, file=out)
            continue
        emit(engine.run(text), as_json, quiet, out, err)

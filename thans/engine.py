"""Command engine: parse → resolve → execute → human-readable report.

Fallback chain (step 47): rule parser → optional offline LLM parser →
polite "I didn't catch that". Every successful action is recorded for
single-level ``undo``.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from . import actions, config
from .parser_rules import ALLOWED_ACTIONS, parse as parse_rules

HELP_TEXT = """I can manage files & folders inside your working folder. Try:
  • list  ·  show files  ·  what's in <folder>  ·  how many files in <folder>
  • create folder <name> [in <folder>]
  • create file <name> [with <text>] [in <folder>]
  • read <file>  ·  preview <file>  (view file text right here)
  • rename <old> to <new>
  • move <item> to <folder>     • copy <item> to <folder>
  • delete <item>   → trash (say 'undo' to restore, 'show trash' or 'empty trash')
  • find <name>     • search for <ext> files   • find *.log
  • open <item>     • show in folder <item>
  • organize <folder> [by extension|date]
  • go to <folder>  ·  go back / up  ·  cd  (back to root)  ·  status
  • undo (multi-step)    • help
Everything stays inside the working folder; deletes go to .thans_trash."""


@dataclass
class Result:
    ok: bool
    message: str
    command: str = ""    # interpreted command, e.g. "move 'a.txt' → 'docs/'"
    source: str = ""     # "rules" | "llm" | ""


class Engine:
    def __init__(self, root: str | Path, cfg: dict):
        self.cfg = dict(cfg or {})
        self.root = config.resolve_root(root)
        self.current = self.root
        self.undo_stack: list[dict] = []
        self.llm = None
        if self.cfg.get("use_llm"):
            try:
                from .parser_llm import LLMParser
                lp = LLMParser(self.cfg)
                self.llm = lp if lp.available() else None
            except Exception:
                self.llm = None

    @property
    def last_record(self) -> dict | None:
        return self.undo_stack[-1] if self.undo_stack else None

    @last_record.setter
    def last_record(self, val: dict | None) -> None:
        if val is None:
            self.undo_stack.clear()
        else:
            self.undo_stack.append(val)
            if len(self.undo_stack) > 25:
                self.undo_stack.pop(0)

    # ------------------------------------------------------------- public
    def set_root(self, root: str | Path) -> None:
        self.root = config.resolve_root(root)
        self.current = self.root
        self.undo_stack.clear()

    def items_for_llm(self) -> list[str]:
        try:
            return [p.name for p in sorted(self.current.iterdir(), key=lambda p: p.name.casefold())[:100]]
        except OSError:
            return []

    def run(self, text: str) -> Result:
        text = (text or "").strip()
        if not text:
            return Result(False, "What shall we do? Say 'help' for commands.")

        cmd = parse_rules(text)
        source = "rules"
        if cmd is None and self.llm is not None:
            try:
                cmd = self.llm.parse(text, self.items_for_llm())
            except Exception:
                cmd = None
            if cmd is not None:
                source = "llm"

        if cmd is None:
            return Result(False, "Sorry, I didn't catch that. Say \"help\" for the command list.", source=source)

        action = cmd.get("action")
        if action not in ALLOWED_ACTIONS:
            return Result(False, f"Action '{action}' isn't something I can do. Say \"help\".", source=source)

        desc = self._describe(cmd)
        try:
            ok, message, record = self._execute(cmd)
        except actions.UnsafePathError as e:
            return Result(False, f"Blocked for safety: {e}", desc, source)
        except (actions.NotFoundError, actions.AmbiguousError, ValueError) as e:
            return Result(False, f"Sorry: {e}", desc, source)
        except OSError as e:
            return Result(False, f"File error: {e}", desc, source)

        if ok and record:
            self.last_record = record
        return Result(ok, message, desc, source)

    # ---------------------------------------------------------- dispatch
    def _execute(self, cmd: dict):
        a = cmd["action"]
        p = cmd.get("params") or {}
        if a == "help":
            return True, HELP_TEXT, None
        if a == "undo":
            return self._undo()
        if a == "cd":
            return self._cd(p.get("path") or "~")
        if a == "list":
            return actions.list_dir(self.root, self.current, p.get("path"), count_only=bool(p.get("count")))
        if a == "mkdir":
            return actions.create_folder(self.root, self.current, p["path"], p.get("in_dir"))
        if a == "touch":
            return actions.create_file(self.root, self.current, p["path"], p.get("content"), p.get("in_dir"))
        if a == "rename":
            return actions.rename_item(self.root, self.current, p["src"], p["dest"])
        if a == "move":
            return actions.move_item(self.root, self.current, p["src"], p["dest"])
        if a == "copy":
            return actions.copy_item(self.root, self.current, p["src"], p["dest"])
        if a == "delete":
            permanent = bool(p.get("permanent")) or bool(self.cfg.get("permanent_delete"))
            return actions.delete_item(self.root, self.current, p["path"], permanent=permanent)
        if a == "search":
            return actions.find(self.root, self.current, p.get("query") or "")
        if a == "open":
            return actions.open_item(self.root, self.current, p["path"], reveal=bool(p.get("reveal")))
        if a == "organize":
            return actions.organize(self.root, self.current, p.get("path"), p.get("mode") or "extension")
        if a == "read":
            return actions.read_file_preview(self.root, self.current, p["path"])
        if a == "trash":
            return actions.manage_trash(self.root, p.get("mode") or "list")
        if a == "status":
            return actions.workspace_status(self.root, self.current, len(self.undo_stack))
        return False, f"Unknown action '{a}'.", None

    def _cd(self, name: str) -> tuple:
        if name in ("~", "", "home", "root"):
            d = self.root
        elif name == "..":
            if self.current.resolve() == self.root.resolve():
                return True, f"Already at the root folder ('{actions.rel(self.root, self.root)}').", None
            d = actions.safe_path(self.root, self.current, "..")
        else:
            d = actions.safe_path(self.root, self.current, name)
            if not d.is_dir():
                d = actions.find_dir(self.current, name)
        self.current = d
        return True, f"Now in '{actions.rel(d, self.root) or '.'}'.", None

    # ------------------------------------------------------------- undo
    def _undo(self) -> tuple:
        if not self.undo_stack:
            return False, "Nothing to undo yet.", None
        rec = self.undo_stack.pop()
        a = rec.get("action")
        try:
            if a in ("rename", "move"):
                src, dest = Path(rec["src"]), Path(rec["dest"])
                if dest.exists():
                    shutil.move(str(dest), str(src))
                    return True, f"Undid {a}: '{actions.rel(dest, self.root)}' is back as '{actions.rel(src, self.root)}'.", None
                return False, f"Nothing left to undo for that {a}.", None
            if a == "copy":
                d = Path(rec["dest"])
                if d.exists():
                    if d.is_dir():
                        shutil.rmtree(d)
                    else:
                        d.unlink()
                    return True, f"Undid copy: removed '{actions.rel(d, self.root)}'.", None
                return False, "The copy is already gone — nothing to undo.", None
            if a == "delete":
                original = Path(rec.get("original") or rec.get("path"))
                if rec.get("permanent"):
                    return False, "That item was deleted permanently, so it cannot be restored.", None
                trashed = rec.get("trashed")
                if trashed and Path(trashed).exists():
                    actions.restore(self.root, Path(trashed), original)
                    return True, f"Restored '{actions.rel(original, self.root)}' from trash.", None
                if not original.exists():
                    return False, "The trashed entry is no longer in .thans_trash.", None
                return False, "It seems it was already restored.", None
            if a == "mkdir":
                d = Path(rec["created"])
                if d.is_dir():
                    if any(d.iterdir()):
                        return False, "That folder is not empty — delete its contents first (I won't).", None
                    d.rmdir()
                    return True, f"Undid create: removed empty folder '{actions.rel(d, self.root)}'.", None
                return False, "That folder is already gone — nothing to undo.", None
            if a == "touch":
                f = Path(rec["created"])
                if f.is_file():
                    actions.to_trash(self.root, f)
                    return True, f"Undid create: moved '{actions.rel(f, self.root)}' to trash.", None
                return False, "That file is already gone — nothing to undo.", None
            if a == "organize":
                moves = rec.get("moves") or []
                restored = 0
                for dest_str, src_str in reversed(moves):
                    dest_p, src_p = Path(dest_str), Path(src_str)
                    if dest_p.exists() and not src_p.exists():
                        src_p.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(dest_p), str(src_p))
                        restored += 1
                for d_str in reversed(rec.get("dirs") or []):
                    dp = Path(d_str)
                    if dp.is_dir() and not any(dp.iterdir()):
                        try:
                            dp.rmdir()
                        except OSError:
                            pass
                return True, f"Undid organize: restored {restored} file{'s' if restored != 1 else ''} to original place.", None
            return False, f"I can't undo '{a}' automatically.", None
        except actions.UnsafePathError as e:
            return False, f"Blocked for safety: {e}", None
        except (ValueError, OSError) as e:
            return False, f"Undo failed: {e}", None

    # --------------------------------------------------------- cosmetics
    def _describe(self, cmd: dict) -> str:
        a = cmd["action"]
        p = cmd.get("params") or {}

        def s(k, default=""):
            v = p.get(k)
            return f"'{v}'" if v not in (None, "") else default

        if a == "list":
            return f"list {s('path', '(current folder)')}"
        if a in ("mkdir", "touch"):
            extra = f" in {s('in_dir')}" if p.get("in_dir") else ""
            return f"{a} {s('path')}{extra}"
        if a in ("rename", "move", "copy"):
            return f"{a} {s('src')} → {s('dest')}"
        if a in ("delete", "open", "read"):
            extra = " (permanently)" if p.get("permanent") else ""
            return f"{a} {s('path')}{extra}"
        if a == "search":
            return f"search for {s('query')}"
        if a == "organize":
            target = s("path", "(current folder)")
            mode = f" by {p['mode']}" if p.get("mode") else ""
            return f"organize {target}{mode}"
        if a == "cd":
            return f"go to {s('path', '~')}"
        if a == "trash":
            return f"trash ({p.get('mode', 'list')})"
        if a == "status":
            return "workspace status"
        return a

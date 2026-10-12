"""Rule-based command parser: natural phrase → {"action", "params"}.

This is THANS' fast path: deterministic, zero-dependency, and it works even
before any model is downloaded. The optional offline LLM (parser_llm.py) is
only consulted when the rules do not match, so every command in the README
reference is handled without a model.

Grammar notes:
  * "in <folder>" qualifiers are captured as separate params where supported
    and also fall back to an existence-driven split in the engine.
  * leading kind words are stripped: "delete folder work" → path "work".
  * names keep their internal dots/symbols ("report (1).txt" stays intact).
"""
from __future__ import annotations

import re
from typing import Callable, Optional

ALLOWED_ACTIONS = {
    "list", "mkdir", "touch", "rename", "move", "copy", "delete",
    "search", "open", "organize", "cd", "help", "undo",
}

# --------------------------------------------------------------------------
# normalization
# --------------------------------------------------------------------------


def normalize(text: str) -> str:
    """Lowercase, drop fillers/leader names, trim edge punctuation, squash spaces.

    Interior punctuation (dots, dashes, parentheses) is preserved so file
    names like ``report (1).txt`` survive.
    """
    t = (text or "").strip().lower()
    t = re.sub(r"^(?:hey |ok(ay)? )*(?:thans|assistant|computer|jarvis)[,:\s]+", "", t)
    for _ in range(3):
        t = re.sub(r"^(?:please|pls|can you|could you|would you|will you)\s+", "", t)
    t = t.strip(" \t\r\n!.,;:'\"")
    t = re.sub(r"\s+", " ", t).strip()
    return t


_KIND_LEAD = re.compile(r"^(?:the |a |an |my )?(?:subfolder|subdirectory|folder|directory|dir|file)\s+")
_KIND_TAIL = re.compile(r"\s+(?:subfolder|subdirectory|folder|directory|dir|file)$")


def _name(s: Optional[str]) -> str:
    """Clean a path/name group: quotes, whitespace, leading article/kind words."""
    s = (s or "").strip().strip('"').strip("'").strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"^(?:the |a |an )", "", s)          # leading article
    s = _KIND_LEAD.sub("", s, count=1).strip()       # leading kind word ("folder work" → "work")
    s = _KIND_TAIL.sub("", s).strip()                # trailing kind word ("work folder" → "work")
    return s


# --------------------------------------------------------------------------
# rule builders
# --------------------------------------------------------------------------

_PERM = re.compile(r"\s+\b(?:permanently|for good|forever)\b$")


def _delete_build(m: re.Match) -> dict:
    p = (m["p"] or "").strip()
    perm = bool(_PERM.search(p))
    if perm:
        p = _PERM.sub("", p)
    p = _name(p)
    if not p:
        return None
    return {"action": "delete", "params": {"path": p, "permanent": perm}}


_ORG_MODE = {
    "extension": "extension", "type": "extension",
    "date": "date", "day": "date", "time": "date", "mtime": "date",
}


def _organize_build(m: re.Match) -> dict:
    p = (m["p"] or "").strip()
    mm = re.match(r"^(?:files?|items?) in (.+)$", p)
    if mm:
        p = mm.group(1).strip()
    elif p in ("files", "items", "everything", "the files"):
        p = ""
    p = _name(p)
    return {"action": "organize", "params": {"path": p or None, "mode": _ORG_MODE.get(m["mode"], "extension")}}


def _mkdir_build(m: re.Match) -> Optional[dict]:
    p = _name(m["p"])
    if not p:
        return None
    return {"action": "mkdir", "params": {"path": p, "in_dir": (m["dir"] or "").strip() or None}}


def _touch_build(m: re.Match) -> Optional[dict]:
    p = _name(m["p"])
    if not p:
        return None
    return {"action": "touch", "params": {
        "path": p,
        "in_dir": (m["dir"] or "").strip() or None,
        "content": (m["content"] or "").strip() or None,
    }}


def _list_build(m: re.Match) -> Optional[dict]:
    d = (m["dir"] or "").strip()
    return {"action": "list", "params": {"path": _name(d) or None}}


# --------------------------------------------------------------------------
# rule table (ORDER MATTERS — specific rules first)
# --------------------------------------------------------------------------

RULES: list[tuple[str, re.Pattern, Callable[[re.Match], Optional[dict]]]] = [
    ("help",
     re.compile(r"^(?:help|show help|what can you do|what do you do|list commands|commands|show commands|tell me what you can do)$"),
     lambda m: {"action": "help", "params": {}}),

    ("undo",
     re.compile(r"^undo\b.*$"),
     lambda m: {"action": "undo", "params": {}}),

    ("reveal",
     re.compile(r"^(?:show (?:it |that )?in (?:the )?(?:file )?folder(?: manager)?|show me in folder|reveal) (?P<p>.+)$"),
     lambda m: {"action": "open", "params": {"path": _name(m["p"]), "reveal": True}}),

    ("cd-home",
     re.compile(r"^(?:cd|home|go home|back to (?:root|home|start|top))$"),
     lambda m: {"action": "cd", "params": {"path": "~"}}),

    ("cd",
     re.compile(r"^(?:go to |go into |navigate to |cd to |cd |change (?:the )?working folder to |change folder to |set folder to |switch to folder)(?P<p>.+)$"),
     lambda m: {"action": "cd", "params": {"path": _name(m["p"])}}),

    ("open",
     re.compile(r"^open (?:the )?(?P<p>.+)$"),
     lambda m: {"action": "open", "params": {"path": _name(m["p"]), "reveal": False}}),

    ("mkdir",
     re.compile(r"^(?:create|make|new) (?:a |an |an? new )?(?:empty )?(?:folder|directory|dir) (?:called |named |with the name |with name )?(?P<p>.+?)(?: in (?P<dir>.+?))?$"),
     _mkdir_build),

    ("touch",
     re.compile(r"^(?:create|make|new) (?:a |an |an? new )?file (?:called |named |with the name |with name )?(?P<p>.+?)(?: (?:with|containing|that says|with text|with content|with the text|with the content) (?P<content>(?:(?! in ).)+))?(?: in (?P<dir>.+?))?$"),
     _touch_build),

    ("rename",
     re.compile(r"^(?:rename|change (?:the )?name of) (?P<src>.+?) (?:to |as )(?P<dest>.+)$"),
     lambda m: {"action": "rename", "params": {"src": _name(m["src"]), "dest": _name(m["dest"])}}),

    ("move",
     re.compile(r"^(?:move|shift) (?P<src>.+?) (?:to|into) (?P<dest>.+)$"),
     lambda m: {"action": "move", "params": {"src": _name(m["src"]), "dest": _name(m["dest"])}}),

    ("put",
     re.compile(r"^put (?P<src>.+?) in (?P<dest>.+)$"),
     lambda m: {"action": "move", "params": {"src": _name(m["src"]), "dest": _name(m["dest"])}}),

    ("copy",
     re.compile(r"^(?:copy|duplicate) (?P<src>.+?) to (?P<dest>.+)$"),
     lambda m: {"action": "copy", "params": {"src": _name(m["src"]), "dest": _name(m["dest"])}}),

    ("delete",
     re.compile(r"^(?:delete|remove|trash|get rid of) (?P<p>.+)$"),
     _delete_build),

    ("search",
     re.compile(r"^(?:find|search) (?:for )?(?P<q>.+)$"),
     lambda m: {"action": "search", "params": {"query": (m["q"] or "").strip()}}),

    ("organize",
     re.compile(r"^organize (?:the )?(?P<p>.+?)(?: by (?P<mode>extension|type|date|day|time|mtime))?$"),
     _organize_build),

    ("organize-here",
     re.compile(r"^organize$"),
     lambda m: {"action": "organize", "params": {"path": None, "mode": "extension"}}),

    ("how-many",
     re.compile(r"^how many (?:files?|folders?|items?) (?:are )?in (?P<dir>.+)$"),
     lambda m: {"action": "list", "params": {"path": _name(m["dir"]), "count": True}}),

    ("what-in",
     re.compile(r"^what(?:'s| is) in (?P<dir>.+)$"),
     lambda m: {"action": "list", "params": {"path": _name(m["dir"])}}),

    ("list",
     re.compile(r"^(?:list|ls|show)(?: me)?(?: (?:the |all )?(?:files?|folders?|contents?|everything|items?))?(?: (?:in )?(?P<dir>.+))?$"),
     _list_build),
]


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------


def parse(text: str) -> Optional[dict]:
    """Parse a phrase; return {"action", "params"} or None (→ LLM / 'help')."""
    t = normalize(text)
    if not t:
        return None
    for _rule, pattern, build in RULES:
        m = pattern.match(t)
        if m:
            cmd = build(m)
            if cmd is not None:
                return cmd
    return None

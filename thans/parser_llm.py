"""Optional offline LLM parser: llama.cpp + GGUF from the models/ folder.

Design: the LLM only ever translates free-form speech/text into the same
{"action", "params"} dict the rule parser emits — never into code or file
ops directly. Output is validated against ALLOWED_ACTIONS, so a hallucinated
response degrades to "I didn't catch that" instead of a wrong action.

Default model: Qwen2.5-0.5B-Instruct Q4_K_M (~408 MB) — small enough to load
in <2 s on a laptop CPU, accurate enough for strict JSON extraction.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from . import model_manager
from .parser_rules import ALLOWED_ACTIONS

SYSTEM = """You are the command parser for THANS, an offline file assistant.
Respond with ONE JSON object only. No prose, no markdown fences.
Schema: {"action": <string>, "params": <object>, "confidence": <number>}
Allowed actions and params:
 list{path?} | mkdir{path} | touch{path, content?} | rename{src, dest}
 move{src, dest} | copy{src, dest} | delete{path, permanent?}
 search{query} | open{path} | organize{path?, mode? "extension"|"date"}
 cd{path} | help{} | undo{}
Rules:
 - Relative paths are relative to the current directory.
 - "permanent" is true only when the user explicitly says so.
 - If the request is not a file/folder task, or is too unclear, respond:
   {"action":"help","params":{},"confidence":0}"""


class LLMParser:
    def __init__(self, cfg: dict):
        self.cfg = dict(cfg or {})
        self.model_path = model_manager.llm_model_path(self.cfg)
        self._llm = None

    def available(self) -> bool:
        return self.model_path is not None

    def _ensure(self):
        if self._llm is None:
            from llama_cpp import Llama
            self._llm = Llama(str(self.model_path), n_ctx=512, n_threads=2, verbose=False)
        return self._llm

    def parse(self, text: str, items: list[str]) -> Optional[dict]:
        """Translate free-form text into a validated command dict (or None)."""
        if not self.available():
            return None
        llm = self._ensure()
        ctx = ", ".join(items[:80]) if items else "(empty)"
        user = f"Current directory contents: {ctx}\nUser request: {text}"
        out = llm.create_chat_completion(
            messages=[{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": user}],
            max_tokens=150,
            temperature=0.0,
        )
        content = out["choices"][0]["message"]["content"]
        return self.extract(content)

    @staticmethod
    def extract(content: str) -> Optional[dict]:
        """Pull a validated JSON command out of raw LLM output."""
        s = (content or "").strip()
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
        start, end = s.find("{"), s.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            data = json.loads(s[start:end + 1])
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        action = str(data.get("action", "")).strip().lower()
        if action not in ALLOWED_ACTIONS:
            return None
        params = {}
        raw = data.get("params") or {}
        if isinstance(raw, dict):
            for k, v in raw.items():
                if isinstance(v, str):
                    v = v.strip()
                params[str(k)] = v
        return {"action": action, "params": params}

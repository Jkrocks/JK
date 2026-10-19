"""Settings for Tejas AI.

Everything lives in one folder (default ~/.tejas-ai, override with TEJAS_AI_HOME):
  config.json   settings (editable from the Parent zone)
  tejas.db      profiles, memories and conversation history
  models/       speech models (Whisper, Piper voices)
  library/      books and notes the kids' Tejas can read (txt, md, pdf)
  certs/        the home HTTPS certificate so phones and TVs can use the mic
"""
from __future__ import annotations

import copy
import json
import os
import threading
from pathlib import Path

DEFAULTS: dict = {
    "assistant": {
        "name": "Tejas",
        # Homework: guide the child with hints before revealing the answer.
        "hint_first": True,
        # Extra self-check pass on hard questions (slower, more careful).
        "deep_think_default": False,
    },
    "llm": {
        # "ollama" (recommended) or "openai" for any OpenAI-compatible local
        # server such as llama.cpp's llama-server or LM Studio.
        "backend": "ollama",
        "url": "http://127.0.0.1:11434",
        "model": "qwen2.5:7b",
        "temperature": 0.6,
        "num_ctx": 8192,
        "timeout_s": 300,
    },
    "stt": {
        # faster-whisper size: tiny, base, small, medium, large-v3.
        # "small" is a good balance for kids' voices and Indian accents.
        "model": "small",
        "device": "auto",
        "compute_type": "int8",
    },
    "tts": {
        "enabled": True,
        "voices": {
            "en": "en_GB-northern_english_male-medium",
            "hi": "hi_IN-pratham-medium",
        },
        "speed": 1.0,
    },
    "server": {
        "host": "0.0.0.0",
        "http_port": 8000,
        "https_port": 8443,
        "https": True,
    },
    "parent": {
        # PBKDF2 hash of the parent PIN; None until a parent sets one.
        "pin_hash": None,
        "pin_salt": None,
    },
}


def home() -> Path:
    p = Path(os.environ.get("TEJAS_AI_HOME", Path.home() / ".tejas-ai")).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    for sub in ("models", "library", "certs"):
        (p / sub).mkdir(exist_ok=True)
    return p


def _merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


class Config:
    """Thread-safe settings backed by config.json."""

    def __init__(self, path: Path | None = None):
        self.path = path or home() / "config.json"
        self._lock = threading.Lock()
        data = {}
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text("utf-8"))
            except (json.JSONDecodeError, OSError):
                # A broken file must never stop the assistant from starting.
                self.path.rename(self.path.with_suffix(".broken.json"))
        self.data = _merge(DEFAULTS, data)
        self.save()

    def get(self, dotted: str, default=None):
        node = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def update(self, patch: dict) -> None:
        with self._lock:
            self.data = _merge(self.data, patch)
            self.save()

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2), "utf-8")
        tmp.replace(self.path)

    def public(self) -> dict:
        """Settings safe to show in the app (no PIN hash)."""
        d = copy.deepcopy(self.data)
        d.pop("parent", None)
        d["parent_pin_set"] = bool(self.data["parent"].get("pin_hash"))
        return d

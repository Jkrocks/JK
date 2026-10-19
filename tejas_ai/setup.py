"""One-time setup helpers (used by the installers and the desktop app).

All downloads happen once, while the computer has internet. After that
Tejas never needs the internet again.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import urllib.request
from pathlib import Path
from typing import Callable

from .config import Config, home
from .speech import DEFAULT_VOICES, voice_url

Progress = Callable[[str, float | None], None]  # (message, fraction 0..1 or None)
OLLAMA = "http://127.0.0.1:11434"


def memory_gb() -> int:
    try:
        if sys.platform == "win32":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MS()
            m.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return int(m.ullTotalPhys / 2**30)
        return int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30)
    except Exception:
        return 8


def recommended() -> dict:
    gb = memory_gb()
    if gb >= 24:
        return {"model": "qwen2.5:14b", "whisper": "small", "gb": gb}
    if gb >= 12:
        return {"model": "qwen2.5:7b", "whisper": "small", "gb": gb}
    return {"model": "qwen2.5:3b", "whisper": "base", "gb": gb}


def ollama_installed() -> bool:
    if shutil.which("ollama"):
        return True
    guesses = [Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Ollama/ollama.exe",
               Path("/Applications/Ollama.app"), Path("/usr/local/bin/ollama"), Path("/usr/bin/ollama")]
    return any(p.exists() for p in guesses)


def ollama_running() -> bool:
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def ollama_models() -> list[str]:
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=3) as r:
            return [m["name"] for m in json.load(r).get("models", [])]
    except Exception:
        return []


def start_ollama() -> bool:
    """Start the Ollama service if it's installed but not running."""
    if ollama_running():
        return True
    import subprocess
    import time
    exe = shutil.which("ollama")
    if not exe and sys.platform == "win32":
        p = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Ollama/ollama.exe"
        exe = str(p) if p.exists() else None
    try:
        if sys.platform == "darwin" and not exe:
            subprocess.Popen(["open", "-a", "Ollama"])
        elif exe:
            flags = 0x08000000 if sys.platform == "win32" else 0  # no console window
            subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
        else:
            return False
    except OSError:
        return False
    for _ in range(20):
        time.sleep(0.5)
        if ollama_running():
            return True
    return False


def ollama_download_url() -> str:
    return {"Windows": "https://ollama.com/download/windows", "Darwin": "https://ollama.com/download/mac"}.get(
        platform.system(), "https://ollama.com/download/linux")


def pull_model(name: str, progress: Progress) -> None:
    """Download a model through Ollama's own API, reporting progress."""
    req = urllib.request.Request(f"{OLLAMA}/api/pull", data=json.dumps({"name": name, "stream": True}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60 * 60) as r:
        for line in r:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("error"):
                raise RuntimeError(d["error"])
            total, done = d.get("total"), d.get("completed")
            progress(f"Brain: {d.get('status', '')}", (done / total) if total and done else None)
    progress("Brain ready", 1.0)


def _fetch(url: str, dest: Path, label: str, progress: Progress) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        return
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while chunk := r.read(1 << 20):
            f.write(chunk)
            got += len(chunk)
            progress(label, got / total if total else None)
    tmp.replace(dest)


def whisper_ready(size: str) -> bool:
    return (home() / "models" / "whisper" / size / "model.bin").exists()


def download_whisper(size: str, progress: Progress) -> None:
    from faster_whisper.utils import download_model
    out = home() / "models" / "whisper" / size
    out.mkdir(parents=True, exist_ok=True)
    progress(f"Ears: downloading Whisper {size}…", None)
    download_model(size, output_dir=str(out))
    progress("Ears ready", 1.0)


def voices_ready(names=None) -> bool:
    d = home() / "models" / "piper"
    return all((d / f"{n}.onnx").exists() for n in (names or DEFAULT_VOICES.values()))


def download_voices(names, progress: Progress) -> list[str]:
    d = home() / "models" / "piper"
    d.mkdir(parents=True, exist_ok=True)
    failed = []
    for n in names:
        onnx, js = voice_url(n)
        try:
            _fetch(js, d / f"{n}.onnx.json", f"Voice: {n}", progress)
            _fetch(onnx, d / f"{n}.onnx", f"Voice: {n}", progress)
        except Exception:
            failed.append(n)
            for p in (d / f"{n}.onnx.json", d / f"{n}.onnx"):
                p.unlink(missing_ok=True)
    progress("Voice ready", 1.0)
    return failed


def full_setup(progress: Progress, model: str | None = None, whisper: str | None = None) -> None:
    rec = recommended()
    model, whisper = model or rec["model"], whisper or rec["whisper"]
    cfg = Config()
    cfg.update({"llm": {"model": model}, "stt": {"model": whisper}})
    if not start_ollama():
        raise RuntimeError("Ollama isn't installed or won't start.")
    if not any(m in (model, f"{model}:latest") for m in ollama_models()):
        pull_model(model, progress)
    if not whisper_ready(whisper):
        download_whisper(whisper, progress)
    if not voices_ready():
        download_voices(list(DEFAULT_VOICES.values()), progress)

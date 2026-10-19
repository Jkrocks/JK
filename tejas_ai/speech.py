"""Ears and voice, both offline.

Ears: faster-whisper (OpenAI's Whisper, run locally). Understands English,
Hindi, Punjabi and many more, and copes well with children's voices.

Voice: Piper, a fast neural voice that runs on the CPU. Tejas's default is a
warm, calm, low male voice. Any Piper voice can be chosen in settings.

If either isn't installed, Tejas still works: the screens fall back to their
own built-in speech.
"""
from __future__ import annotations

import io
import os
import tempfile
import threading
import wave
from pathlib import Path

# Curated voices: soft, natural, good for long listening.
VOICES = {
    "en_GB-northern_english_male-medium": "Warm, calm, low male voice (default)",
    "en_US-ryan-high": "Clear, friendly American male",
    "en_US-lessac-high": "Soft, clear American female",
    "en_GB-alba-medium": "Gentle Scottish female",
    "en_US-amy-medium": "Bright, friendly American female",
    "hi_IN-pratham-medium": "Hindi male",
    "hi_IN-priyamvada-medium": "Hindi female",
}
DEFAULT_VOICES = {"en": "en_GB-northern_english_male-medium", "hi": "hi_IN-pratham-medium"}


def voice_url(name: str) -> tuple[str, str]:
    """Hugging Face download URLs for a Piper voice (used by the installer)."""
    lang_region, speaker, quality = name.split("-")
    lang = lang_region.split("_")[0]
    base = f"https://huggingface.co/rhasspy/piper-voices/resolve/main/{lang}/{lang_region}/{speaker}/{quality}/{name}"
    return base + ".onnx", base + ".onnx.json"


class Ears:
    def __init__(self, cfg, models_dir: Path):
        self.cfg, self.models_dir = cfg, models_dir
        self._model = None
        self._lock = threading.Lock()
        self.error: str | None = None

    def available(self) -> bool:
        try:
            import faster_whisper  # noqa: F401
            return True
        except ImportError:
            self.error = "faster-whisper is not installed"
            return False

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            size = self.cfg.get("stt.model", "small")
            local = self.models_dir / "whisper" / size
            device = self.cfg.get("stt.device", "auto")
            self._model = WhisperModel(
                str(local) if local.exists() else size,
                device=device, compute_type=self.cfg.get("stt.compute_type", "int8"),
                download_root=str(self.models_dir / "whisper-cache"),
                local_files_only=local.exists() or os.environ.get("TEJAS_OFFLINE") == "1",
            )
        return self._model

    def transcribe(self, audio: bytes, language: str | None = None) -> dict:
        if not audio or len(audio) < 1000:
            return {"text": "", "language": None}
        with self._lock:
            model = self._load()
            with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as f:
                f.write(audio)
                path = f.name
            try:
                lang = language if language in ("en", "hi", "pa") else None
                segments, info = model.transcribe(
                    path, language=lang, vad_filter=True, beam_size=5,
                    initial_prompt="Tejas, homework, maths, reminder, please, thank you.",
                )
                text = " ".join(s.text.strip() for s in segments).strip()
            finally:
                os.unlink(path)
        # Whisper sometimes "hears" these in silence.
        if text.lower().strip(" .!") in {"thank you", "thanks for watching", "you", "bye"} and len(audio) < 40000:
            text = ""
        return {"text": text, "language": getattr(info, "language", None)}


class Voice:
    def __init__(self, cfg, models_dir: Path):
        self.cfg, self.dir = cfg, models_dir / "piper"
        self._voices: dict = {}
        self._lock = threading.Lock()

    def installed(self) -> list[str]:
        return sorted(p.stem for p in self.dir.glob("*.onnx")) if self.dir.exists() else []

    def available(self) -> bool:
        try:
            import piper  # noqa: F401
        except ImportError:
            return False
        return bool(self.installed()) and bool(self.cfg.get("tts.enabled", True))

    def pick(self, lang: str) -> str | None:
        want = (self.cfg.get("tts.voices") or {}).get(lang) or DEFAULT_VOICES.get(lang)
        have = self.installed()
        if want in have:
            return want
        pref = [v for v in have if v.startswith(lang)]
        return pref[0] if pref else (have[0] if have and lang == "en" else None)

    def _load(self, name: str):
        if name not in self._voices:
            from piper import PiperVoice
            self._voices[name] = PiperVoice.load(str(self.dir / f"{name}.onnx"))
        return self._voices[name]

    def speak(self, text: str, lang: str = "en") -> bytes | None:
        """Return a WAV for the text, or None so the screen uses its own voice."""
        text = " ".join((text or "").split())[:1200]
        name = self.pick(lang)
        if not text or not name or not self.available():
            return None
        with self._lock:
            v = self._load(name)
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wav:
                speed = float(self.cfg.get("tts.speed", 1.0)) or 1.0
                try:  # piper-tts >= 1.3
                    from piper import SynthesisConfig
                    v.synthesize_wav(text, wav, syn_config=SynthesisConfig(length_scale=1.0 / speed))
                except ImportError:  # older piper-tts
                    v.synthesize(text, wav, length_scale=1.0 / speed, sentence_silence=0.25)
            return buf.getvalue()

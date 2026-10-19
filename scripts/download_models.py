"""Download Tejas's offline models once. After this, no internet is needed.

  python scripts/download_models.py                 # ears (Whisper small) + default voices
  python scripts/download_models.py --whisper base  # smaller ears for older PCs
  python scripts/download_models.py --voices all    # every curated voice
"""
from __future__ import annotations

import argparse
import shutil
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tejas_ai.config import home  # noqa: E402
from tejas_ai.speech import DEFAULT_VOICES, VOICES, voice_url  # noqa: E402


def fetch(url: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  ✓ {dest.name} (already here)")
        return
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"  ↓ {dest.name}")
    with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, length=1 << 20)
    tmp.replace(dest)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--whisper", default="small", help="tiny | base | small | medium | large-v3 | none")
    ap.add_argument("--voices", default="default", help="default | all | comma list of voice names | none")
    a = ap.parse_args()
    models = home() / "models"

    if a.whisper != "none":
        print(f"Ears: Whisper '{a.whisper}'")
        try:
            from faster_whisper.utils import download_model
            out = models / "whisper" / a.whisper
            out.mkdir(parents=True, exist_ok=True)
            download_model(a.whisper, output_dir=str(out))
            print(f"  ✓ saved to {out}")
        except ImportError:
            print("  ! faster-whisper isn't installed; skipping ears")

    if a.voices != "none":
        names = (list(VOICES) if a.voices == "all" else list(DEFAULT_VOICES.values()) if a.voices == "default"
                 else [v.strip() for v in a.voices.split(",") if v.strip()])
        print("Voices: " + ", ".join(names))
        d = models / "piper"
        d.mkdir(parents=True, exist_ok=True)
        for n in names:
            onnx, js = voice_url(n)
            try:
                fetch(js, d / f"{n}.onnx.json")
                fetch(onnx, d / f"{n}.onnx")
            except Exception as e:  # a voice may be renamed upstream; keep going
                print(f"  ! couldn't get {n}: {e}")
                for p in (d / f"{n}.onnx.json", d / f"{n}.onnx"):
                    p.unlink(missing_ok=True)
    print("Done. Tejas can now listen and talk without the internet.")


if __name__ == "__main__":
    main()

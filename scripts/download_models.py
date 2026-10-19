"""Download Tejas's offline ears and voice once. After this, no internet is needed.

  python scripts/download_models.py                 # ears (Whisper small) + default voices
  python scripts/download_models.py --whisper base  # smaller ears for older PCs
  python scripts/download_models.py --voices all    # every curated voice
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tejas_ai import setup  # noqa: E402
from tejas_ai.speech import DEFAULT_VOICES, VOICES  # noqa: E402


def show(msg: str, frac) -> None:
    pct = f" {frac * 100:5.1f}%" if frac is not None else ""
    print(f"\r  {msg[:60]:<60}{pct}", end="", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--whisper", default="small", help="tiny | base | small | medium | large-v3 | none")
    ap.add_argument("--voices", default="default", help="default | all | comma list | none")
    a = ap.parse_args()
    if a.whisper != "none":
        try:
            setup.download_whisper(a.whisper, show)
        except ImportError:
            print("  ! faster-whisper isn't installed; skipping ears")
        print()
    if a.voices != "none":
        names = (list(VOICES) if a.voices == "all" else list(DEFAULT_VOICES.values()) if a.voices == "default"
                 else [v.strip() for v in a.voices.split(",") if v.strip()])
        failed = setup.download_voices(names, show)
        print()
        for n in failed:
            print(f"  ! couldn't get voice {n}")
    print("Done. Tejas can now listen and talk without the internet.")


if __name__ == "__main__":
    main()

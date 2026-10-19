#!/usr/bin/env bash
# Upload files to the "Tejas AI V1 2026" release so they have direct download links.
set -euo pipefail
TAG="tejas-ai-v1.0.0"
NOTES="Tejas AI V1 2026 — offline family AI companion.

Downloads (tap on the device):
• Tejas-AI-Android.apk — Android phones, tablets and Android TV
• Tejas-AI-iOS-unsigned.ipa — iPhone/iPad via SideStore or AltStore (add source: altstore-source.json)
• Tejas-AI-Windows.zip / Tejas-AI-macOS.zip / Tejas-AI-Linux.tar.gz — the home computer app (runs Tejas's brain)"
for i in 1 2 3; do
  gh release view "$TAG" >/dev/null 2>&1 && break
  gh release create "$TAG" --target tejas-ai --title "Tejas AI V1 2026" --notes "$NOTES" --latest=false && break || sleep $((i * 7))
done
gh release upload "$TAG" "$@" --clobber

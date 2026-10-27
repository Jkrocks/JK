#!/usr/bin/env bash
# Put an ISO on the public "TEJAS OS 1.0" release (no login needed to download).
# Under 2 GB: one file. Bigger: pieces + a one-click join file (GitHub's per-file limit).
set -euo pipefail
ISO="$1"; TAG="${TAG:-tejas-os-v1.0}"; R="$GITHUB_REPOSITORY"
DIR=$(dirname "$ISO"); NAME=$(basename "$ISO")
SIZE=$(stat -c %s "$ISO")
cd "$DIR"
[ -f "$NAME.sha256" ] || sha256sum "$NAME" > "$NAME.sha256"
HASH=$(cut -d' ' -f1 "$NAME.sha256")
FILES=("$NAME.sha256")
if [ "$SIZE" -lt 2147000000 ]; then
  FILES+=("$NAME")
else
  split -b 1900M -d -a 3 --numeric-suffixes=1 "$NAME" "$NAME."
  PARTS=$(ls "$NAME".0* | tr '\n' ' ')
  PLUS=$(echo $PARTS | sed 's/ / + /g')
  BAT="JOIN-${NAME%.iso}-WINDOWS.bat"
  [ "$NAME" = "tejas-1.0-amd64.iso" ] && BAT="JOIN-TEJAS-WINDOWS.bat"
  printf '%s\r\n' '@echo off' 'cd /d "%~dp0"' 'echo.' \
    'echo  TEJAS: joining the pieces into one file. Please wait about a minute...' 'echo.' \
    "copy /b $PLUS \"$NAME\" >nul" \
    "if not exist \"$NAME\" (echo  Something is missing. Put all the pieces and this file in the same folder. & pause & exit /b 1)" \
    'echo  Checking the file, another minute...' \
    "certutil -hashfile \"$NAME\" SHA256 | findstr /i \"$HASH\" >nul && (echo. & echo  DONE! $NAME is ready. Now flash it to a USB stick with Rufus.) || (echo. & echo  The check failed: one piece did not download fully. Download it again.)" \
    'echo.' 'pause' > "$BAT"
  FILES+=($PARTS "$BAT")
fi
gh release view "$TAG" -R "$R" >/dev/null 2>&1 || \
  gh release create "$TAG" -R "$R" --target tejas-os --title "TEJAS OS 1.0" --latest=false \
    --notes "TEJAS OS 1.0 - free desktop OS. Lite = one file under 2 GB. Full = every app, in pieces: download all pieces + the JOIN file, double-click JOIN."
for f in "${FILES[@]}"; do
  for i in 1 2 3; do gh release upload "$TAG" "$f" -R "$R" --clobber && break || sleep 20; done
done
# The old Mac/Linux join script carried an old checksum: remove it.
gh release delete-asset "$TAG" join-tejas-mac-linux.sh -R "$R" -y >/dev/null 2>&1 || true
echo "::notice title=Published $NAME ($(numfmt --to=iec $SIZE))::https://github.com/$R/releases/tag/$TAG"

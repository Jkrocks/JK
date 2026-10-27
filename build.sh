#!/usr/bin/env bash
# Builds the TEJAS ISO. Runs on Debian 13 (or in a `debian:trixie` container
# started with --privileged). Needs root and about 25 GB of free disk.
#
#   sudo ./build.sh            -> out/tejas-1.0-amd64.iso
set -euo pipefail
cd "$(dirname "$0")"

VERSION="1.0"
EDITION="${EDITION:-full}"   # full | lite (lite fits in one file under 2 GB)
if [ "$EDITION" = "lite" ]; then
	OUT="out/tejas-${VERSION}-lite-amd64.iso"; PKGS=packages-lite.list
else
	OUT="out/tejas-${VERSION}-amd64.iso"; PKGS=packages.list
fi

if [ "$(id -u)" -ne 0 ]; then
	echo "Run as root: sudo ./build.sh" >&2
	exit 1
fi

echo "==> Installing build tools"
# Make sure the host can see the same archive areas the ISO uses.
if [ -f /etc/apt/sources.list.d/debian.sources ]; then
	sed -i 's/^Components: main$/Components: main contrib non-free-firmware/' /etc/apt/sources.list.d/debian.sources
fi
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
	live-build debootstrap squashfs-tools xorriso grub-efi-amd64-bin grub-pc-bin \
	mtools dosfstools syslinux syslinux-common isolinux ca-certificates

echo "==> Checking the package list against Debian 13"
mkdir -p config/package-lists
: > config/package-lists/tejas.list.chroot
missing=()
while read -r pkg; do
	pkg="${pkg%%#*}"; pkg="$(echo "$pkg" | xargs)"
	[ -z "$pkg" ] && continue
	cand="$(apt-cache policy "$pkg" 2>/dev/null | awk '/Candidate:/{print $2; exit}')"
	if [ -n "$cand" ] && [ "$cand" != "(none)" ]; then
		echo "$pkg" >> config/package-lists/tejas.list.chroot
	else
		missing+=("$pkg")
	fi
done < "$PKGS"
if [ "${#missing[@]}" -gt 0 ]; then
	echo "!! Skipping packages not found in Debian 13: ${missing[*]}"
fi
echo "   $(wc -l < config/package-lists/tejas.list.chroot) packages will be installed"

echo "$EDITION" > config/includes.chroot/etc/tejas-edition

echo "==> Building the $EDITION edition (this takes 30-60 minutes)"
lb clean --purge >/dev/null 2>&1 || true
if [ "$EDITION" = "lite" ]; then
	# Only the firmware in the package list (common Wi-Fi, sound, Intel/AMD graphics), not every firmware package.
	lb config --firmware-binary false --firmware-chroot false
else
	lb config
fi
lb build 2>&1 | tee build.log

iso="$(ls -1 ./*.hybrid.iso 2>/dev/null | head -n1 || true)"
if [ -z "$iso" ]; then
	echo "!! No ISO was produced. See build.log." >&2
	exit 1
fi
mkdir -p out
mv "$iso" "$OUT"
( cd out && sha256sum "$(basename "$OUT")" > "$(basename "$OUT").sha256" )
echo "==> Biggest packages inside:"
chroot chroot dpkg-query -Wf '${Installed-Size}\t${Package}\n' 2>/dev/null | sort -rn | head -40 | awk '{printf "   %6d MB  %s\n", $1/1024, $2}' | tee out/biggest-packages.txt || true
echo "==> Done: $OUT ($(du -h "$OUT" | cut -f1))"

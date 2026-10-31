# TEJAS OS

A free desktop operating system for PCs, where every app is free.
Built on **Debian 13** with **KDE Plasma 6**, in the TEJAS sky-glass style.

| | |
|---|---|
| Base | Debian 13 "trixie", Linux 6.12 LTS |
| Desktop | KDE Plasma 6, TEJAS layout: glass top bar, floating dock, sky wallpapers |
| Apps | Firefox, Thunderbird, LibreOffice, Inkscape, Krita, GIMP, Blender, Kdenlive, OBS Studio, VLC, Elisa, SuperTuxKart |
| More apps | Discover + Flathub, thousands of free apps in one click |
| Windows apps | **Bridge**: double-click a `.exe` (Bottles + Wine) |
| Installer | Calamares, branded "Install TEJAS" |
| Updates | Debian security updates until June 2030 |
| PCs | 64-bit (x86-64), UEFI and legacy BIOS, 4 GB RAM minimum (8 GB recommended), 40 GB disk |

## 1. Get the ISO

Download it from the public release, no GitHub account needed: **Releases → TEJAS OS 1.0** (`tejas-os-v1.0`).

- **Lite:** one file, `tejas-1.0-lite-amd64.iso` (under 2 GB).
- **Full:** download every piece (`.001`, `.002`, ...) plus `JOIN-TEJAS-WINDOWS.bat` into one folder and double-click the JOIN file.

To check it's genuine, see [SECURITY.md](SECURITY.md#checking-a-download-is-genuine).

Builders: every push to `tejas-os` builds and publishes a fresh ISO. **Actions → Build TEJAS ISO → Run workflow** builds on demand (pick `lite` or `full`, 45 to 90 minutes).

If a run goes red, download **build-log** from the same page. The last lines say what failed.

## 2. Put it on a USB stick (8 GB or bigger)

- **Windows:** [Rufus](https://rufus.ie). Choose the ISO and press Start. If it asks, pick **DD image mode**.
- **Mac / Windows / Linux:** [balenaEtcher](https://etcher.balena.io). Pick the ISO, the stick, and Flash.
- **Best for testing many ISOs:** [Ventoy](https://www.ventoy.net). Install it once, then just copy ISO files onto the stick.

This erases the USB stick.

## 3. Try it, then install

1. Plug the stick into the PC and restart. Open the boot menu: usually **F12**, **F11**, **F8** or **Esc** as the PC starts.
2. Choose the USB stick. TEJAS starts in **try-it mode**. Nothing on the PC changes.
3. To install, double-click **Install TEJAS** on the desktop.

Back up your files before installing. Choose "Install alongside" in the installer to keep Windows and pick at each start-up.

If the PC won't boot the stick, turn off **Secure Boot** in its firmware settings and try again.

## Change TEJAS

| To change | Edit |
|---|---|
| Which apps come built in | `packages.list` (one Debian package per line) |
| Logo, wallpapers (Night is the default), icons, boot splash | Replace `branding/src/tejas-logo-original.png`, then run `python3 branding/make_assets.py` |
| Dock apps and desktop layout | `config/includes.chroot/usr/share/plasma/look-and-feel/org.tejas.desktop/contents/layouts/org.kde.plasma.desktop-layout.js` |
| Colours and theme defaults | `.../org.tejas.desktop/contents/defaults` and `config/includes.chroot/etc/xdg/kdeglobals` |
| Name, version, boot entry | `config/hooks/live/0100-tejas-identity.hook.chroot` |
| Installer look | `config/hooks/live/0300-tejas-installer.hook.chroot` |
| Welcome page | `config/includes.chroot/usr/share/tejas/welcome/index.html` |
| Build options | `auto/config` |

Commit and push. GitHub builds a new ISO automatically.

## Build on your own machine (optional)

On Debian 13, or any Linux with Docker, with 25 GB free:

```bash
# Debian 13
sudo ./build.sh

# Any Linux with Docker
docker run --rm --privileged -v "$PWD":/build -w /build debian:trixie ./build.sh
```

The ISO lands in `out/`.

## How it's put together

```
auto/config                         live-build settings: Debian 13, amd64, UEFI + BIOS
packages.list                       everything installed (checked before each build)
build.sh                            one command: check packages, build, write out/*.iso
config/hooks/live/                  scripts run inside the new system while it's built
  0100-tejas-identity               name, os-release, boot entry, About page
  0200-tejas-boot-splash            Plymouth splash with the TEJAS logo
  0300-tejas-installer              Calamares rebrand ("Install TEJAS")
  0400-tejas-apps                   Flathub + Bottles for Bridge
config/includes.chroot/             files copied straight into the system
  usr/share/plasma/look-and-feel/   TEJAS desktop theme + layout
  usr/share/wallpapers/             Night (default), Morning, Noon, Dusk, Mint
  usr/bin/tejas-bridge              Bridge launcher (Windows apps)
  usr/bin/tejas-welcome             first-login welcome page
branding/                           logo source + asset generator
.github/workflows/build-iso.yml     cloud build
```

## Honest notes

- **Free apps, some non-free firmware.** Every app is free and open source. Wi-Fi and graphics chips often need the maker's firmware to work, so TEJAS includes Debian's `non-free-firmware` packages.
- **Windows apps through Bridge** run on Wine. Most apps work. Anti-cheat games, some Adobe apps and hardware drivers usually don't.
- **TEJAS is a Debian-based distribution.** Debian does the heavy lifting: kernel, drivers, security fixes. TEJAS is the design, the app choices, Bridge and the experience. That's how most modern Linux distributions are made.

## Licence

Build scripts: GPL-2.0-or-later. TEJAS logo and wallpapers: © JK Design, CC BY-SA 4.0.
Debian and KDE are trademarks of their respective owners. TEJAS is not affiliated with them.

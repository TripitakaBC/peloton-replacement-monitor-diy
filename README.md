# Peloton DIY Smart Bike — Build Guide

> **Turn a Peloton spin bike into a full entertainment and fitness tracking system using commodity hardware and open-source software.**

This guide walks through the complete build process, from hardware assembly to a working system with live stats overlay, ANT+ broadcasting to Garmin watches, Spotify, YouTube Music, Plex, and remote administration.

---

## Table of Contents

1. [Overview](#overview)
2. [Bill of Materials](#bill-of-materials)
3. [Hardware Assembly](#hardware-assembly)
4. [OS Installation](#os-installation)
5. [System Hardening & Debloat](#system-hardening--debloat)
6. [On-Screen Keyboard](#on-screen-keyboard)
7. [Multi-User Setup](#multi-user-setup)
8. [Serial Data Connection](#serial-data-connection)
9. [Python Stats Bar](#python-stats-bar)
10. [ANT+ & Heart Rate](#ant--heart-rate)
11. [Stats Bar Autostart](#stats-bar-autostart)
12. [Entertainment Apps](#entertainment-apps)
13. [Per-User Desktop Setup](#per-user-desktop-setup)
14. [Remote Administration](#remote-administration)
15. [Backup](#backup)
16. [Maintenance Scripts](#maintenance-scripts)
17. [Troubleshooting](#troubleshooting)

---

## Overview

### What This Build Does

- **Replaces the Peloton screen** with a touchscreen monitor driven by a small-form-factor PC
- **Displays a live stats bar** showing Heart Rate, HR Zone, Power, Cadence, Resistance, Time, and Calories overlaid on the GNOME taskbar
- **Broadcasts bike data via ANT+** so a Garmin watch can record rides with full power/cadence/speed data
- **Receives heart rate via ANT+** from a chest strap or arm band
- **Provides entertainment** via Spotify (with Spicetify), YouTube Music, FreeTube, and Plex HTPC
- **Supports multiple users** via native Ubuntu user accounts with PIN login at GDM
- **Remote administration** via SSH and RustDesk with a self-hosted relay server

### Architecture

```
Peloton Bike (3.5mm TRRS sensor output)
    │
    ▼
USB RS232 Adapter (with TX/RX crossover cable)
    │
    ▼
PC (/dev/ttyUSB0 → /dev/peloton_serial via udev symlink)
    │
    ├── peloton_strip.py (Python 3)
    │       ├── Reads serial data → Power, Cadence, Resistance
    │       ├── Calculates Speed, Distance, Calories
    │       ├── Renders Tkinter stats overlay on taskbar
    │       ├── ANT+ TX → Broadcasts Power/Cadence/Speed to Garmin watch
    │       └── ANT+ RX → Receives HR from ANT+ HR monitor
    │
    ├── GNOME Desktop (X11)
    │       ├── Spotify + Spicetify
    │       ├── YouTube Music (Brave PWA)
    │       ├── FreeTube (Flatpak)
    │       └── Plex HTPC (Flatpak)
    │
    └── Touchscreen (HDMI + USB touch)
```

---

## Bill of Materials

### Core Hardware

| Item | Purpose | Notes |
|---|---|---|
| Small-form-factor PC (e.g., Intel NUC) | Main computer | Any x86_64 PC with HDMI and USB. Mounted behind screen |
| Touchscreen monitor (1080p) | Display | Must have HDMI input and USB touch interface |
| DSD-Tech USB RS232 to 3.5mm female jack | Bike data connection | See [crossover cable section](#crossover-cable) |
| Additional 3.5mm female jack (bare wire) | TX/RX crossover | For the required crossover cable |
| USB ANT+ dongle | Garmin broadcast + HR receive | e.g., Dynastream/Garmin USB stick |
| USB Bluetooth dongle | Audio streaming | External BT avoids signal loss from behind screen |
| USB extension hub/cable | Port access | Brings ANT+ and BT to the front of the screen |

### Cables & Power

| Item | Purpose | Notes |
|---|---|---|
| DC extension cable (match PC voltage) | PC power | Runs inside the bike frame along existing cable path |
| Short DC extension (12V) | Monitor power | Extends original Peloton power supply to reach touchscreen |

### Peripherals (Optional)

| Item | Purpose | Notes |
|---|---|---|
| ANT+ HR monitor (e.g., Scosche Rhythm Sync) | Heart rate | Any ANT+ compatible HR monitor works |
| Garmin watch (or compatible ANT+ receiver) | Ride recording | Receives ANT+ power/cadence/speed data |
| Bluetooth earbuds | Audio | Connected via the USB BT dongle |

---

## Hardware Assembly

### Monitor Mounting

Mount the touchscreen where the original Peloton screen was. The PC mounts to the back of the monitor using a VESA adapter or adhesive mounting.

Connect:
- HDMI cable from PC to monitor
- USB cable from monitor (touch interface) to PC

### Power Routing

1. **PC:** Run a DC extension cable from the base of the bike up inside the frame, following the existing cable path. Connect to the PC's power input.
2. **Monitor:** The existing Peloton power supply feeds the touchscreen. You may need a short extension lead depending on your mounting position.

### Crossover Cable

The Peloton's 3.5mm TRRS output uses a serial RS232 protocol. The DSD-Tech USB RS232 adapter comes with a 3.5mm **male** jack. You need a **female** jack with bare wires to create a TX/RX crossover:

> [!IMPORTANT]
> The Peloton's TX (transmit) must connect to the adapter's RX (receive) and vice versa.

Wire the additional 3.5mm female jack as follows:

| Female Jack Wire | Connects To | DSD-Tech Male Jack Wire |
|---|---|---|
| Black (Ground) | → | Black (Ground) |
| White (TX) | → **crossover** → | Red (RX) |
| Red (RX) | → **crossover** → | White (TX) |
| Green | — | Leave unconnected |

Plug the Peloton's 3.5mm output into your female jack, and the DSD-Tech male jack plugs into the female jack at the other end.

> [!TIP]
> Refer to the [PeloMon project](https://github.com/ihaque/pelomon) for detailed hardware schematics of the Peloton serial interface.

### USB Device Placement

> [!WARNING]
> If the PC is mounted behind the screen, the on-board Bluetooth will suffer signal loss when you sit up on the bike (your body blocks the signal). Use a **separate USB Bluetooth dongle** brought to the front of the screen via the USB extension hub.

Place the **ANT+ dongle** and **BT dongle** on the USB extension, routed to the front/top of the monitor. Keep them physically separated (at least a few inches) to avoid 2.4GHz RF interference, which can cause audio artifacts (pops/zips) in BT earbuds.

---

## OS Installation

### Ubuntu 24.04 LTS

1. Install **Ubuntu 24.04 LTS** (minimal install, GNOME desktop)
2. Boot configuration:
   - UEFI boot
   - Secure Boot **disabled**
3. Create the primary admin user during installation (this is **User 1** — the system administrator)

### Disable Wayland

Wayland causes issues with RustDesk, Spotify, and X11-dependent applications. Force GDM and all sessions to use X11:

```bash
sudo nano /etc/gdm3/custom.conf
```

```ini
[daemon]
WaylandEnable=false
```

---

## System Hardening & Debloat

Remove unnecessary packages for a lean, purpose-built system:

```bash
# Remove printing/scanning
sudo apt purge -y cups cups-browsed cups-daemon cups-filters cups-ipp-utils \
    system-config-printer* printer-driver* hplip sane-utils libsane*

# Remove accessibility stack (except on-screen keyboard)
sudo apt purge -y orca brltty speech-dispatcher

# Remove enterprise directory services
sudo apt purge -y sssd* libnss-sss libpam-sss

# Remove cloud-init and crash reporting  
sudo apt purge -y cloud-init whoopsie apport

# Remove CJK input methods
sudo apt purge -y ibus-hangul ibus-libpinyin ibus-table*

# Remove unnecessary GNOME apps
sudo apt purge -y gnome-calendar gnome-contacts gnome-maps gnome-weather \
    gnome-clocks gnome-characters totem rhythmbox shotwell cheese

# Clean up
sudo apt autoremove -y
sudo apt clean
```

### Power Management

```bash
# Power button triggers suspend
gsettings set org.gnome.settings-daemon.plugins.power power-button-action 'suspend'

# Idle suspend after 30 minutes
gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-timeout 1800
gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type 'suspend'
```

---

## On-Screen Keyboard

Since this is a touchscreen device without a physical keyboard, install and enable the Onboard on-screen keyboard:

```bash
sudo apt install -y onboard
```

Enable it in GNOME accessibility settings:
```bash
gsettings set org.gnome.desktop.a11y.applications screen-keyboard-enabled true
```

The on-screen keyboard will appear automatically when a text input field is focused. This works at the GDM login screen and within user sessions.

> [!NOTE]
> Wi-Fi and Bluetooth audio are configured using standard Ubuntu settings. Refer to the [Ubuntu documentation](https://help.ubuntu.com/) for these standard setup procedures.

---

## Multi-User Setup

The system uses native Ubuntu user accounts. Each user logs in via GDM with a numeric PIN on the on-screen keyboard. The GNOME user list is displayed at the login screen for touch-friendly user selection.

### Create the Admin User

The admin user (**User 1**) is created during Ubuntu installation. This is the only user with `sudo` access and is responsible for system administration.

### Add Additional Users

For each additional user:

```bash
sudo adduser <username>
```

> [!NOTE]
> Additional users do not need `sudo` access. They are added to the `users` group by default, which is sufficient for normal use.

### Per-User Setup Checklist

**Each time you add a new user**, the following steps must be completed for that user. See the [Per-User Desktop Setup](#per-user-desktop-setup) section for details:

1. Set GNOME dock favorites (Spotify, YouTube Music, Plex, FreeTube)
2. Remove non-essential dock icons (Files, Help, etc.)
3. Ensure the YouTube Music `.desktop` file is globally accessible
4. Verify Spotify file permissions allow the new user to launch it

---

## Serial Data Connection

### udev Rule

Create a persistent device symlink for the Peloton serial adapter:

```bash
# Find the adapter's vendor/product ID
lsusb | grep -i "serial\|RS232\|CP210\|FTDI"

# Create udev rule
sudo nano /etc/udev/rules.d/99-peloton-serial.rules
```

```
SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", SYMLINK+="peloton_serial", MODE="0666"
```

> [!NOTE]
> Replace `idVendor` and `idProduct` with those from your specific adapter (commonly `10c4:ea60` for CP2102 or `0403:6001` for FTDI).

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
ls -la /dev/peloton_serial  # Verify
```

### Serial Protocol

The Peloton bike communicates at **19200 baud** via RS232. The Python script sends poll commands and decodes responses:

| Metric | Poll Command (hex) | Response Type |
|---|---|---|
| Cadence | `F6 F5 41 36` | Packet type `0x41` |
| Power | `F6 F5 44 39` | Packet type `0x44` |
| Resistance | `F6 F5 4A 3F` | Packet type `0x4A` |

---

## Python Stats Bar

### Dependencies

Install Python dependencies **globally** so all users can run the stats bar:

```bash
sudo apt install -y python3-tk python3-serial python3-pip
sudo pip3 install openant python-xlib --break-system-packages
```

> [!IMPORTANT]
> `python-xlib` **must** be installed globally. Without it, the stats bar calculates incorrect screen geometry and renders off-screen (invisible). This was a critical bug that took extensive troubleshooting to identify.

### Install the Script

```bash
sudo cp peloton_strip.py /usr/local/bin/peloton_strip.py
sudo chmod +x /usr/local/bin/peloton_strip.py
```

### ANT+ USB Permissions

The ANT+ dongle requires udev rules for non-root access:

```bash
sudo nano /etc/udev/rules.d/99-ant-usb.rules
```

```
SUBSYSTEM=="usb", ATTRS{idVendor}=="0fcf", MODE="0666"
```

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### What the Stats Bar Displays

The stats bar renders as two strips embedded in the GNOME taskbar:

**Left Strip (HR):** Heart rate (bpm), HR Zone (Z1–Z5) with colour-coded progress bar, Calories

**Right Strip (Bike):** Power (W), Cadence (RPM), Resistance (0–100%), Current time

The middle third of the taskbar remains clear for GNOME dock icons.

### Resistance Scaling

The Peloton reports raw resistance values between approximately 500 and 1000. The script maps these to a 0–100% range:
- Raw ≤ 500 → 0%
- Raw 750 → 50%
- Raw ≥ 1000 → 100%

---

## ANT+ & Heart Rate

### How Data Flows

The Python script acts as a **unified ANT+ manager** handling three channels simultaneously:

1. **RX Channel (Heart Rate):** Receives HR from any ANT+ HR monitor. Device Type 120, 4.06Hz.
2. **TX Channel (Power Meter):** Broadcasts power and cadence as ANT+ Power Meter (Device Type 11, Page 16).
3. **TX Channel (Bike Speed):** Broadcasts cumulative wheel revolutions as ANT+ Bike Speed sensor (Device Type 123).

### Garmin Integration

On your Garmin watch:
1. **Sensors & Accessories → Add New**
2. Pair the **Power Meter** (broadcasts as device number 12345)
3. Pair the **Speed Sensor** (device number 12346)
4. The HR monitor can pair directly to the Garmin via ANT+ independently

During a ride, the Garmin records a complete merged workout with power, cadence, speed, distance, and heart rate — all pushed to Garmin Connect.

---

## Stats Bar Autostart

### The Working Method: XDG Autostart

After extensive troubleshooting of systemd services, bash wrappers, and profile.d scripts, the reliable method for autolaunching a graphical Python/Tkinter application at login for **all users** is **XDG Autostart** via `/etc/xdg/autostart/`.

```bash
sudo nano /etc/xdg/autostart/peloton-strip.desktop
```

```ini
[Desktop Entry]
Type=Application
Name=Peloton Stats Strip
Exec=/usr/bin/python3 -u /usr/local/bin/peloton_strip.py
Hidden=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=10
```

> [!IMPORTANT]
> **Key flags:**
> - `-u` — Unbuffered Python output. Without this, errors are silently swallowed and debugging is impossible.
> - `X-GNOME-Autostart-Delay=10` — Waits 10 seconds after desktop is ready before launching. Ensures X11 and all display services are fully initialized.

This file lives in `/etc/xdg/autostart/` (global), so it applies to **every user** automatically. No per-user configuration is needed for the stats bar autostart.

### Why Other Methods Failed

| Method | Failure Reason |
|---|---|
| System-level systemd service | Cannot attach to user's X11 session |
| User-level systemd service | Per-user, not global; symlinks not reliably picked up |
| `/etc/profile.d/` script | Runs before graphical session is ready |
| XDG + `sh -c` wrapper | GNOME fails to parse complex `Exec` lines |
| XDG without `-u` flag | Silent failures, no diagnostic output |
| XDG without delay | Race condition with X11 initialization |

---

## Entertainment Apps

### Spotify + Spicetify

```bash
# Install Spotify
curl -sS https://download.spotify.com/debian/pubkey_C85668DF69375001.gpg | sudo gpg --dearmor --yes -o /etc/apt/trusted.gpg.d/spotify.gpg
echo "deb http://repository.spotify.com stable non-free" | sudo tee /etc/apt/sources.list.d/spotify.list
sudo apt update && sudo apt install -y spotify-client

# Install Spicetify (as the admin user, NOT with sudo)
curl -fsSL https://raw.githubusercontent.com/spicetify/cli/main/install.sh | sh

# Apply Spicetify
~/.spicetify/spicetify backup apply

# CRITICAL: Fix permissions for multi-user access
sudo chown -R root:root /usr/share/spotify/
sudo chmod -R a+rX /usr/share/spotify/
```

> [!CAUTION]
> **Every time you run `spicetify apply`**, it changes file ownership of `/usr/share/spotify/` to the running user with `700` permissions. Other users will see a **black screen with three white dots** because they can't read the app files. Always run the `chown`/`chmod` fix after applying Spicetify. The included [update script](#maintenance-scripts) handles this automatically.

#### Spotify `.desktop` Fix

Force Spotify to use X11 rendering (prevents black screen on some configurations):

```bash
sudo sed -i 's|^Exec=spotify|Exec=spotify --ozone-platform=x11|' /usr/share/applications/spotify.desktop
```

### YouTube Music

YouTube Music runs as a Brave browser PWA. Install Brave, then create a system-wide desktop entry:

```bash
# Install Brave browser
sudo curl -fsSLo /usr/share/keyrings/brave-browser-archive-keyring.gpg https://brave-browser-apt-release.s3.brave.com/brave-browser-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/brave-browser-archive-keyring.gpg] https://brave-browser-apt-release.s3.brave.com/ stable main" | sudo tee /etc/apt/sources.list.d/brave-browser-release.list
sudo apt update && sudo apt install -y brave-browser
```

```bash
sudo nano /usr/share/applications/youtube-music.desktop
```

```ini
[Desktop Entry]
Version=1.0
Terminal=false
Type=Application
Name=YouTube Music
Exec=brave-browser --app=https://music.youtube.com
Icon=/usr/share/icons/hicolor/256x256/apps/youtube-music.png
Categories=Audio;Music;
```

> [!NOTE]
> Use an **absolute path** for the `Icon=` field. The icon theme name lookup may fail for some users. Ensure the `.desktop` file has `644` permissions and `root:root` ownership.

### FreeTube

```bash
flatpak install -y flathub io.freetubeapp.FreeTube
```

Recommended channels for cycling content:
- Global Cycling Network (GCN)
- Indoor Cycling
- Kayleigh Cohen Cycling

### Plex HTPC

```bash
flatpak install -y flathub tv.plex.PlexHTPC
```

Plex Home handles per-user library context automatically.

---

## Per-User Desktop Setup

**These steps must be run for each user** — either logged in as that user on the desktop, or via `su - <username>` from the admin account.

### GNOME Dock Configuration

The dock sits at the bottom of the screen with only the entertainment apps visible:

```bash
# Remove non-essential icons and set the app lineup
gsettings set org.gnome.shell favorite-apps "['spotify.desktop', 'youtube-music.desktop', 'tv.plex.PlexHTPC.desktop', 'io.freetubeapp.FreeTube.desktop']"
```

### Verify App Access

For non-admin users, check that all app files are readable:

```bash
# Spotify (check after any Spicetify apply)
ls /usr/share/spotify/Apps/ >/dev/null 2>&1 && echo "Spotify: OK" || echo "Spotify: PERMISSION DENIED — run fix"

# YouTube Music desktop entry
cat /usr/share/applications/youtube-music.desktop >/dev/null 2>&1 && echo "YT Music: OK" || echo "YT Music: PERMISSION DENIED"
```

If any show "PERMISSION DENIED", fix from the admin account:
```bash
sudo chown -R root:root /usr/share/spotify/
sudo chmod -R a+rX /usr/share/spotify/
sudo chmod 644 /usr/share/applications/youtube-music.desktop
sudo chown root:root /usr/share/applications/youtube-music.desktop
```

### Stats Bar Autostart Verification

The stats bar autostarts globally via XDG Autostart (see [Stats Bar Autostart](#stats-bar-autostart)). No per-user action is needed. After a new user's first login, verify the stats bar appeared. If not, check:

```bash
journalctl --user -b | grep -i peloton
```

Common causes of failure for new users:
- `python-xlib` not installed globally (stats bar renders off-screen)
- Missing ANT+ USB permissions (stats bar crashes on ANT+ init)

---

## Remote Administration

### SSH

```bash
sudo apt install -y openssh-server
sudo systemctl enable ssh
```

### RustDesk

RustDesk provides remote desktop access, including at the GDM login screen (before any user logs in).

**Why Direct IP doesn't work:** RustDesk requires an ID/Relay server for the system daemon to register with. Without it, the background service cannot reliably accept connections, especially at the login screen.

**Solution: Self-hosted relay server**

Deploy RustDesk's `hbbs` (ID server) and `hbbr` (Relay server) on any Docker host on your LAN:

```bash
docker run -d --name hbbs \
    -p 21115:21115 -p 21116:21116 -p 21116:21116/udp -p 21118:21118 \
    -v ./data:/root rustdesk/rustdesk-server hbbs

docker run -d --name hbbr \
    -p 21117:21117 -p 21119:21119 \
    -v ./data:/root rustdesk/rustdesk-server hbbr
```

Configure the Peloton's RustDesk client to point at your server's LAN IP as the ID/Relay server.

---

## Backup

### Proxmox Backup Server (Optional)

If you have a Proxmox Backup Server on your network, a script can send full system images:

```bash
sudo nano /usr/local/bin/pbs-backup.sh
```

```bash
#!/bin/bash

PBS_IP="<your-pbs-server-ip>"
PBS_USER="root@pam!<token-name>"
PBS_DATASTORE="<datastore-name>"

export PBS_PASSWORD="<your-api-token>"
export PBS_FINGERPRINT="<your-server-fingerprint>"
export PBS_REPOSITORY="$PBS_USER@$PBS_IP:$PBS_DATASTORE"

echo "Starting backup to $PBS_REPOSITORY..."

proxmox-backup-client backup root.pxar:/ \
    --exclude /dev \
    --exclude /proc \
    --exclude /sys \
    --exclude /tmp \
    --exclude /run \
    --exclude /mnt \
    --exclude /media \
    --exclude /lost+found

[ $? -eq 0 ] && echo "Backup completed successfully." || { echo "Backup FAILED."; exit 1; }
```

```bash
sudo chmod +x /usr/local/bin/pbs-backup.sh
# Run with sudo to access all system files
sudo /usr/local/bin/pbs-backup.sh
```

---

## Maintenance Scripts

### App Update Script

A single script that updates all entertainment apps and handles Spicetify's permission issues:

```bash
nano ~/update-peloton-apps.sh
chmod +x ~/update-peloton-apps.sh
```

```bash
#!/bin/bash
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }

echo "=============================="
echo " Peloton Apps Updater"
echo "=============================="

# Spotify (apt)
echo "--- Spotify ---"
sudo apt update -qq 2>/dev/null
sudo apt install --only-upgrade -y spotify-client 2>/dev/null && info "Spotify updated" || warn "Already latest"

# Spicetify
echo "--- Spicetify ---"
SPICETIFY="$HOME/.spicetify/spicetify"
if [ -x "$SPICETIFY" ]; then
    $SPICETIFY upgrade 2>/dev/null || warn "Already latest"
    sudo chown -R $(whoami) /usr/share/spotify/
    $SPICETIFY restore -n 2>/dev/null
    $SPICETIFY backup apply -n 2>/dev/null && info "Spicetify applied" || warn "Spicetify apply failed"
fi

# Fix Spotify permissions (critical for multi-user)
echo "--- Fixing Spotify permissions ---"
sudo chown -R root:root /usr/share/spotify/
sudo chmod -R a+rX /usr/share/spotify/
info "Permissions fixed"

# FreeTube (Flatpak)
echo "--- FreeTube ---"
flatpak update -y io.freetubeapp.FreeTube 2>/dev/null && info "FreeTube updated" || warn "Already latest"

# Plex HTPC (Flatpak)
echo "--- Plex HTPC ---"
flatpak update -y tv.plex.PlexHTPC 2>/dev/null && info "Plex HTPC updated" || warn "Already latest"

echo "=============================="
echo " Update complete!"
echo "=============================="
```

---

## Troubleshooting

### Stats bar is invisible (renders off-screen)

**Cause:** `python-xlib` not installed globally. The fallback geometry places the window below the visible screen.

```bash
sudo pip3 install python-xlib --break-system-packages
```

### Spotify black screen with three white dots (non-admin users)

**Cause:** Spicetify changed `/usr/share/spotify/` ownership with `700` permissions.

```bash
sudo chown -R root:root /usr/share/spotify/
sudo chmod -R a+rX /usr/share/spotify/
```

### Stats bar autostart fails silently

1. Verify `-u` flag on the `Exec` line (unbuffered Python output)
2. Check `X-GNOME-Autostart-Delay=10` is present
3. Verify `.desktop` file permissions: `sudo chmod 644 /etc/xdg/autostart/peloton-strip.desktop`
4. Check logs: `journalctl --user -b | grep -i peloton`

### Bluetooth audio pops/zips

**Cause:** RF interference between ANT+ and BT dongles (both 2.4GHz).

**Fix:** Physically separate the dongles on different USB ports, as far apart as possible.

### USB serial not detected

```bash
lsusb | grep -i serial       # Check adapter is recognized
sudo dmesg | grep -i tty     # Check kernel messages
ls -la /dev/peloton_serial    # Verify udev symlink
```

---

## Project Structure (for GitHub)

```
peloton-diy/
├── README.md                      # This guide
├── scripts/
│   ├── peloton_strip.py           # Stats bar Python script
│   ├── update-peloton-apps.sh     # App update script
│   └── pbs-backup.sh              # Proxmox backup script (template)
├── config/
│   ├── peloton-strip.desktop      # XDG autostart entry
│   ├── 99-peloton-serial.rules    # udev rule for serial adapter
│   ├── 99-ant-usb.rules           # udev rule for ANT+ dongle
│   └── youtube-music.desktop      # YouTube Music PWA launcher
└── docs/
    └── troubleshooting.md         # Extended troubleshooting guide
```

---

## Credits & References

- **[PeloMon](https://github.com/ihaque/pelomon)** — Original Peloton serial protocol research and speed/distance formulas
- **[openant](https://github.com/Tigge/openant)** — Python ANT+ library
- **[Spicetify](https://spicetify.app/)** — Spotify customization tool (better lyrics support)
- **[RustDesk](https://rustdesk.com/)** — Open-source remote desktop

---

## License

This project is shared for educational and personal use. The Peloton serial protocol information is based on community reverse-engineering efforts.

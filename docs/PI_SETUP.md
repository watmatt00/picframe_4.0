# PicFrame 4.0 - Pi Setup Guide

Complete setup guide for a fresh Raspberry Pi.

**Upgrading an existing v3.0 frame?** See [UPGRADE_V3_TO_V4.md](UPGRADE_V3_TO_V4.md) instead.

**IMPORTANT FOR CLAUDE**: When guiding a user through Pi setup, prompt them explicitly
at each step checkpoint before moving to the next step. Do not assume any step is complete
unless the user confirms it.

## Prerequisites

- Raspberry Pi 4 or 5 (64-bit recommended)
- MicroSD card (32GB+ recommended)
- Display connected via HDMI
- Network connection (Ethernet or WiFi)
- Tailscale account

---

## Step 1: Raspberry Pi OS

**PROMPT USER**: "Have you flashed Raspberry Pi OS to the SD card and completed initial boot?"

1. Download [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
2. Flash **Raspberry Pi OS (64-bit)** to SD card
3. In imager settings:
   - Enable SSH
   - Set hostname (e.g., `tkframe`)
   - Configure WiFi if needed
   - Set username/password
4. Boot Pi and complete initial setup

```bash
# Optional: Configure additional settings
sudo raspi-config
```

**CHECKPOINT**: User should be able to SSH into the Pi.

---

## Step 2: Verify Python Version

**PROMPT USER**: "Confirm Python 3.11+ is available — the installer will fail immediately if not."

```bash
python3 --version
# Should be 3.11+
```

The installer handles OS updates and all package installs automatically. No manual `apt` steps needed.

**CHECKPOINT**: Ask user to confirm Python version is 3.11+.

---

## Steps 3–9: Full Install (single command)

**PROMPT USER**: "Now we'll run the combined installer. It asks a few questions upfront, then handles everything automatically — including multiple reboots."

Before running, generate a **Tailscale pre-auth key** to skip browser auth:
1. Go to [Tailscale admin → Settings → Keys](https://login.tailscale.com/admin/settings/keys)
2. Create a one-time, ephemeral auth key
3. Paste it when the installer prompts (or leave blank to auth via browser)

Run the installer:

```bash
curl -fsSL https://raw.githubusercontent.com/watmatt00/picframe_4.0/main/scripts/setup/install.sh -o /tmp/install.sh && sudo bash /tmp/install.sh
```

> **Note:** Keep this as a single line — the `\` line-continuation form breaks when pasted into a terminal. Process substitution (`sudo bash <(curl ...)`) also fails on Pi OS.

The installer prompts for:
- **Frame name** (hostname, e.g. `tkframe`)
- **Branch** (`main` for production, `dev` for testing)
- **Tailscale pre-auth key** (leave blank for browser auth)
- **Koofr email + app password** — generate an app password at [app.koofr.net](https://app.koofr.net) → Preferences → App passwords (use an app password, NOT your main account password)

Then it runs fully automatically through 4 reboots (~15–20 minutes total). It installs:
1. **OS update** — packages up to date
2. **Console mode** — no desktop environment needed
3. **Core packages** — labwc (Wayland compositor), SDL2, VLC, FFmpeg
4. **picframe** — display engine via pip, initialized with display defaults
5. **picframe_4.0** — repo cloned, venv created, API installed
6. **Config** — `~/.picframe/config.yaml` written with frame name + Funnel URL
7. **labwc** — Wayland compositor + systemd user service wired up
8. **API/sync/lights** — `picframe-api`, `picframe-sync`, `picframe-lights` services started
9. **Koofr** — credentials validated and configured (no dashboard step needed)
10. **Phase 6** — WiFi watchdog, AP portal, `picframe-config` tool installed

Optional services (pass as flags):
```bash
sudo bash /tmp/install.sh --with-samba --with-mqtt
```

**CHECKPOINT**: Ask user to confirm the script completes successfully and shows the summary banner.

---

## Step 10: Verify Installation

**PROMPT USER**: "Let's verify everything is working."

Check services:
```bash
# Pi3D display
systemctl --user status picframe.service

# API (if running via systemd)
systemctl --user status picframe-api.service
```

Test API locally:
```bash
curl http://localhost:8000/health
# {"status":"ok"}

curl http://localhost:8000/version
# {"version":"4.0.0","api":"picframe"}
```

Test via Tailscale Funnel:
```bash
curl https://<hostname>.<tailnet>.ts.net/health
# {"status":"ok"}
```

**CHECKPOINT**: Ask user to confirm both local and Funnel health checks pass.

---

## Verification Checklist

- [ ] `python3 --version` shows 3.11+
- [ ] `systemctl --user status picframe.service` shows loaded
- [ ] `rclone version` shows installed
- [ ] `tailscale status` shows connected
- [ ] `~/picframe_4.0/venv/` exists
- [ ] `~/.picframe/config.yaml` exists
- [ ] `curl http://localhost:8000/health` returns `{"status":"ok"}`
- [ ] `curl https://<hostname>.<tailnet>.ts.net/health` returns `{"status":"ok"}`
- [ ] `sudo systemctl status picframe-watchdog` shows active (running)
- [ ] `sudo picframe-config --show` prints state without errors

---

---

## WiFi Recovery — Usage Guide

### How setup mode is triggered

| Condition | When |
|-----------|------|
| First boot (`provisioned=false`) | Immediately on boot |
| WiFi lost > 10 minutes | `needs_setup` flag set; setup mode on next reboot |
| Manual trigger | `sudo picframe-config --force-setup` then reboot |

### What the frame does in setup mode

1. Photo display stops
2. Console (`/etc/issue`) shows a box with the hotspot name, AP password, and portal URL — visible above the login prompt
3. Frame broadcasts a WiFi hotspot: `PicFrame-<framename>` with a unique 8-character password derived from the Pi's serial number
4. Any URL resolves to `http://192.168.4.1` (DNS hijack via dnsmasq)

### Reconfiguring WiFi via hotspot

1. On your phone or laptop, connect to `PicFrame-<framename>` (password shown on console)
2. A captive portal should open automatically — or open a browser to `http://192.168.4.1`
3. Enter your home WiFi SSID and password
4. Frame reboots and reconnects; gallery resumes

### First-run setup (new frame, two steps)

**Step 1 — Portal:** Enter frame name + home WiFi credentials. Success page shows Step 2 instructions.

**Step 2 — Dashboard:** Rejoin your home WiFi, open `http://<framename>.local:8000` in a browser. A Koofr setup banner appears — enter your Koofr email and password. The frame validates credentials and starts syncing photos.

### Reconfiguring WiFi via SSH / `picframe-config`

If you can reach the frame over Tailscale or Ethernet:

```bash
# Update WiFi credentials (creates a NetworkManager connection profile)
sudo picframe-config --wifi-ssid "MyNetwork" --wifi-password "mysecret"
sudo reboot

# Show current frame state
sudo picframe-config --show

# Other commands
sudo picframe-config --frame-name "kframe"
sudo picframe-config --koofr-user "user@example.com" --koofr-pass "secret"
sudo picframe-config --force-setup     # trigger setup mode on next reboot
sudo picframe-config --clear-setup     # cancel a pending setup mode
```

### Checking watchdog and AP service logs

```bash
# Watchdog (WiFi monitor)
sudo journalctl -u picframe-watchdog -f

# AP setup service (hostapd + portal)
sudo journalctl -u picframe-ap-setup -f

# Current state
sudo cat /var/lib/picframe/state.yaml
```

---

## Claude Setup Prompt Sequence

When setting up a new Pi, Claude should follow this sequence:

1. **Ask**: "Is this a fresh Pi or updating an existing one?"
2. **Step 1**: "Have you flashed Raspberry Pi OS and can SSH in?"
3. **Step 2**: "Run system updates. Confirm Python 3.11+?"
4. **Steps 3–9**: "Before running the installer, have you generated a Tailscale pre-auth key and a Koofr app password? Run the installer and confirm it completes with the summary banner."
5. **Step 10**: "Run verification checks. All passing?"

## Troubleshooting

### SSH Connection Issues

```bash
# Check SSH service
sudo systemctl status ssh

# Check firewall
sudo ufw status
```

### Tailscale Funnel Not Working

1. Verify Funnel is enabled in [Tailscale admin console](https://login.tailscale.com/admin/acls)
2. Check Funnel status: `tailscale funnel status`
3. Verify API is running on port 8000

### Pi3D Not Displaying

1. Check service: `systemctl --user status picframe.service`
2. Check logs: `journalctl --user -u picframe.service -f`
3. Verify display: `echo $DISPLAY`

### WiFi Hotspot Not Appearing

1. Check watchdog entered setup mode: `sudo journalctl -u picframe-watchdog -n 20`
2. Check AP service started: `sudo systemctl status picframe-ap-setup`
3. Check hostapd is running: `sudo iw dev wlan0 info` — should show `type AP`
4. If `type managed` instead, NetworkManager reclaimed the interface — check AP service logs: `sudo journalctl -u picframe-ap-setup -n 30`

### Frame Won't Reconnect After Portal Submit

1. Check `needs_setup` was cleared: `sudo cat /var/lib/picframe/state.yaml`
2. Verify NM connection was created: `nmcli con show picframe-wifi`
3. If connection missing, reconfigure manually: `sudo picframe-config --wifi-ssid "..." --wifi-password "..."`

### API Won't Start

1. Check if port 8000 is in use: `lsof -i :8000`
2. Check Python path: `which python3`
3. Verify venv is activated: `source ~/picframe_4.0/venv/bin/activate`

## Test Pi Environment

For reference, the test Pi used during development:

| Property | Value |
|----------|-------|
| IP | 192.168.102.210 |
| Hostname | tkframe.local |
| Username | matt |
| Funnel URL | https://tkframe.tail7de60a.ts.net |

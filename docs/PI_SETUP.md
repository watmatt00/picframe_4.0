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

## Step 2: System Updates

**PROMPT USER**: "Let's update the system and install dependencies. Run these commands on the Pi:"

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git python3-pip python3-venv curl
```

Verify Python version:
```bash
python3 --version
# Should be 3.11+
```

**CHECKPOINT**: Ask user to confirm Python version is 3.11+.

---

## Step 3: Pi3D PictureFrame (Display Engine)

**PROMPT USER**: "Now we'll install the Pi3D display engine. This is what actually shows photos on the screen."

Install the display engine using our installer (derived from thedigitalpictureframe.com's 2025 guide):

```bash
curl -fsSL https://raw.githubusercontent.com/watmatt00/picframe_4.0/dev/scripts/setup/install_picframe.sh -o /tmp/install_picframe.sh && sudo bash /tmp/install_picframe.sh
```

> **Note:** Use the `curl -o /tmp/... && sudo bash` form — process substitution (`sudo bash <(curl ...)`) fails on Pi OS.

The script handles multiple reboots automatically and resumes where it left off. Total time ~8–12 minutes. It installs: labwc (Wayland compositor), SDL2, VLC, FFmpeg, picframe (via pip), and wires up the systemd user service.

Optional services (not installed by default):
```bash
# Add Samba file sharing and/or Mosquitto MQTT broker:
curl -fsSL https://raw.githubusercontent.com/watmatt00/picframe_4.0/dev/scripts/setup/install_picframe.sh -o /tmp/install_picframe.sh && sudo bash /tmp/install_picframe.sh --with-samba --with-mqtt
```

Verify installation after the final reboot:
```bash
systemctl --user status picframe.service
```

**CHECKPOINT**: Ask user to confirm `picframe.service` shows as loaded.

See [Pi3D Integration](PI3D_INTEGRATION.md) for more details.

---

## Steps 4–9: API Setup (automated)

**PROMPT USER**: "Now we'll run the API setup script. This handles rclone, Tailscale, the repo clone, config, systemd services, and Phase 6 WiFi recovery in one shot."

Run the setup script:

```bash
curl -fsSL https://raw.githubusercontent.com/watmatt00/picframe_4.0/dev/scripts/setup/setup_api.sh | bash -s -- --branch=dev --frame-name=YOUR_FRAME_NAME
```

For `main` branch (production frames):
```bash
curl -fsSL https://raw.githubusercontent.com/watmatt00/picframe_4.0/dev/scripts/setup/setup_api.sh | bash -s -- --branch=main --frame-name=YOUR_FRAME_NAME
```

The script handles:
1. **rclone** — installs if not present
2. **Tailscale** — installs, authenticates (browser URL printed — follow it), enables Funnel on port 8000
3. **picframe_4.0** — clones repo, checks out branch, creates venv, pip installs
4. **Config** — generates `~/.picframe/config.yaml`, writes frame name and Funnel URL
5. **Systemd** — deploys and starts `picframe-api.service` and `picframe-sync.timer`
6. **Phase 6** — runs `install_setup.sh` (WiFi watchdog, AP portal, picframe-config)
7. **Provisioned** — marks `provisioned=true` so frame doesn't enter AP portal on next boot

**Note on Tailscale Funnel**: Before running, approve Funnel for this node in the [Tailscale admin console](https://login.tailscale.com/admin/acls). If not yet approved, the script will print a URL — visit it to approve, then press Enter to continue.

**CHECKPOINT**: Ask user to confirm the script completes successfully and shows the summary banner.

---

## Step 10 (was Step 10): Verify Installation

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
4. **Step 3**: "Install Pi3D display engine. Confirm picframe.service loaded?"
5. **Step 4**: "Install rclone. Confirm `rclone version` works? Configure a remote now?"
6. **Step 5**: "Install Tailscale. Confirm connected? Funnel approved in admin console? What's your Funnel URL?"
7. **Step 6**: "Clone picframe_4.0 repo. Confirm venv created?"
8. **Step 7**: "Create config. What frame name? Confirm config.yaml exists?"
9. **Step 8**: "Start API. Any errors?"
10. **Step 9**: "Run Phase 6 installer. Confirm watchdog active and picframe-config --show works?"
11. **Step 10**: "Run verification checks. All passing?"

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

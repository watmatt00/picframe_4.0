# PicFrame 4.0 - Pi Setup Guide

Complete setup guide for a fresh Raspberry Pi.

## Prerequisites

- Raspberry Pi 4 or 5 (64-bit recommended)
- MicroSD card (32GB+ recommended)
- Display connected via HDMI
- Network connection (Ethernet or WiFi)
- Tailscale account

## Step 1: Raspberry Pi OS

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

## Step 2: System Updates

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git python3-pip python3-venv curl
```

Verify Python version:
```bash
python3 --version
# Should be 3.11+
```

## Step 3: Pi3D PictureFrame (Display Engine)

Install the display engine using the one-click installer:

```bash
bash <(curl -s https://raw.githubusercontent.com/helgeerbe/picframe/main/scripts/install_picframe.sh)
```

During setup, enter:
- **Picture directory**: `/home/<user>/Pictures`
- **Deleted pictures**: `/home/<user>/picframe_data/deleted_pictures`
- **Locale**: `en_US.UTF-8`

Verify installation:
```bash
systemctl --user status picframe.service
```

See [Pi3D Integration](PI3D_INTEGRATION.md) for more details.

## Step 4: rclone

Install rclone for cloud sync:

```bash
curl https://rclone.org/install.sh | sudo bash
```

Configure a remote (Koofr, Google Drive, etc.):
```bash
rclone config
```

Test connection:
```bash
rclone lsd <remote>:
```

## Step 5: Tailscale + Funnel

Install Tailscale:
```bash
curl -fsSL https://tailscale.com/install.sh | sh
```

Authenticate:
```bash
sudo tailscale up
```

**Important**: Before enabling Funnel, you must approve it in the [Tailscale admin console](https://login.tailscale.com/admin/acls).

Enable Funnel:
```bash
sudo tailscale funnel 443 http://localhost:8000
```

Verify Funnel URL:
```bash
tailscale funnel status
# Should show: https://<hostname>.<tailnet>.ts.net
```

## Step 6: picframe_4.0 Installation

Clone the repository:
```bash
cd ~
git clone https://github.com/watmatt00/picframe_4.0.git
cd picframe_4.0
```

Create virtual environment and install:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

## Step 7: Configuration

Create the config directory:
```bash
mkdir -p ~/.picframe
```

The API will create a default config on first run at `~/.picframe/config.yaml`.

Edit the config to set your frame details:
```bash
nano ~/.picframe/config.yaml
```

```yaml
frame:
  id: "tkframe"
  name: "Kitchen Frame"
  funnel_url: "https://tkframe.tail1234.ts.net"

display:
  current_source: "local"
  rotation_interval: 30

sync:
  interval: 900
  rclone_flags: []

logging:
  level: "INFO"
  retention_days: 7
  security_retention_days: 90
```

## Step 8: Start the API

For development/testing:
```bash
cd ~/picframe_4.0
source venv/bin/activate
python -m src.main
```

For production (systemd service - coming in Phase 4):
```bash
# Not yet implemented
systemctl --user enable picframe-api.service
systemctl --user start picframe-api.service
```

## Step 9: Verify Installation

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

## Verification Checklist

- [ ] `python3 --version` shows 3.11+
- [ ] `systemctl --user status picframe.service` shows loaded
- [ ] `rclone version` shows installed
- [ ] `tailscale status` shows connected
- [ ] `~/picframe_4.0/venv/` exists
- [ ] `curl http://localhost:8000/health` returns `{"status":"ok"}`
- [ ] `curl https://<hostname>.<tailnet>.ts.net/health` returns `{"status":"ok"}`

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

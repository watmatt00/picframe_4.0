# PicFrame 4.0 - Pi Setup Guide

Complete setup guide for a fresh Raspberry Pi.

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

**CHECKPOINT**: Ask user to confirm `picframe.service` shows as loaded.

See [Pi3D Integration](PI3D_INTEGRATION.md) for more details.

---

## Step 4: rclone

**PROMPT USER**: "Now we'll install rclone for syncing photos from cloud storage (Koofr, Google Drive, etc.)."

Install rclone for cloud sync:

```bash
curl https://rclone.org/install.sh | sudo bash
```

**CHECKPOINT**: Ask user to run `rclone version` and confirm it's installed.

**PROMPT USER**: "Do you want to configure a cloud remote now? (Koofr, Google Drive, etc.) This can also be done later."

If yes, configure a remote:
```bash
rclone config
```

Test connection:
```bash
rclone lsd <remote>:
```

**CHECKPOINT**: If remote configured, ask user to confirm `rclone listremotes` shows the remote.

---

## Step 5: Tailscale + Funnel

**PROMPT USER**: "Now we'll set up Tailscale for secure remote access. Do you have a Tailscale account?"

Install Tailscale:
```bash
curl -fsSL https://tailscale.com/install.sh | sh
```

Authenticate:
```bash
sudo tailscale up
```

**CHECKPOINT**: Ask user to confirm `tailscale status` shows connected.

**PROMPT USER**: "Before enabling Funnel, you must approve it in the Tailscale admin console. Have you done this?"

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

**CHECKPOINT**: Ask user to provide their Funnel URL (save this for config).

---

## Step 6: picframe_4.0 Installation

**PROMPT USER**: "Now we'll clone and install the picframe_4.0 API."

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

**CHECKPOINT**: Ask user to confirm `~/picframe_4.0/venv/` exists.

---

## Step 7: Configuration

**PROMPT USER**: "Now we'll create the configuration. What name do you want for this frame?"

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

**CHECKPOINT**: Ask user to confirm `~/.picframe/config.yaml` exists.

---

## Step 8: Start the API

**PROMPT USER**: "Ready to start the API for testing?"

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

**CHECKPOINT**: Ask user to confirm API started without errors.

---

## Step 9: Verify Installation

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
10. **Step 9**: "Run verification checks. All passing?"

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

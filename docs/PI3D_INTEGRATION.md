# PicFrame 4.0 - Pi3D PictureFrame Integration

## Overview

[Pi3D PictureFrame](https://github.com/helgeerbe/picframe) is an open-source digital picture frame software that handles:
- GPU-accelerated image rendering via Pi3D/OpenGL
- Smooth transitions between photos
- EXIF data display (date, location)
- MQTT-based remote control
- HTTP status interface

**We don't rewrite the display engine - we wrap and control it.**

## Installation

### One-Click Installer

Reference: [TheDigitalPictureFrame.com Installation Guide](https://www.thedigitalpictureframe.com/install-the-pi3d-pictureframe-software-with-one-click-2025-edition-raspberry-pi-2-3-4-5/)

The upstream helgeerbe install script no longer exists. We maintain our own at `scripts/setup/install_picframe.sh`, derived from the thedigitalpictureframe.com 2025 installer with these improvements:
- Username-agnostic (uses `$SUDO_USER` — works with any username, not just `pi`)
- Samba and Mosquitto/MQTT are optional flags, not installed by default
- Preserves reboot-resume progress tracking and Wayland/labwc setup

```bash
# Default (no Samba, no MQTT):
curl -fsSL https://raw.githubusercontent.com/watmatt00/picframe_4.0/dev/scripts/setup/install_picframe.sh -o /tmp/install_picframe.sh && sudo bash /tmp/install_picframe.sh

# With optional services:
curl -fsSL https://raw.githubusercontent.com/watmatt00/picframe_4.0/dev/scripts/setup/install_picframe.sh -o /tmp/install_picframe.sh && sudo bash /tmp/install_picframe.sh --with-samba --with-mqtt
```

> **Note:** Use the `curl -o /tmp/... && sudo bash` form — process substitution (`sudo bash <(curl ...)`) fails on Pi OS.

The installer:
1. Updates OS and sets boot to console mode (2 reboots)
2. Installs core packages: `labwc` (Wayland compositor), `libsdl2-dev`, `vlc`, `ffmpeg`
3. Creates virtual environment at `/home/<user>/venv_picframe` and installs `picframe` via pip
4. Creates `~/Pictures` and `~/picframe_data/deleted_pictures`
5. Creates `~/start_picframe.sh` launcher and `~/.config/labwc/autostart`
6. Sets up `~/.config/systemd/user/picframe.service` (runs `labwc` → picframe)
7. Enables linger so the service starts at boot without login

## File Locations

| Component | Path |
|-----------|------|
| Virtual environment | `/home/<user>/venv_picframe/` |
| Configuration | `/home/<user>/picframe_data/config/configuration.yaml` |
| Pictures directory | `/home/<user>/Pictures/` (configurable) |
| Deleted photos | `/home/<user>/picframe_data/deleted_pictures/` |
| Service | `~/.config/systemd/user/picframe.service` |

## Configuration

### configuration.yaml

```yaml
viewer:
  blur_amount: 12
  blur_zoom: 1.0
  edge_alpha: 0.0
  fps: 20.0
  background: [0.2, 0.2, 0.2, 1.0]
  blend_type: "blend"
  font_file: "/home/<user>/venv_picframe/lib/python3.11/site-packages/picframe/data/fonts/NotoSans-Regular.ttf"
  show_text_tm: 5.0
  fit: false
  kenburns: false
  display_x: 0
  display_y: 0
  display_w: 0
  display_h: 0

model:
  pic_dir: "/home/<user>/Pictures"
  deleted_pictures: "/home/<user>/picframe_data/deleted_pictures"
  no_files_img: "/home/<user>/venv_picframe/lib/python3.11/site-packages/picframe/data/no_pictures.jpg"
  follow_links: false
  subdirectory: ""
  recent_n: 0
  shuffle: true
  time_delay: 30.0
  fade_time: 2.0

mqtt:
  server: ""
  port: 1883
  login: ""
  password: ""
  tls: ""

http:
  use_http: false
  port: 9000
```

### Key Settings

| Setting | Description | Default |
|---------|-------------|---------|
| `model.pic_dir` | Directory containing photos | `/home/<user>/Pictures` |
| `model.shuffle` | Random order vs sequential | `true` |
| `model.time_delay` | Seconds between images | `30.0` |
| `model.fade_time` | Transition duration | `2.0` |
| `viewer.kenburns` | Ken Burns pan/zoom effect | `false` |
| `viewer.fit` | Fit image to screen (no crop) | `false` |

## Control Methods

### How picframe_4.0 Controls Pi3D

| Control Method | How We Use It |
|----------------|---------------|
| **Pi3D HTTP API** | Primary real-time control: subdirectory switching, pause/resume, time_delay (port 9000) |
| **Config file** | Persistence: updates `pic_dir` / `subdirectory` in `configuration.yaml` for reboot survival |
| **systemctl** | Start/stop/restart picframe.service (fallback when HTTP API unreachable or path is outside ~/Pictures) |
| **MQTT** | Available but not actively used — HTTP API preferred |

### systemctl Commands

```bash
# Check status
systemctl --user status picframe.service

# Start/stop/restart
systemctl --user start picframe.service
systemctl --user stop picframe.service
systemctl --user restart picframe.service

# Enable on boot
systemctl --user enable picframe.service
```

### MQTT Commands

Pi3D PictureFrame has built-in MQTT support for real-time control.

| Topic | Payload | Action |
|-------|---------|--------|
| `picframe/date_from` | `YYYY-MM-DD` | Filter photos from date |
| `picframe/date_to` | `YYYY-MM-DD` | Filter photos to date |
| `picframe/time_delay` | seconds | Delay between images |
| `picframe/fade_time` | seconds | Transition duration |
| `picframe/shuffle` | `true/false` | Random vs sequential |
| `picframe/paused` | `true/false` | Pause/resume playback |
| `picframe/back` | - | Previous photo |
| `picframe/subdirectory` | path | Show only subfolder |
| `picframe/delete` | - | Delete current image |
| `picframe/quit` | - | Exit Pi3D |

### Example MQTT Usage

```python
import paho.mqtt.client as mqtt

client = mqtt.Client()
client.connect("localhost", 1883)

# Pause playback
client.publish("picframe/paused", "true")

# Change time delay to 60 seconds
client.publish("picframe/time_delay", "60")

# Show only photos from 2025
client.publish("picframe/date_from", "2025-01-01")
client.publish("picframe/date_to", "2025-12-31")

# Switch to specific subdirectory
client.publish("picframe/subdirectory", "vacation/hawaii")
```

## Source Switching Strategy

picframe_4.0 manages multiple photo sources as directories under `~/Pictures/`:

```
~/Pictures/
  ├── koofr_main/          <- Synced from Koofr
  ├── google_drive/        <- Synced from Google Drive
  ├── local/               <- Local photos
  └── spotlight/           <- Temporary spotlight dir (permanent, never deleted)
```

To switch sources, picframe_4.0 uses Pi3D's HTTP API:

```
GET http://localhost:9000/?subdirectory=koofr_main
```

This triggers a live directory switch with a smooth fade transition — no service restart needed. The config file is also updated so the change survives reboots.

## HTTP Control Interface

Pi3D exposes a live control API on port 9000 (must be enabled in `configuration.yaml`):

```yaml
http:
  use_http: true
  port: 9000
```

**picframe_4.0 uses this as the primary control method** — it accepts `GET /?<key>=<value>` to change settings without any service restart, producing seamless fade transitions.

### HTTP API Commands

| Parameter | Value | Action |
|-----------|-------|--------|
| `subdirectory` | relative path or `""` | Switch to subdirectory inside `pic_dir` |
| `paused` | `true` / `false` | Pause or resume slideshow |
| `time_delay` | seconds | Change interval between photos |
| `shuffle` | `true` / `false` | Toggle random order |

### Source Switching Strategy

`display_service.switch_folder()` uses this priority:

1. If the target path is inside `~/Pictures`: send `GET /?subdirectory=<rel>` (seamless, no restart)
2. Always update `configuration.yaml` for persistence across reboots
3. Fall back to `systemctl restart picframe` only if the HTTP API is unreachable or the target is outside `~/Pictures`

### Spotlight Implementation

The spotlight feature (`POST /api/v1/display/spotlight`) uses the HTTP API to display a single photo temporarily:

1. Copy photo to `~/Pictures/spotlight/` (persistent dir so Pi3D keeps it indexed via SQLite)
2. Wait 2.5s for Pi3D's update scan to index the new file
3. Send `GET /?subdirectory=spotlight` to switch without restart
4. Wait 4.5s for the fade transition to complete (matches tkframe `fade_time: 3.0s`)
5. Send `GET /?paused=true` to freeze on the spotlight photo
6. After `duration_seconds`: send `paused=false`, then restore previous subdirectory
7. Clear spotlight dir contents (keep the dir so Pi3D's DB tracking is preserved)

## Troubleshooting

### Service Won't Start

```bash
# Check logs
journalctl --user -u picframe.service -f

# Verify display is available
echo $DISPLAY

# Check for GPU access
vcgencmd get_mem gpu
```

### No Pictures Showing

1. Verify `pic_dir` path exists and contains images
2. Check supported formats: JPEG, PNG, HEIF
3. Check file permissions

### MQTT Not Working

1. Verify MQTT broker is running: `systemctl status mosquitto`
2. Check configuration in `configuration.yaml`
3. Test with `mosquitto_pub -t "picframe/paused" -m "true"`

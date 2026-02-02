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

```bash
bash <(curl -s https://raw.githubusercontent.com/helgeerbe/picframe/main/scripts/install_picframe.sh)
```

The installer:
1. Creates virtual environment at `/home/<user>/venv_picframe`
2. Installs `picframe` package via pip
3. Creates config at `/home/<user>/picframe_data/config/configuration.yaml`
4. Sets up systemd user service

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
| **systemctl** | Start/stop/restart picframe.service |
| **MQTT** | Real-time commands (pause, next, shuffle, subdirectory) |
| **Config file** | Change settings, picture directory |
| **Symlink** | Switch photo sources by changing pic_dir symlink |

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

picframe_4.0 manages multiple photo sources by using symlinks:

```
/home/<user>/Pictures/          <- symlink to active source
/home/<user>/Pictures_sources/
  ├── koofr_main/              <- Synced from Koofr
  ├── google_drive/            <- Synced from Google Drive
  └── local/                   <- Local photos
```

To switch sources:
1. Update the symlink to point to the new source
2. Restart picframe service (or use MQTT to trigger rescan)

## HTTP Status Interface

Pi3D can optionally expose an HTTP interface for status:

```yaml
http:
  use_http: true
  port: 9000
```

This provides status info but picframe_4.0 uses MQTT for control instead.

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

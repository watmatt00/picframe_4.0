# PicFrame 4.0

Secure mobile management for Raspberry Pi picture frames.

## Overview

PicFrame 4.0 is a complete rewrite providing:
- **FastAPI backend** with JWT authentication
- **Web dashboard** for LAN-based management
- **Mobile app support** via Tailscale Funnel (no VPN needed)
- **Pi3D PictureFrame** integration for GPU-accelerated display
- **rclone sync** for cloud photo synchronization
- **WiFi recovery** — self-hosted hotspot + captive portal when WiFi credentials change

## Architecture

```
Mobile App ──(Tailscale Funnel)──> Pi API ──> Pi3D Display
Web Dashboard ──(LAN only)──────> Pi API ──> Pi3D Display
Contributors ──(Koofr)──────────> Cloud ──> rclone sync
WiFi lost ──────────────────────> Hotspot + Captive Portal ──> Reconfigure
```

## Current Status

**Phases 1-3 + Phase 6 Complete**

| Feature | Status |
|---------|--------|
| FastAPI skeleton | ✅ Done |
| Tailscale Funnel | ✅ Done |
| JWT authentication | ✅ Done |
| Device pairing (QR) | ✅ Done |
| Config management | ✅ Done |
| Dual logging | ✅ Done |
| rclone sync | ✅ Done |
| Web dashboard | ✅ Done |
| systemd service | ✅ Done |
| WiFi watchdog | ✅ Done |
| AP captive portal | ✅ Done |
| BLE setup service | ✅ Done |
| `picframe-config` CLI | ✅ Done |

### Web Dashboard Features
- **Status Tab**: Photo sync status, cloud/local photo counts, traffic light indicator, current image thumbnail, quick actions (Sync Now, Restart Frame, Restart API)
- **Switch Source Tab**: Source management, add new sources with rclone folder browser
- **Settings Tab**: Frame settings (name, rotation interval, sync interval, log level), device pairing (QR code + instructions), manage paired devices (inline table with revoke), log viewer (ops/security with auto-refresh)
- **OpenAPI Docs**: Auto-generated at `/docs` and `/openapi.json`

### WiFi Recovery (Phase 6)
When a frame loses WiFi for more than 10 minutes (or on first boot), it automatically enters setup mode:
1. Photo display stops; the console shows connection instructions
2. Frame broadcasts a `PicFrame-<name>` WiFi hotspot
3. Connect a phone or laptop to that network and open `http://192.168.4.1`
4. Enter new WiFi credentials — frame reboots and reconnects

SSH/command-line access is preserved throughout via the `picframe-config` tool.

## Quick Start

### Prerequisites
- Raspberry Pi 4/5 with 64-bit OS
- Pi3D PictureFrame installed
- Tailscale account with Funnel enabled

### Installation

```bash
# Clone repo
git clone https://github.com/watmatt00/picframe_4.0.git
cd picframe_4.0

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install
pip install -e .

# Run API (development mode)
python -m src.main
```

See [Pi Setup Guide](docs/PI_SETUP.md) for complete installation instructions.

### Access

- **Web Dashboard**: `http://<pi-ip>:8000` (LAN only, no auth required)
- **Remote API**: `https://<hostname>.<tailnet>.ts.net` (via Tailscale Funnel, JWT required)

### Test Endpoints

```bash
# Health check
curl http://localhost:8000/health

# Version
curl http://localhost:8000/version
```

## WiFi Recovery — Quick Reference

### What happens when WiFi is lost

| Condition | Behavior |
|-----------|----------|
| WiFi lost < 10 min | Gallery keeps running, watchdog waits |
| WiFi lost > 10 min | `needs_setup` flag set; setup mode on next reboot |
| `provisioned=false` (first boot) | Setup mode immediately |

### Reconfigure via hotspot (phone/laptop)

1. Look for `PicFrame-<framename>` in WiFi networks — password: `picframe`
2. Connect and open `http://192.168.4.1` (captive portal auto-opens on most phones)
3. Enter your home WiFi SSID and password, then submit
4. Frame reboots and reconnects

### Reconfigure via SSH / `picframe-config`

```bash
# Update WiFi credentials
sudo picframe-config --wifi-ssid "MyNetwork" --wifi-password "secret"

# Show current state
sudo picframe-config --show

# Manually trigger setup mode on next reboot
sudo picframe-config --force-setup

# Cancel a pending setup mode
sudo picframe-config --clear-setup
```

## Documentation

- [Full Specification](docs/SPECIFICATION.md)
- [Security Model](docs/SECURITY.md)
- [API Reference](docs/API.md)
- [Test Plan](docs/TEST_PLAN.md)
- [Pi3D Integration](docs/PI3D_INTEGRATION.md)
- [Pi Setup Guide](docs/PI_SETUP.md)

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linting
ruff check src/

# Run locally with auto-reload
uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000
```

## License

MIT

# PicFrame 4.0

Secure mobile management for Raspberry Pi picture frames.

## Overview

PicFrame 4.0 is a complete rewrite providing:
- **FastAPI backend** with JWT authentication
- **Web dashboard** for LAN-based management
- **Mobile app support** via Tailscale Funnel (no VPN needed)
- **Pi3D PictureFrame** integration for GPU-accelerated display
- **rclone sync** for cloud photo synchronization

## Architecture

```
Mobile App ──(Tailscale Funnel)──> Pi API ──> Pi3D Display
Web Dashboard ──(LAN only)──────> Pi API ──> Pi3D Display
Contributors ──(Koofr)──────────> Cloud ──> rclone sync
```

## Current Status

**Phases 1-3 Complete** - API Foundation + Remote Access + Web Dashboard

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

### Web Dashboard Features
- **Status Tab**: Photo sync status, cloud/local photo counts, traffic light indicator, current image thumbnail
- **Switch Source Tab**: Source management, add new sources with rclone folder browser
- **Settings Tab**: Frame name, rotation interval, sync interval (minutes), log level
- **Quick Actions**: Refresh, Sync Now, Restart Frame, Restart API
- **Device Pairing**: QR code generation for mobile app pairing
- **OpenAPI Docs**: Auto-generated at `/docs` and `/openapi.json`

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

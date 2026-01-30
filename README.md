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

## Quick Start

### Prerequisites
- Raspberry Pi 4/5 with 64-bit OS
- Pi3D PictureFrame installed
- rclone configured
- Tailscale account

### Installation

```bash
# Clone repo
git clone https://github.com/<your-org>/picframe_4.0.git
cd picframe_4.0

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install
pip install -e .

# Run install script
./scripts/install.sh

# Start service
systemctl --user enable picframe-api.service
systemctl --user start picframe-api.service
```

### Access

- **Dashboard**: `http://<pi-ip>:8000` (LAN only, no auth)
- **Mobile API**: `https://<hostname>.ts.net` (JWT auth via Tailscale Funnel)

## Documentation

- [Full Specification](docs/SPECIFICATION.md)
- [Security Model](docs/SECURITY.md)
- [API Reference](docs/API.md)
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

# Run locally
uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000
```

## License

MIT

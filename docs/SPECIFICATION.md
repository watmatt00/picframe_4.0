# WanderWall - Security & Mobile Management

## Project Overview

**New project, new repo, clean slate.**

- **Repo**: `wanderwall_frame` (new)
- **Mobile**: `wanderwall_app` (existing, updated for 4.0 API)
- **Display Engine**: [Pi3D PictureFrame](https://github.com/helgeerbe/picframe) (existing open-source)
- **Approach**: Pure Python implementation, no shell scripts
- **Development**: New Pi, built from ground up
- **3.0 Status**: Stays as-is, no migration during development

---

## Requirements Summary

- **Users**: Family + extended family/friends
- **Access Levels**:
  - **Admin**: Full control - service restarts, folder switching, capacity, device management
  - **Contributor**: Upload photos only via Koofr (no Pi access)
- **Admin Hierarchy**: All admins equal
- **Network**: Tailscale Funnel (no VPN on mobile)
- **Priority**: Security first

---

## Architecture

```
┌─────────────────┐                              ┌──────────────────────────────┐
│  Mobile App     │                              │  Pi Frame (4.0)              │
│  (iOS)          │      HTTPS (Funnel)          │                              │
│                 │─────────────────────────────>│  ┌────────────────────────┐  │
│  No VPN needed  │  https://frame.ts.net        │  │ Tailscale Funnel       │  │
└─────────────────┘                              │  └───────────┬────────────┘  │
                                                 │              │               │
┌─────────────────┐                              │              │               │
│  Web Dashboard  │      HTTP (LAN only)         │              │               │
│  (Browser)      │─────────────────────────────>│              │               │
│  http://pi:8000 │                              │              ▼               │
└─────────────────┘                              │  ┌────────────────────────┐  │
                                                 │  │ wanderwall_frame API       │  │
┌─────────────────┐                              │  │ (FastAPI)              │  │
│  Contributor    │      Koofr API               │  │ - Auth/Pairing         │  │
│  (upload only)  │─────────────────> Koofr ────>│  │ - Sync Engine          │  │
└─────────────────┘                   Cloud      │  │ - Config Mgmt          │  │
                                        │        │  │ - Web Dashboard        │  │
                                        │        │  └───────────┬────────────┘  │
                                        └───────>│              │               │
                                      rclone     │              │ controls      │
                                                 │              ▼               │
                                                 │  ┌────────────────────────┐  │
                                                 │  │ Pi3D PictureFrame      │  │
                                                 │  │ (Display Engine)       │  │
                                                 │  │ - Image rendering      │  │
                                                 │  │ - Transitions          │  │
                                                 │  │ - MQTT control         │  │
                                                 │  └────────────────────────┘  │
                                                 │                              │
                                                 │  Logs:                       │
                                                 │  - wanderwall.log              │
                                                 │  - security.log              │
                                                 └──────────────────────────────┘
```

---

## Web Dashboard

### Overview

The web dashboard provides browser-based management accessible **only on the local network**. No authentication required - if you're on the LAN, you have access.

- **URL**: `http://<pi-ip>:8000` or `http://<hostname>.local:8000`
- **Auth**: None (LAN-only)
- **Remote access**: Use mobile app instead (via Tailscale Funnel)

### Dashboard Features (Implemented)

The dashboard is a tabbed interface with three main sections:

#### Status Tab
| Feature | Endpoint | Description |
|---------|----------|-------------|
| **Traffic Light** | `GET /dashboard/status` | Visual sync indicator (green/amber/red) |
| **Photo Counts** | `GET /dashboard/status` | Cloud and local photo counts with mismatch detection |
| **Current Image** | `GET /current-image` | Thumbnail of currently displayed photo |
| **Service Status** | `GET /dashboard/status` | Frame display and dashboard service health |
| **Storage Info** | `GET /dashboard/status` | Disk usage percentage and capacity |
| **Quick Actions** | Various POST | Refresh, Sync Now, Restart Frame, Restart API |
| **Activity Log** | `GET /api/logs` | Recent log entries (collapsible) |

#### Switch Source Tab
| Feature | Endpoint | Description |
|---------|----------|-------------|
| **Source List** | `GET /api/sources` | Table of configured photo sources |
| **Source Switcher** | `POST /api/frame-live` | One-click switch to different source |
| **Add Source Form** | `POST /api/sources/create` | Create new source with folder browser |
| **Folder Browser** | `POST /api/rclone/list-dirs` | Navigate rclone remote directories |
| **Remote Selector** | `GET /api/rclone/remotes` | Dropdown of configured rclone remotes |
| **Connection Test** | `POST /api/config/test-remote` | Verify rclone remote connectivity |
| **Delete Source** | `POST /api/sources/delete` | Remove a photo source |

#### Settings Tab
| Feature | Endpoint | Description |
|---------|----------|-------------|
| **Frame Name** | `POST /api/settings` | Display name for the frame |
| **Rotation Interval** | `POST /api/settings` | Seconds between photos (auto-restarts frame) |
| **Sync Interval** | `POST /api/settings` | Minutes between cloud syncs |
| **Log Level** | `POST /api/settings` | DEBUG/INFO/WARNING/ERROR |
| **Mobile Pairing** | `POST /pairing/generate` (AJAX) | Inline QR code generation in Settings tab |
| **Device Management** | `GET /devices` | Link to paired devices list |

#### Other Dashboard Pages
| Page | URL | Description |
|------|-----|-------------|
| **Pairing** | `/pairing` | Generate QR code for mobile app |
| **Devices** | `/devices` | List and revoke paired devices |
| **Logs** | `/logs` | Full log viewer with filtering |

### Dashboard Technology

- **Backend**: FastAPI (same as API)
- **Frontend**: Jinja2 templates + HTMX (or vanilla JS)
- **Styling**: Tailwind CSS or simple custom CSS
- **No SPA framework** - Keep it simple, server-rendered

### Access Control

```
┌─────────────────────────────────────────────────────────────┐
│                      ACCESS MODEL                            │
├─────────────────────────────────────────────────────────────┤
│  LOCAL (LAN)           │  REMOTE (Internet)                 │
├────────────────────────┼────────────────────────────────────┤
│  Web Dashboard         │  Mobile App                        │
│  http://pi:8000        │  https://frame.ts.net              │
│  No auth required      │  JWT auth required                 │
│                        │  Via Tailscale Funnel              │
└────────────────────────┴────────────────────────────────────┘
```

---

## Pi3D PictureFrame Integration

### What is Pi3D PictureFrame?

[Pi3D PictureFrame](https://github.com/helgeerbe/picframe) is an open-source digital picture frame software that handles:
- GPU-accelerated image rendering via Pi3D/OpenGL
- Smooth transitions between photos
- EXIF data display (date, location)
- MQTT-based remote control
- HTTP status interface

**We don't rewrite the display engine - we wrap and control it.**

### Pi3D Installation (One-Click)

Reference: [TheDigitalPictureFrame.com Installation Guide](https://www.thedigitalpictureframe.com/install-the-pi3d-pictureframe-software-with-one-click-2025-edition-raspberry-pi-2-3-4-5/)

The one-click installer:
1. Creates virtual environment at `/home/pi/venv_picframe`
2. Installs `picframe` package via pip
3. Creates config at `/home/pi/picframe_data/config/configuration.yaml`
4. Sets up systemd user service

### Pi3D File Locations

| Component | Path |
|-----------|------|
| Virtual environment | `/home/pi/venv_picframe/` |
| Configuration | `/home/pi/picframe_data/config/configuration.yaml` |
| Pictures directory | `/home/pi/Pictures/` (configurable) |
| Deleted photos | `/home/pi/picframe_data/deleted_pictures/` |
| Service | `~/.config/systemd/user/picframe.service` |

### Pi3D Configuration (configuration.yaml)

```yaml
viewer:
  blur_amount: 12
  blur_zoom: 1.0
  edge_alpha: 0.0
  fps: 20.0
  background: [0.2, 0.2, 0.2, 1.0]
  blend_type: "blend"
  font_file: "/home/pi/venv_picframe/lib/python3.11/site-packages/picframe/data/fonts/NotoSans-Regular.ttf"
  show_text_tm: 5.0
  fit: false
  kenburns: false
  display_x: 0
  display_y: 0
  display_w: 0
  display_h: 0

model:
  pic_dir: "/home/pi/Pictures"
  deleted_pictures: "/home/pi/picframe_data/deleted_pictures"
  no_files_img: "/home/pi/venv_picframe/lib/python3.11/site-packages/picframe/data/no_pictures.jpg"
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

### How wanderwall_frame Controls Pi3D

| Control Method | How We Use It |
|----------------|---------------|
| **systemctl** | Start/stop/restart picframe.service |
| **MQTT** | Real-time commands (pause, next, shuffle, subdirectory) |
| **Config file** | Change settings, picture directory |
| **Symlink** | Switch photo sources by changing pic_dir symlink |

### MQTT Commands (Built into Pi3D)

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

---

## Repository Structure

### wanderwall_frame (New - Pi-side)

```
wanderwall_frame/
├── src/
│   ├── __init__.py
│   ├── main.py                 # Entry point
│   ├── api/
│   │   ├── __init__.py
│   │   ├── app.py              # FastAPI application
│   │   ├── routes/
│   │   │   ├── pairing.py      # /pair, /pairing/generate
│   │   │   ├── status.py       # /status, /version
│   │   │   ├── devices.py      # /devices CRUD
│   │   │   ├── services.py     # /services/{name}/restart
│   │   │   ├── display.py      # /display/folder
│   │   │   ├── folders.py      # /folders CRUD
│   │   │   └── contributors.py # /contributors/invite
│   │   └── dependencies.py     # Auth dependencies
│   │
│   ├── dashboard/
│   │   ├── __init__.py
│   │   ├── routes.py           # Dashboard page routes
│   │   ├── templates/
│   │   │   ├── base.html       # Base template
│   │   │   ├── dashboard.html  # Main dashboard
│   │   │   ├── settings.html   # Settings page
│   │   │   ├── devices.html    # Device management
│   │   │   ├── pairing.html    # QR code display
│   │   │   └── logs.html       # Log viewer
│   │   └── static/
│   │       ├── css/
│   │       │   └── dashboard.css
│   │       └── js/
│   │           └── dashboard.js
│   │
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── jwt_handler.py      # Token creation/validation
│   │   ├── pairing.py          # Code generation, QR display
│   │   └── models.py           # Token claims, device models
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── sync_service.py     # rclone sync operations
│   │   ├── display_service.py  # Display control, folder switching
│   │   ├── source_manager.py   # Photo source management
│   │   ├── status_service.py   # Shared status logic (counts, sync, capacity)
│   │   └── systemd_service.py  # Service control wrapper
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings.py         # Pydantic settings
│   │   ├── schema.py           # Config validation schemas
│   │   └── manager.py          # Config read/write with locking
│   │
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── devices.py          # Paired devices storage (JSON)
│   │   └── sources.py          # Photo sources storage
│   │
│   └── utils/
│       ├── __init__.py
│       ├── rclone.py           # rclone wrapper (Python, not shell)
│       ├── logging.py          # Dual logging setup
│       └── qr_generator.py     # QR code for pairing
│
├── tests/
│   ├── unit/
│   │   ├── test_auth.py
│   │   ├── test_sync.py
│   │   └── test_config.py
│   └── integration/
│       ├── test_api.py
│       ├── test_pairing.py
│       └── test_dashboard.py  # Dashboard page and form tests
│
├── config/
│   ├── config.example.yaml     # Example config (YAML, not bash)
│   └── sources.example.yaml    # Example sources
│
├── systemd/
│   └── picframe.service        # Single service file
│
├── scripts/
│   ├── install.sh              # Initial Pi setup
│   └── setup_tailscale.sh      # Tailscale + Funnel setup
│
├── pyproject.toml              # Dependencies, build config
├── requirements.txt            # Pinned dependencies
└── README.md
```

### wanderwall_app (iOS Mobile App)

**iOS only. Android is permanently on hold.**

```
wanderwall_app/
├── iosApp/
│   ├── iosApp/
│   │   ├── FrameClient.swift           # HTTP client for Pi API (/api/v1)
│   │   ├── KoofrClient.swift           # Koofr cloud upload client
│   │   ├── MainViewModel.swift         # View model with all API calls
│   │   ├── MainMenuView.swift          # Main menu with paired frames
│   │   ├── FrameDetailView.swift       # Frame detail (status, actions)
│   │   ├── DestinationsView.swift      # Switch Source view
│   │   ├── UploadSheetView.swift       # Photo upload to Koofr
│   │   ├── SettingsView.swift          # Settings (sync interval, logs)
│   │   ├── LogViewerView.swift         # Log viewer (ops/security)
│   │   ├── PairingView.swift           # Manual code pairing
│   │   └── Models/
│   │       ├── PairedFrame.swift       # Frame model with baseURL
│   │       └── FrameStatus.swift       # Status/response models
│   └── iosApp.xcodeproj/
│
└── api-tests/                          # Python CLI upload tool (legacy)
    └── koofr_upload.py
```

---

## Security Model

### Authentication Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Pi Frame   │     │   QR Code   │     │  Mobile App │
│             │     │             │     │             │
│ Generates:  │────>│ Contains:   │────>│ Scans QR    │
│ - 6-char    │     │ - URL       │     │ Extracts:   │
│   code      │     │ - Code      │     │ - URL       │
│ - Displays  │     │ - Name      │     │ - Code      │
│   on screen │     │             │     │             │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
                    POST /pair                 │
                    {code, device_name}        │
┌─────────────┐                         ┌──────▼──────┐
│  Pi Frame   │<────────────────────────│  Mobile App │
│             │                         │             │
│ Validates   │     Returns JWT         │ Stores:     │
│ code        │────────────────────────>│ - URL       │
│ Issues JWT  │     + frame info        │ - Token     │
│             │                         │ - Name      │
└─────────────┘                         └─────────────┘
```

### JWT Security

- **Algorithm**: HS256 with 256-bit secret
- **Secret**: Per-Pi, stored at `~/.wanderwall/jwt_secret` (600 perms)
- **Expiry**: 1 year with refresh capability
- **Claims**: device_id, device_name, role, frame_id, iat, exp

### Pairing Code Security

- **Format**: 6 alphanumeric, case-insensitive (e.g., `A3B-X7K`)
- **Keyspace**: 36^6 = 2.17 billion combinations
- **Attempt limit**: 3 failures = code invalidated
- **Expiry**: 5 minutes
- **Rate limit**: 3 codes per hour

---

## API Endpoints

| Endpoint | Method | Auth | Role | Description |
|----------|--------|------|------|-------------|
| `/version` | GET | None | - | API version |
| `/health` | GET | None | - | Health check |
| `/api/v1/pair` | POST | Code | - | Exchange code for JWT |
| `/api/v1/pairing/generate` | POST | JWT | Admin | Generate new pairing QR |
| `/api/v1/status` | GET | JWT | Admin | Frame status, capacity |
| `/api/v1/devices` | GET | JWT | Admin | List paired devices |
| `/api/v1/devices/{id}` | DELETE | JWT | Admin | Revoke device |
| `/api/v1/services` | GET | JWT | Admin | List services + status |
| `/api/v1/services/{name}/restart` | POST | JWT | Admin | Restart service |
| `/api/v1/display/folder` | GET | JWT | Admin | Current display folder |
| `/api/v1/display/folder` | POST | JWT | Admin | Switch folder (source_id) |
| `/api/v1/folders` | GET | JWT | Admin | List folders |
| `/api/v1/folders` | POST | JWT | Admin | Create folder |
| `/api/v1/contributors` | GET | JWT | Admin | List contributor invites |
| `/api/v1/contributors/invite` | POST | JWT | Admin | Generate Koofr invite |
| `/api/v1/settings` | GET | JWT | Admin | Get frame settings |
| `/api/v1/settings/sync-interval` | PUT | JWT | Admin | Update sync interval |
| `/api/v1/logs` | GET | JWT | Admin | Recent log entries |

---

## Configuration

### Config Files

WanderWall uses two configuration files:

| File | Purpose |
|------|---------|
| `~/.wanderwall/config.yaml` | Dashboard settings (frame name, sync interval, current source) |
| `~/picframe_data/config/configuration.yaml` | Pi3D PictureFrame settings (rotation interval, display options) |

### Dashboard Config: `~/.wanderwall/config.yaml`

```yaml
frame:
  id: "kframe"
  name: "Kitchen Frame"
  funnel_url: "https://kframe.tailnet.ts.net"

display:
  current_source: "koofr_main"
  rotation_interval: 30  # seconds (also written to picframe config)

sync:
  interval: 900  # seconds (displayed as minutes in UI)
  rclone_flags: ["--verbose"]

tailscale:
  funnel_port: 443

logging:
  level: "INFO"
  retention_days: 90
```

### Pi3D PictureFrame Config: `~/picframe_data/config/configuration.yaml`

The dashboard settings page writes directly to picframe's config for settings that affect display:

```yaml
model:
  time_delay: 30.0        # Rotation interval in seconds
  log_level: "WARNING"    # Log level
  pic_dir: "/home/matt/Pictures"
  shuffle: true
  # ... other picframe settings
```

When the rotation interval is changed via the dashboard, the picframe service is automatically restarted to apply the change.

### Sources Format: YAML

```yaml
# ~/.wanderwall/sources.yaml

sources:
  - id: "koofr_main"
    name: "Main Photos"
    local_path: "/home/pi/Pictures/koofr_main"
    rclone_remote: "koofr:KFR_kframe"
    enabled: true

  - id: "google_drive"
    name: "Google Drive"
    local_path: "/home/pi/Pictures/gdrive"
    rclone_remote: "gdrive:WanderWall"
    enabled: false
```

---

## Logging

### Dual Log Strategy

| Log | Purpose | Location | Retention |
|-----|---------|----------|-----------|
| `wanderwall.log` | Operations (sync, display, errors) | `~/.wanderwall/logs/` | 7 days |
| `security.log` | Auth events, API access, failures | `~/.wanderwall/logs/` | 90 days |

### Log Format

```
# wanderwall.log
2026-01-30 10:00:00 INFO  [sync] Sync started for source 'koofr_main'
2026-01-30 10:00:15 INFO  [sync] Sync complete: 3 new files
2026-01-30 10:00:16 INFO  [display] Restarted display service

# security.log
2026-01-30 10:00:00 INFO  [auth] PAIR_ATTEMPT ip=100.64.1.5 code=A3B-X7K
2026-01-30 10:00:01 INFO  [auth] PAIR_SUCCESS device=abc123 name="Matt's iPhone" role=admin
2026-01-30 10:05:00 INFO  [api] REQUEST device=abc123 method=GET path=/status status=200
```

---

## Implementation Phases

### Phase 1: Pi Core (wanderwall_frame)
1. Project setup (pyproject.toml, structure)
2. Config management (YAML, Pydantic validation)
3. Logging setup (dual logs)
4. Basic FastAPI skeleton
5. JWT auth module
6. Pairing system with QR generation

### Phase 2: Pi Services (wanderwall_frame)
7. rclone wrapper (Python)
8. Sync service
9. systemd service wrapper
10. Display/source management (Pi3D integration)
11. Status endpoint

### Phase 3: Web Dashboard (wanderwall_frame)
12. Dashboard base template and routing
13. Status/home page (file counts, service status)
14. Source switcher UI
15. Settings page (config editor)
16. Logs viewer
17. Device management page
18. Pairing QR display page

### Phase 4: Pi Deployment (wanderwall_frame)
19. Tailscale Funnel setup script
20. systemd service file
21. Install script for fresh Pi
22. Integration tests (API endpoints)
23. Dashboard tests (page loads, form submissions, UI interactions)

### Phase 5: Mobile App (wanderwall_app - iOS only)

**Note: Android is permanently on hold. iOS only.**

**Status: Core functionality complete.** App builds, runs on simulator, and works against live Pi API.

- ✅ Update FrameClient for Funnel URLs and `/api/v1` prefix
- ✅ Update PairedFrame model with baseURL
- ✅ Build in Xcode, fix compile errors
- ✅ Test on simulator against live Pi API
- ✅ Fix runtime issues (multiple rounds)
- ⬜ QR scanner view (iOS) - future
- ⬜ TestFlight beta distribution

### Phase 6: Admin Features (both)
29. Service restart endpoints + UI (dashboard + mobile)
30. Folder management endpoints + UI
31. Device management endpoints + UI
32. Contributor invite flow

### Phase 7: Polish
33. Comprehensive error handling
34. Offline state handling in mobile
35. Security testing
36. Documentation

---

## Dependencies

### wanderwall_frame (Pi)

```toml
[project]
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "pyjwt>=2.8.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "pyyaml>=6.0.1",
    "qrcode[pil]>=7.4.2",
    "python-multipart>=0.0.6",  # File uploads
    "filelock>=3.13.0",         # Config locking
    "jinja2>=3.1.0",            # Dashboard templates
    "aiofiles>=23.0.0",         # Async static file serving
    "paho-mqtt>=2.0.0",         # MQTT for Pi3D control
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.23.0",
    "httpx>=0.26.0",            # Test client
    "ruff>=0.1.0",              # Linting
]
```

### wanderwall_app (iOS)

**iOS**: SwiftUI, Foundation (URLSession), AVFoundation (future QR scanning) - no external dependencies

---

## Security Checklist

- [ ] JWT secret: 256-bit random, unique per Pi, 600 permissions
- [ ] Config files: 600 permissions, YAML (no code execution)
- [ ] Pairing codes: cryptographically random, 3 attempts, 5-min expiry
- [ ] Last admin protection: cannot remove last admin
- [ ] SSH recovery: `wanderwall-cli emergency-reset` command
- [ ] Input validation: Pydantic models for all inputs
- [ ] Path validation: No traversal in folder operations
- [ ] Rate limiting: Per-endpoint limits
- [ ] Service whitelist: Only allowed services can restart
- [ ] Tailscale Funnel: HTTPS only, no direct port exposure
- [ ] Security log: 90-day retention, 600 permissions

---

## Development Environment

### New Pi Setup - Complete Steps

#### Step 1: Raspberry Pi OS
```bash
# Flash Raspberry Pi OS (64-bit recommended) to SD card
# Boot Pi, complete initial setup
# Enable SSH, set hostname (e.g., "devframe")
sudo raspi-config
```

#### Step 2: System Updates
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git python3-pip python3-venv
```

#### Step 3: Pi3D PictureFrame (One-Click Installer)
```bash
# From: https://www.thedigitalpictureframe.com/install-the-pi3d-pictureframe-software-with-one-click-2025-edition-raspberry-pi-2-3-4-5/
bash <(curl -s https://raw.githubusercontent.com/helgeerbe/picframe/main/scripts/install_picframe.sh)

# Answer the setup questions:
# - Picture directory: /home/pi/Pictures
# - Deleted pictures: /home/pi/picframe_data/deleted_pictures
# - Locale: en_US.UTF-8

# Verify installation
systemctl --user status picframe.service
```

#### Step 4: rclone
```bash
# Install rclone
curl https://rclone.org/install.sh | sudo bash

# Configure remote (Koofr, Google Drive, etc.)
rclone config

# Test connection
rclone lsd <remote>:
```

#### Step 5: Tailscale + Funnel
```bash
# Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh

# Authenticate
sudo tailscale up

# Enable Funnel (requires Tailscale admin console approval)
sudo tailscale funnel 443 / http://localhost:8000

# Verify Funnel URL
tailscale funnel status
```

#### Step 6: wanderwall_frame Installation
```bash
# Clone repo
cd ~
git clone https://github.com/<your-org>/wanderwall_frame.git
cd wanderwall_frame

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -e .

# Run install script (sets up systemd, configs, etc.)
./scripts/install.sh

# Start service
systemctl --user enable wanderwall-api.service
systemctl --user start wanderwall-api.service
```

#### Step 7: Verify Installation
```bash
# Check services
systemctl --user status picframe.service      # Pi3D display
systemctl --user status wanderwall-api.service  # Our API

# Test API locally
curl http://localhost:8000/health

# Test via Tailscale Funnel
curl https://<hostname>.<tailnet>.ts.net/health
```

### Testing Strategy

| Test Type | Tool | Location |
|-----------|------|----------|
| Unit tests | pytest | `tests/unit/` |
| Integration tests | pytest + httpx | `tests/integration/` |
| API tests | httpx TestClient | `tests/integration/test_api.py` |
| Dashboard tests | pytest + httpx | `tests/integration/test_dashboard.py` |
| Mobile tests | XCTest / JUnit | In mobile repo |
| E2E tests | Manual | Real Pi + real phone |

### Dashboard Test Coverage

| Test | Description |
|------|-------------|
| Page loads | All dashboard pages return 200 |
| Status display | Status page shows correct file counts, service status |
| Source switching | Source switcher changes active source |
| Settings save | Settings form saves config correctly |
| Pairing QR | Pairing page generates valid QR code |
| Device list | Devices page lists paired devices |
| Logs display | Logs page shows recent entries |
| Service restart | Restart buttons trigger correct service restart |

---

## Migration Path (Future - Not Part of Initial Build)

Once 4.0 is stable and tested:

1. **Parallel deployment**: Run 4.0 on new Pi alongside 3.0 on existing
2. **Mobile app versioning**: Detect API version, support both
3. **Data migration script**: Convert 3.0 config to 4.0 YAML
4. **Gradual rollout**: Migrate one frame at a time
5. **3.0 deprecation**: After all frames migrated

---

## Chat-to-Repo Migration Steps

### Step 1: Create the New Repository

```bash
# On your development machine
mkdir wanderwall_frame
cd wanderwall_frame
git init

# Create initial structure
mkdir -p src/{api/routes,auth,services,config,storage,utils}
mkdir -p tests/{unit,integration}
mkdir -p config systemd scripts docs
touch README.md
```

### Step 2: Copy This Plan to Repo

```bash
# Copy this plan file as the project specification
cp ~/.claude/plans/replicated-tickling-cocke.md docs/SPECIFICATION.md

# Create a summary README
# (Claude will generate this from the spec)
```

### Step 3: Create Core Documentation Files

Create these files in the new repo:

| File | Content Source |
|------|----------------|
| `docs/SPECIFICATION.md` | This plan file (full details) |
| `docs/SECURITY.md` | Security Model section from this plan |
| `docs/API.md` | API Endpoints section from this plan |
| `docs/PI3D_INTEGRATION.md` | Pi3D PictureFrame Integration section |
| `README.md` | Summary of project overview |
| `CONTRIBUTING.md` | Development workflow, coding standards |

### Step 4: Initialize Project Files

```bash
# pyproject.toml - copy Dependencies section from this plan
# requirements.txt - generate from pyproject.toml
# .gitignore - standard Python gitignore
# .env.example - environment variables template
```

### Step 5: Create Initial Code Stubs

Based on Repository Structure section, create empty files with docstrings:

```python
# src/api/app.py
"""
WanderWall API - FastAPI Application

See docs/SPECIFICATION.md for full details.
"""
from fastapi import FastAPI

app = FastAPI(
    title="WanderWall API",
    description="Secure mobile management for Raspberry Pi picture frames",
    version="4.0.0"
)
```

### Step 6: Set Up GitHub Repository

```bash
# Create repo on GitHub (wanderwall_frame)
# Add remote
git remote add origin https://github.com/<your-org>/wanderwall_frame.git

# Initial commit
git add .
git commit -m "Initial project structure from specification"
git push -u origin main
```

### Step 7: Create GitHub Issues from Implementation Phases

Convert each implementation phase to GitHub issues:

| Issue | Title | Labels |
|-------|-------|--------|
| #1 | Phase 1: Project setup and config management | `phase-1`, `pi` |
| #2 | Phase 1: Logging setup (dual logs) | `phase-1`, `pi` |
| #3 | Phase 1: FastAPI skeleton | `phase-1`, `pi` |
| #4 | Phase 1: JWT auth module | `phase-1`, `pi`, `security` |
| #5 | Phase 1: Pairing system with QR | `phase-1`, `pi`, `security` |
| #6 | Phase 2: rclone wrapper | `phase-2`, `pi` |
| #7 | Phase 2: Sync service | `phase-2`, `pi` |
| ... | (continue for all phases) | |

### Step 8: Link Mobile Repo

```bash
# In wanderwall_app repo, create tracking issue
# Title: "Support WanderWall API"
# Reference wanderwall_frame repo
# List mobile changes needed (from Phase 4 of this plan)
```

### Step 9: Development Workflow

```bash
# When starting implementation, use Claude Code with context:
cd wanderwall_frame
claude

# Point Claude to the specification:
# "Read docs/SPECIFICATION.md and implement Phase 1, Step 1"
```

### Key Documents to Transfer

| From This Chat | To Repo Location | Purpose |
|----------------|------------------|---------|
| Full plan | `docs/SPECIFICATION.md` | Complete project spec |
| Architecture diagram | `docs/ARCHITECTURE.md` | Visual overview |
| API endpoints table | `docs/API.md` | API reference |
| Security model | `docs/SECURITY.md` | Security documentation |
| Pi setup steps | `docs/PI_SETUP.md` | Installation guide |
| Pi3D integration | `docs/PI3D_INTEGRATION.md` | Display engine docs |

---

## Open Questions (Resolved)

- ✅ Approach: Option B - Pure Python, new repo (wanderwall_frame)
- ✅ Migration: None - clean slate, 3.0 stays as-is
- ✅ Development: New Pi, fresh build
- ✅ Display Engine: Pi3D PictureFrame (wrap, don't rewrite)
- ✅ Security: JWT + Tailscale Funnel + alphanumeric codes
- ✅ Logging: Separate files (ops + security)
- ✅ Admin hierarchy: All admins equal
- ✅ Contributors: Koofr-only via invite flow
- ✅ Config format: YAML (not bash)

# WanderWall - Security & Mobile Management

## Project Overview

**New project, new repo, clean slate.**

- **Repo**: `wanderwall_frame` (new)
- **Mobile**: `wanderwall_app` (iOS: WanderWall – Photo Frame and WanderWall Share)
- **Display Engine**: [Pi3D PictureFrame](https://github.com/helgeerbe/picframe) (existing open-source)
- **Approach**: Pure Python implementation, no shell scripts
- **Development**: New Pi, built from ground up
- **3.0 Status**: Stays as-is, no migration during development

---

## Requirements Summary

- **Users**: Family + extended family/friends
- **Access Levels**:
  - **Admin**: Full control - service restarts, folder switching, capacity, device management
  - **Contributor**: Upload photos only, with the WanderWall Share app (`/api/v1/contributor/*`; no frame settings)
- **Admin Hierarchy**: All admins equal
- **Network**: Tailscale Funnel (no VPN on mobile)
- **Priority**: Security first

---

## Architecture

```
┌─────────────────┐                              ┌──────────────────────────────┐
│  Mobile App     │                              │  Pi Frame (5.0)              │
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
│  Manager app    │      Koofr API               │  │ - Auth/Pairing         │  │
│  (photo upload) │─────────────────> Koofr ────>│  │ - Sync Engine          │  │
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

The dashboard is one page (`GET /`, `src/dashboard/templates/dashboard.html` + `static/js/dashboard.js`) with five tabs: **Frame Status | Albums | Tools | Backups | Settings**. Every endpoint below is in [API.md](API.md#dashboard-endpoints-lan-and-tailnet-only-no-auth). Banners above the tabs show demo mode and the album registry's questions (SD card last used on another Pi; this frame taken over by another Pi).

#### Frame Status tab
| Feature | Endpoint | Description |
|---------|----------|-------------|
| **Traffic Light** | `GET /dashboard/status` | Sync indicator (green/amber/red, blue while syncing) |
| **Photo Counts** | `GET /dashboard/status` | Cloud and frame counts for the album showing |
| **Current Image** | `GET /current-image` | The photo on screen now |
| **Service Status** | `GET /dashboard/status` | Display, API, sync timer, lights, Tailscale health |
| **Storage Info** | `GET /dashboard/status` | SD card use |
| **Quick Actions** | `POST /sync`, `/services/{name}/restart`, `/system/reboot` | Refresh, Sync Now, Restart Frame, Restart API, Reboot Frame |

#### Albums tab
| Feature | Endpoint | Description |
|---------|----------|-------------|
| **Album List** | `GET /api/sources` | Name, cloud folder, cloud and frame counts, status; technical columns (ID, local path, actions) behind a toggle |
| **Show on Frame** | `POST /api/frame-live` | "Activate": show the album and sync it |
| **Add Album** | `POST /api/sources/create` | Display Name only; the album id, local folder and cloud folder (`KFR_<id>`, or `_2`… if taken, PL-165) come from it |
| **Delete** | `POST /api/sources/delete` | Deletes the album **and its photos on the frame**; the cloud folder and backups are kept (PL-147). Hidden for the album that's showing |

#### Tools tab
An **Album** picker shared by the cards (reloaded each time the tab opens), then: Filename Cleaner, Duplicate Finder, Video File Manager, Corrupt Photo Finder, Rename File, Rotate Photos. Each scans first (read-only), shows the results, and applies changes to the cloud folder first, then the frame (`/api/tools/{id}/scan/*`, `/apply/*`, `/rename`).

#### Backups tab (PL-164)
| Feature | Endpoint | Description |
|---------|----------|-------------|
| **Photo Backups** | `/api/tools/backup/*` | Own picker: **Whole frame** (default) or one album. Create, list (full path on the frame), Restore, Download, Delete. A whole-frame backup is one `frame_<name>_<ts>.tar.gz` with a manifest, restored in one click |
| **Recover Albums** | `/api/albums/*` | Deleted albums from cloud storage (this frame's; unclaimed folders behind a warning), take over another frame, upload a .zip/.tar.gz (up to 16 GB; a whole-frame backup restores all its albums) |

Every restore skips photos the album already has, so nothing is duplicated. The picker and the Recover list reload each time the tab opens.

#### Settings tab
| Feature | Endpoint | Description |
|---------|----------|-------------|
| **Frame Settings** | `POST /api/settings`, `/api/settings/log-level` | Frame name, rotation interval (restarts the display), sync interval, fade time, log level; read-only Frame ID and Funnel URL |
| **Network / Cloud Sync** | `GET /dashboard/status`, `/dashboard/koofr-setup`, `/api/cloud/test` | LAN IP and WiFi; Koofr setup and connection test |
| **Display Sleep Schedule** | `POST /api/settings/sleep-schedule` | Display off and on times |
| **Mobile App Pairing** | `POST /pairing/generate` | Pairing code and QR, with countdown |
| **Paired Devices** | `GET /api/devices`, `POST /devices/{id}/revoke` | List and revoke (not the last admin) |
| **Logs** | `GET /api/logs` | Ops or security log |
| **Updates** | `/api/updates/*` | Check, apply, automatic check schedule |
| **Demo Mode** | `/api/settings/demo*` | Reviewer codes, only when `demo.allowed` is set (PL-015) |
| **Party Mode** | `POST /api/settings/party` | Stops cloud sync and the WiFi watchdog |

There are no other dashboard pages.

### Dashboard Technology

- **Backend**: FastAPI (same app as the API)
- **Frontend**: one Jinja2 template plus vanilla JS (`fetch` calls to the endpoints above)
- **Styling**: custom CSS (`static/css/`)
- **No SPA framework**

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

### wanderwall_frame (Pi-side)

From the repo as of 2026-10-21 (5.0.0):

```
wanderwall_frame/
├── src/
│   ├── main.py                    # Entry point (uvicorn)
│   ├── api/
│   │   ├── app.py                 # FastAPI app, routers, upload size limits
│   │   ├── middleware.py          # LAN-only (deny by default), upload limits
│   │   ├── dependencies.py        # Auth: get_current_device, require_admin, require_contributor
│   │   └── routes/                # /api/v1 (see docs/API.md)
│   │       ├── pairing.py         # /pair, /pairing/generate
│   │       ├── auth.py            # /auth/refresh
│   │       ├── status.py          # /status
│   │       ├── devices.py         # /devices
│   │       ├── services.py        # /services
│   │       ├── system.py          # /system/reboot
│   │       ├── display.py         # /display/folder, /display/spotlight
│   │       ├── folders.py         # /folders (albums), sync
│   │       ├── photos.py          # /sources/{id}/photos
│   │       ├── tools.py           # /sources/{id}/tools
│   │       ├── contributors.py    # /contributors (invites)
│   │       ├── contributor.py     # /contributor (Share app uploads)
│   │       ├── cloud.py           # /cloud/credentials
│   │       ├── settings.py        # /settings
│   │       ├── logs.py            # /logs
│   │       └── updates.py         # /updates
│   ├── dashboard/
│   │   ├── routes.py              # The dashboard page and its JSON endpoints
│   │   ├── templates/dashboard.html
│   │   └── static/{css/dashboard.css, js/dashboard.js}
│   ├── auth/                      # jwt_handler.py, pairing.py, models.py
│   ├── config/                    # settings.py, schema.py, manager.py (locked YAML writes)
│   ├── services/
│   │   ├── source_manager.py      # Albums (sources.yaml), cloud folder naming (PL-165)
│   │   ├── sync_service.py        # rclone sync
│   │   ├── display_service.py     # Pi3D control, album switching
│   │   ├── status_service.py      # Counts, sync state, capacity
│   │   ├── systemd_service.py     # Service control (allowlist), timers
│   │   ├── album_service.py       # Delete Album (PL-147)
│   │   ├── frame_registry.py      # Per-frame album registry, take over, SD card swap (PL-147)
│   │   ├── recovery_service.py    # Recover Albums, restores (PL-147, PL-164)
│   │   ├── backup_service.py      # Album and whole-frame backups (PL-164)
│   │   ├── photo_tools_service.py # Filename Cleaner, duplicates, videos, rename
│   │   ├── update_service.py      # Software updates
│   │   ├── power_service.py       # Reboot (PL-142)
│   │   ├── party_service.py       # Party mode
│   │   └── demo_service.py        # Demo mode (PL-015)
│   ├── storage/                   # devices.py, invites.py, sources.py
│   └── utils/                     # rclone.py, logging.py, network.py, qr_generator.py, thumbnails.py
├── tests/
│   ├── unit/                      # ~30 test files (pytest)
│   └── integration/               # test_api.py, test_pairing.py, test_dashboard.py
├── config/config.example.yaml
├── systemd/                       # wanderwall-api.service, wanderwall-sync.{service,timer}, wanderwall-lights.service
├── scripts/
│   ├── install.sh                 # Fresh install (--from-v4 for a v4 frame)
│   ├── update_app.sh              # Pull + restart (how frames update)
│   ├── setup_tailscale.sh
│   ├── indicator_lights.py        # Lights overlay
│   ├── pi/wanderwall-inspect      # Read-only inspection helper
│   └── setup/                     # First-run setup: AP portal, BLE, WiFi watchdog,
│                                  # wanderwall-{ap-setup,ble-setup,watchdog}.service, rollback_v4.sh
├── pyproject.toml
└── README.md
```

The display engine is upstream Pi3D PictureFrame, which keeps its own names (`picframe.service`, `~/picframe_data`).

### wanderwall_app (iOS Mobile App)

**iOS only. Android is permanently on hold.** Two apps from one source folder: **WanderWall – Photo Frame** (Manager, `com.txphipps.wanderwall`) and **WanderWall Share** (Contributor, `com.txphipps.wanderwall.share`). Screens: `wanderwall_app/docs/SCREEN_MAP.md`.

```
wanderwall_app/
├── iosApp/
│   ├── iosApp/
│   │   ├── iosAppApp.swift             # Manager app entry
│   │   ├── ContributorApp.swift        # Share app entry
│   │   ├── FrameClient.swift           # HTTP client for the frame API (/api/v1)
│   │   ├── KoofrClient.swift           # Koofr cloud upload client (Manager uploads)
│   │   ├── MainViewModel.swift         # View model with the API calls
│   │   ├── MainContentView.swift, MainMenuView.swift, FrameListView.swift, FrameDetailView.swift
│   │   ├── FrameSettingsView.swift     # Manage Frame
│   │   ├── DestinationsView.swift      # Albums, New Album, Album Detail
│   │   ├── ManagePhotosView.swift, UploadSheetView.swift, UploadLinkSheet.swift
│   │   ├── ContributorInviteSheet.swift, ContributorHomeView.swift
│   │   ├── SettingsView.swift, ChangeCredentialsView.swift, UpdateScheduleView.swift
│   │   ├── PairingView.swift, QRScannerView.swift, LogViewerView.swift, AboutView.swift
│   │   ├── Components/, Models/
│   │   └── Info.plist, PrivacyInfo.xcprivacy
│   ├── PicFrame.xcodeproj/             # Used on the Mac
│   └── iosApp.xcodeproj/               # Used by CodeMagic (kept in sync)
├── codemagic.yaml                      # CI: IPA builds
└── api-tests/koofr_upload.py           # Python CLI upload tool (legacy)
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

The full, current list of every route (the `/api/v1` API for the apps and the dashboard's LAN-only endpoints), with auth, requests and responses, is in **[API.md](API.md)**. In short:

| Area | Prefix | Auth |
|------|--------|------|
| Health, version | `/health`, `/version` | None (public) |
| Pairing | `/api/v1/pair` | Pairing or invite code |
| Manager app | `/api/v1/*` (status, devices, services, system, display, folders, photos, tools, contributors, cloud, settings, logs, updates) | JWT, admin |
| Share app | `/api/v1/contributor/*` | JWT, admin or contributor |
| Token refresh, self-unpair | `/api/v1/auth/refresh`, `DELETE /api/v1/devices/me` | JWT, any role |
| Dashboard | `/`, `/dashboard/*`, `/api/*` (not `/api/v1`), `/sync`, `/system/reboot`, ... | None; LAN and tailnet only |

---

## Configuration

### Config Files

WanderWall uses two configuration files:

| File | Purpose |
|------|---------|
| `~/.wanderwall/config.yaml` | Frame settings (frame name, sync interval, current album, updates, demo) |
| `~/picframe_data/config/configuration.yaml` | Pi3D PictureFrame settings (rotation interval, display options) |

Other data in `~/.wanderwall/`:

| File | Purpose |
|------|---------|
| `sources.yaml` | Albums (below) |
| `devices.json` | Paired phones |
| `invites.json` | Contributor invites |
| `jwt_secret` | Token signing key (mode 600) |
| `frame_albums.yaml` | This frame's album registry: every album it has had (active/deleted), mirrored to Koofr `.picframe/frames/<pi-serial>.yaml` for Recover Albums (PL-147) |
| `thumbs/` | Thumbnail cache |
| `logs/` | `wanderwall.log`, `security.log` |

Backups are in `~/Pictures/backups/` (album: `<id>_<ts>.tar.gz`; whole frame: `frame_<name>_<ts>.tar.gz`, PL-164).

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

*The original build plan, kept for history. All phases are built; open work is tracked in the parking lot (`wanderwall_app/docs/PARKING_LOT.md`).*

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

**Status: built.** Both apps (Manager and Share) are built by CodeMagic as IPAs; App Store submission is tracked in the parking lot runbook.

- ✅ Update FrameClient for Funnel URLs and `/api/v1` prefix
- ✅ Update PairedFrame model with baseURL
- ✅ Build in Xcode, fix compile errors
- ✅ Test on simulator against live Pi API
- ✅ Fix runtime issues (multiple rounds)
- ✅ QR scanner for pairing
- ✅ WanderWall Share (contributor) app
- ⬜ TestFlight / App Store (parking lot runbook)

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

### New Pi Setup

The current, step-by-step setup (Pi OS, Pi3D, rclone, Tailscale + Funnel, `scripts/install.sh`, verification) is **[PI_SETUP.md](PI_SETUP.md)**. A v4 frame moves to v5 by reinstalling with `install.sh --from-v4` (also in PI_SETUP.md). Frames are updated with `scripts/update_app.sh`.

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
| Page loads | `GET /` returns 200 with all five tabs (there is one page) |
| Status display | `/dashboard/status` shows correct counts and service status |
| Album switching | Activate shows the album and syncs it |
| Album delete | Deletes the photos on the frame, keeps the cloud folder; refused for the showing album |
| Settings save | Settings form saves config correctly |
| Pairing QR | Mobile App Pairing generates a valid code and QR |
| Device list | Paired Devices lists and revokes devices |
| Logs display | Logs card shows recent entries |
| Backups and Recover | Album and whole-frame backup, restore (skips photos already there), Recover Albums |
| Service restart | Restart buttons trigger the right service restart |

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

*Historical: how this repo was first created from the planning chat. Not needed any more.*

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
- ✅ Contributors: invite code → WanderWall Share app, which uploads through the frame (`/api/v1/contributor/upload`)
- ✅ Config format: YAML (not bash)

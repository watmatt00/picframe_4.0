# Codebase Structure

## Directory Layout

```
picframe_4.0/
├── src/                        # Application source code (Python package)
│   ├── main.py                 # CLI entry point — runs uvicorn on 0.0.0.0:8000
│   ├── api/                    # FastAPI application and API routes
│   │   ├── app.py              # FastAPI app factory, router registration, lifespan
│   │   ├── dependencies.py     # Auth dependencies: get_current_device, require_admin, require_contributor
│   │   ├── middleware.py       # LANOnlyDashboardMiddleware (blocks dashboard for non-LAN/non-VPN)
│   │   └── routes/             # One file per API resource (all under /api/v1 prefix)
│   │       ├── cloud.py        # Koofr/rclone cloud operations
│   │       ├── contributor.py  # Single-contributor actions
│   │       ├── contributors.py # Contributor list management
│   │       ├── devices.py      # Paired device listing and revocation
│   │       ├── display.py      # Pi3D display control (source switch, advance, current image)
│   │       ├── folders.py      # rclone folder browser for source creation
│   │       ├── logs.py         # Log retrieval
│   │       ├── pairing.py      # Device pairing flow (QR code, code exchange, JWT issue)
│   │       ├── photos.py       # Photo file operations
│   │       ├── services.py     # systemd service status and control
│   │       ├── settings.py     # Frame/sync settings read and write
│   │       ├── status.py       # Frame status (traffic light, photo counts, sync info)
│   │       └── tools.py        # Photo tools (filename cleaner, duplicate finder, etc.)
│   ├── auth/                   # Authentication layer
│   │   ├── jwt_handler.py      # JWT create/verify, TokenClaims model
│   │   ├── models.py           # Device, PairingRequest, PairingResponse, QRCodeData
│   │   └── pairing.py          # Pairing code generation and validation
│   ├── config/                 # Configuration management
│   │   ├── manager.py          # config_manager singleton — typed get/set on config.yaml
│   │   ├── schema.py           # Pydantic validation schemas for config data
│   │   └── settings.py         # Settings (lru_cache), get_settings(), reload_settings()
│   ├── dashboard/              # Web dashboard (LAN-only, no auth)
│   │   ├── routes.py           # All dashboard routes (Jinja2 server-rendered)
│   │   ├── static/
│   │   │   ├── css/dashboard.css
│   │   │   └── js/dashboard.js
│   │   └── templates/
│   │       └── dashboard.html  # Single-page four-tab dashboard template
│   ├── services/               # Business logic layer
│   │   ├── backup_service.py   # tar.gz backup creation, listing, deletion
│   │   ├── display_service.py  # Pi3D HTTP API control (source switch, advance frame)
│   │   ├── photo_tools_service.py  # Filename cleaner, duplicate finder, video manager, rename
│   │   ├── source_manager.py   # PhotoSource CRUD, sources.yaml I/O, auto rclone config
│   │   ├── status_service.py   # Traffic-light logic, photo counts, sync status, disk capacity
│   │   ├── sync_service.py     # rclone sync execution (POST /sync handler)
│   │   ├── systemd_service.py  # systemctl --user wrappers, sync timer management
│   │   └── update_service.py   # git-based update check/apply, scheduled update task
│   ├── storage/                # Persistent file-backed storage
│   │   ├── devices.py          # DeviceStorage — devices.json with FileLock
│   │   ├── invites.py          # Invite/contributor token storage
│   │   └── sources.py          # Thin wrapper delegating to source_manager
│   └── utils/                  # Shared utilities
│       ├── logging.py          # setup_logging() — ops + security log handlers
│       ├── qr_generator.py     # QR code PNG generation (base64 data URL)
│       └── rclone.py           # rclone subprocess helpers (count, list remotes, validate)
├── config/
│   └── config.example.yaml     # Annotated example — copy to ~/.picframe/config.yaml
├── docs/                       # Project documentation
│   ├── API.md                  # REST API reference (keep in sync with mobile repo)
│   ├── PARKING_LOT.md          # Known deferred issues
│   ├── PHASE_4_5_PLAN.md       # Roadmap — always check for next steps
│   ├── PI3D_INTEGRATION.md     # Pi3D HTTP API and display integration notes
│   ├── PI_SETUP.md             # Phase 6 first-run and WiFi recovery guide
│   ├── SCREEN_MAP.md           # Dashboard UI screen inventory
│   ├── SECURITY.md             # Security design
│   ├── SPECIFICATION.md        # Full API and system specification
│   ├── TEST_PLAN.md            # Manual test plan (backend + iOS)
│   └── test_runs/              # Per-run test result logs
├── scripts/
│   ├── install.sh              # Basic install helper
│   ├── setup_tailscale.sh      # Tailscale Funnel setup
│   └── setup/                  # Phase 6 first-run and WiFi recovery scripts
│       ├── install_setup.sh    # Main install script (run as sudo from project root)
│       ├── state_manager.py    # /var/lib/picframe/state.yaml read/write
│       ├── watchdog.py         # WiFi watchdog — triggers AP or BLE setup
│       ├── ble_setup.py        # BLE WiFi credential exchange
│       ├── picframe-config     # Shell config helper (sourced by setup scripts)
│       ├── ap_portal/          # Captive portal for WiFi/frame-name entry
│       │   ├── portal.py       # Flask portal app
│       │   ├── static/portal.css
│       │   └── templates/      # index, reconfigure, skip, success HTML
│       └── systemd/            # Phase 6 system service units
│           ├── picframe-ap-setup.service
│           ├── picframe-ble-setup.service
│           └── picframe-watchdog.service
├── systemd/                    # User service units (deployed to ~/.config/systemd/user/)
│   ├── picframe-api.service    # FastAPI server
│   ├── picframe-sync.service   # One-shot rclone sync (called by timer)
│   └── picframe-sync.timer     # Periodic sync timer
├── tests/
│   ├── integration/
│   │   ├── test_api.py
│   │   ├── test_dashboard.py
│   │   └── test_pairing.py
│   └── unit/
│       ├── test_auth.py
│       ├── test_config.py
│       └── test_sync.py
├── .planning/codebase/         # Project planning documents
├── pyproject.toml              # Build config, deps, entry points, ruff/pytest config
├── requirements.txt            # Pinned deps for Pi deployment
├── CLAUDE.md                   # Project-level instructions for Claude
└── README.md
```

## Module Boundaries

### `src/api/` — Transport Layer
Owns HTTP concerns only: routing, request parsing, response serialization, auth enforcement. Route handlers should be thin — validate input, call a service, return the result. No business logic lives here.

- `app.py` assembles the FastAPI instance: registers all routers, mounts static files, and starts the update scheduler background task via lifespan.
- `middleware.py` enforces the LAN/VPN-only restriction on dashboard paths before any route handler runs.
- `dependencies.py` provides the two auth dependency chains used by routes: `get_current_device` (JWT verify + revocation check + last_seen update) and `require_admin` / `require_contributor`.

### `src/auth/` — Authentication
JWT lifecycle and device pairing protocol. `jwt_handler.py` creates and verifies tokens; `pairing.py` generates/validates short-lived 6-char codes; `models.py` defines the Pydantic types shared by pairing routes and storage.

### `src/config/` — Configuration
Two separate concerns that should not be conflated:

- `settings.py` — read-only, `lru_cache`-backed `get_settings()`. After any write, call `reload_settings()` to bust the cache.
- `manager.py` — `config_manager` singleton for typed set/get on `~/.picframe/config.yaml`. The sole writer of that file from application code.
- `schema.py` — Pydantic validators for config values passed in via API (prevents illegal values from reaching disk).

### `src/dashboard/` — Web Dashboard
Server-rendered single-page interface served at `/`. No auth. Jinja2 templates + vanilla JS. All dashboard HTML logic lives in `routes.py`; the template (`dashboard.html`) drives four tabs. Dashboard routes are NOT under `/api/v1` — they are registered directly on the app with no prefix.

### `src/services/` — Business Logic
All side-effectful operations: subprocess calls to rclone and systemctl, Pi3D HTTP API calls, git operations, file system manipulation. Route handlers call into services; services do not import from `src/api/`.

Key services:
- `source_manager.py` — the authoritative source of truth for photo sources (CRUD, `sources.yaml`).
- `status_service.py` — computes the traffic-light status, photo counts, and sync state used by both the dashboard and the `/api/v1/status` endpoint.
- `display_service.py` — wraps the Pi3D HTTP API at `http://localhost:9000/`; falls back to config+restart if unreachable.
- `update_service.py` — git-based update checker/applier; runs on a background asyncio task started at lifespan.
- `sync_service.py` — executes rclone sync for the active source.
- `systemd_service.py` — `systemctl --user` wrappers for all four user services.

### `src/storage/` — Persistence
File-backed stores for data that must survive restarts:
- `devices.py` — `DeviceStorage` class, `~/.picframe/devices.json`, `FileLock` for concurrency safety, atomic write (temp → rename), `chmod 600`.
- `invites.py` — contributor invite tokens.
- `sources.py` — thin shim delegating to `source_manager`; exists for import-path compatibility.

### `src/utils/` — Cross-Cutting Utilities
No domain logic. Used freely by any layer: logging setup, QR generation, rclone subprocess primitives.

### `scripts/setup/` — Phase 6 First-Run
Standalone scripts invoked by systemd system services (root-level). Not imported by the FastAPI application. The `state_manager.py` in this directory reads/writes `/var/lib/picframe/state.yaml` which the API also reads to determine first-run state.

## Entry Points

| Entry Point | File | How It Is Used |
|---|---|---|
| `picframe-api` (CLI) | `src/main.py:main` | Installed via `pyproject.toml [project.scripts]`; called by `picframe-api.service` |
| `uvicorn src.api.app:app` | `src/api/app.py` | Direct uvicorn invocation (dev or manual) |
| `picframe-cli` | `src/cli.py` | Management CLI (separate entry point) |
| `scripts/setup/install_setup.sh` | shell | Phase 6 install; run once as `sudo bash` from project root |
| `scripts/setup/watchdog.py` | python | Launched by `picframe-watchdog.service` (system service) |
| `scripts/setup/ble_setup.py` | python | Launched by `picframe-ble-setup.service` (system service) |
| `scripts/setup/ap_portal/portal.py` | python | Launched by `picframe-ap-setup.service` (system service) |

## Route Prefix Map

| Prefix | Auth | Purpose |
|---|---|---|
| `/` (root) | None | Dashboard (LAN/VPN only via middleware) |
| `/static/` | None | Dashboard static assets |
| `/health` | None | Health check (mobile + monitoring) |
| `/version` | None | Version info |
| `/api/v1/` | JWT Bearer | All mobile app endpoints |
| `/debug/token` | None | Dev-only token generator — remove before production |

## Config Files

| File | Location | Owner | Format | Purpose |
|---|---|---|---|---|
| `config.yaml` | `~/.picframe/config.yaml` | `config_manager` / `settings.py` | YAML | Frame identity, display, sync interval, logging, update schedule |
| `sources.yaml` | `~/.picframe/sources.yaml` | `source_manager` | YAML | Photo source definitions (id, name, local_path, rclone_remote, enabled) |
| `devices.json` | `~/.picframe/devices.json` | `DeviceStorage` | JSON | Paired mobile devices (id, name, role, paired_at, last_seen) |
| `configuration.yaml` | `~/picframe_data/config/configuration.yaml` | Pi3D / API (rotation interval write) | YAML | Pi3D display config — rotation interval, pic_dir, transitions |
| `state.yaml` | `/var/lib/picframe/state.yaml` | `state_manager.py` (Phase 6 scripts) | YAML | First-run state: provisioned, koofr_configured, needs_setup, frame_name |
| `install.conf` | `/var/lib/picframe/install.conf` | `install_setup.sh` | key=value | Frame user, home dir, project path — written once at install |
| `config.example.yaml` | `config/config.example.yaml` | repo | YAML | Annotated template for `config.yaml` |

## Key Data Flows

### API Request (mobile app)
```
Mobile ──HTTPS──> Tailscale Funnel ──> uvicorn
  ──> LANOnlyDashboardMiddleware (pass-through for /api)
  ──> Route handler
  ──> get_current_device() [JWT verify → device_storage revocation check → last_seen update]
  ──> Service call
  ──> Response
```

### Dashboard Request (LAN browser)
```
Browser ──HTTP──> uvicorn
  ──> LANOnlyDashboardMiddleware [IP check: LAN or 100.x passes, public IP blocked]
  ──> dashboard/routes.py
  ──> Service/config calls
  ──> Jinja2 render ──> HTML response
```

### Settings Write Pattern
```
Route handler or dashboard route
  ──> config_manager.set("section.key", value)        # writes config.yaml
  ──> reload_settings()                                # busts lru_cache
  ──> get_settings()                                   # fresh read on next call
```

### Source Switch (seamless)
```
Dashboard or API route
  ──> display_service.switch_source(source_id)
      ──> GET http://localhost:9000/?subdirectory=<rel>  # Pi3D HTTP API (seamless fade)
      ──> fallback: config_manager.set + systemctl restart picframe
  ──> config_manager.set("display.current_source", source_id)
  ──> reload_settings()
```

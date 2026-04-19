# Technology Stack

_Last updated: 2026-04-19_

## Summary

PicFrame 4.0 is a pure-Python backend application targeting Raspberry Pi (ARM Linux). It uses FastAPI served by Uvicorn as the HTTP layer, Pydantic v2 for data validation and settings, and PyYAML for all configuration files. The frontend is server-rendered Jinja2 HTML with vanilla JS and CSS — no build step, no bundler. Python 3.11 is the declared minimum; 3.12 is installed on the development machine. All dependencies are managed via `pyproject.toml` with `hatchling` as the build backend.

## Languages

**Primary:**
- Python 3.11+ (`pyproject.toml` `requires-python = ">=3.11"`) — all backend logic, API, services
- Python 3.12.3 — installed on the dev machine (`fuckms`)

**Secondary:**
- HTML/Jinja2 — server-rendered dashboard at `src/dashboard/templates/dashboard.html`
- JavaScript (vanilla) — dashboard interactivity at `src/dashboard/static/js/dashboard.js`
- CSS — dashboard styling at `src/dashboard/static/css/dashboard.css`
- Bash — install/setup scripts in `scripts/` and `scripts/setup/`

## Runtime

**Environment:**
- CPython 3.11+ (Raspberry Pi OS / Debian Bookworm ARM64)
- Runs as a systemd user service (`~/.config/systemd/user/picframe-api.service`)
- Service unit: `systemd/picframe-api.service`

**Package Manager:**
- pip via `pyproject.toml` / `hatchling`
- Virtualenv: `~/picframe_4.0/venv/` on each Pi (referenced in service unit)
- Lockfile: `requirements.txt` present (generated from `pyproject.toml`) — not a pinned lockfile

## Frameworks

**Core:**
- FastAPI `>=0.109.0` (installed: 0.135.1) — REST API + dashboard HTTP layer; defined in `src/api/app.py`
- Uvicorn `>=0.27.0` (with `[standard]` extras: uvloop, httptools, watchfiles) — ASGI server
- Jinja2 `>=3.1.0` (installed: 3.1.6) — server-side template rendering for dashboard (`src/dashboard/routes.py`)
- Starlette — included transitively via FastAPI; `BaseHTTPMiddleware` used in `src/api/middleware.py`

**Data / Config:**
- Pydantic `>=2.5.0` — all API models, service models, config schemas
- pydantic-settings `>=2.1.0` — `Settings` class with YAML + env var loading (`src/config/settings.py`)
- PyYAML `>=6.0.1` — reads/writes `~/.picframe/config.yaml`, `~/picframe_data/config/configuration.yaml`, `~/.picframe/sources.yaml`

**Auth:**
- PyJWT `>=2.8.0` (installed: 2.12.1) — HS256 JWT tokens for mobile API; secret at `~/.picframe/jwt_secret` (600 perms)

**Testing:**
- pytest `>=7.4.0` (installed: 9.0.2) — test runner
- pytest-asyncio `>=0.23.0` (installed: 1.3.0) — async test support (`asyncio_mode = "auto"`)
- httpx `>=0.26.0` (installed: 0.28.1) — async HTTP client used in tests and dashboard routes

**Build/Dev:**
- hatchling — build backend (`pyproject.toml`)
- ruff `>=0.1.0` — linter + formatter (line-length 100, target py311, rules E/F/I/N/W/UP)

## Key Dependencies

**Critical:**
- `fastapi>=0.109.0` — the entire API and dashboard serve through this
- `pyjwt>=2.8.0` — mobile app authentication; without it, all `/api/v1` routes fail
- `pyyaml>=6.0.1` — configuration persistence; all settings read/written as YAML
- `pydantic>=2.5.0` — all data models; Pydantic v2 syntax throughout
- `paho-mqtt>=2.0.0` (installed: 2.1.0) — imported for Pi3D MQTT control; **currently stubbed** (mqtt_client is always `None` in `display_service.py`)

**Infrastructure:**
- `uvicorn[standard]>=0.27.0` — ASGI server; `uvloop` + `httptools` for performance on Pi
- `aiofiles>=23.0.0` — async file I/O
- `filelock>=3.13.0` — file locking for race condition prevention
- `python-multipart>=0.0.6` — form data parsing (FastAPI file/form uploads)
- `httpx>=0.26.0` — async HTTP client; used in `src/dashboard/routes.py` for Koofr credential validation
- `Pillow>=10.0.0` (installed: 12.1.1) — image thumbnails, PIL instruction images for Phase 6 first-run
- `pillow-heif>=0.13` — HEIC/HEIF image support
- `qrcode[pil]>=7.4.2` (installed: 8.2) — QR code generation for device pairing (`src/utils/qr_generator.py`)

## Configuration

**Environment:**
- Primary config: `~/.picframe/config.yaml` — frame identity, display, sync, tailscale, logging, updates settings
- Pi3D config: `~/picframe_data/config/configuration.yaml` — rotation interval, pic_dir, subdirectory
- Sources config: `~/.picframe/sources.yaml` — photo source definitions
- Phase 6 state: `/var/lib/picframe/state.yaml` — provisioning state
- Environment variable prefix: `PICFRAME_` with `__` as nested delimiter (e.g. `PICFRAME_FRAME__NAME`)
- JWT secret: `~/.picframe/jwt_secret` (600 permissions, auto-generated on first run)
- Settings are `@lru_cache`'d; call `reload_settings()` after any `config_manager.set()` call

**Build:**
- `pyproject.toml` — single source of truth for deps, entry points, ruff config, pytest config
- Entry points: `picframe-api` → `src.main:main`, `picframe-cli` → `src.cli:main`

## Platform Requirements

**Development:**
- Python 3.11+
- rclone installed and configured with at least one remote
- Tailscale installed (optional for dashboard IP detection)
- git (required for update check/apply features)

**Production (Raspberry Pi):**
- Raspberry Pi OS (Debian Bookworm ARM64) — Pi3D requires GPU access
- Pi3D PictureFrame running as `picframe.service` (separate systemd user service)
- Pi3D HTTP control API on `localhost:9000`
- systemd user services: `picframe-api`, `picframe-sync`, `picframe-sync.timer`, `picframe`
- Phase 6 system services (root): `picframe-watchdog`, `picframe-ble-setup`, `picframe-ap-setup`
- rclone configured with Koofr remote (set up via dashboard or Phase 6 first-run flow)
- Tailscale installed for Funnel (mobile app remote access) and VPN peer dashboard access

---

_Stack analysis: 2026-04-19_

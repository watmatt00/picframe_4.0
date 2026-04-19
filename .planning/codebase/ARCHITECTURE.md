# Architecture

_Last updated: 2026-04-19_

## Summary

PicFrame 4.0 is a FastAPI application running on a Raspberry Pi that serves two distinct client surfaces from a single process on port 8000: a LAN-restricted web dashboard (Jinja2 server-rendered HTML) and a JWT-authenticated REST API consumed by the iOS mobile app over Tailscale Funnel. The backend controls a Pi3D GPU-accelerated slideshow display via Pi3D's built-in HTTP API on port 9000, syncs photos from cloud storage (Koofr) via rclone, and manages configuration through YAML files with file-locked atomic writes. All services are singleton module-level instances that share in-process state.

---

## Pattern Overview

**Overall:** Single-process monolith with two client surfaces (web dashboard + mobile API), service layer singletons, and file-based persistence.

**Key Characteristics:**
- No database — all persistence is YAML and JSON files in `~/.picframe/`
- Singleton service instances (`sync_service`, `display_service`, `source_manager`, `device_storage`) share in-process state
- Two parallel route namespaces: `/` (dashboard, LAN-only) and `/api/v1/` (JWT-authenticated, mobile)
- `lru_cache` on `get_settings()` — must call `reload_settings()` after any config write
- `asyncio.create_subprocess_exec()` for all external process calls (rclone, git, systemctl)

---

## Layers

**Entry Point:**
- Purpose: Start uvicorn server
- Location: `src/main.py`
- Contains: `main()` function calling uvicorn; reads settings and sets up logging first

**Application Assembly:**
- Purpose: Wire FastAPI app, register routes, add middleware, mount static files, start background tasks
- Location: `src/api/app.py`
- Contains: `FastAPI` instance, lifespan (starts update scheduler), route inclusion, static file mount
- Depends on: All route modules, middleware, dashboard routes

**API Routes (mobile):**
- Purpose: JWT-authenticated endpoints for iOS mobile app
- Location: `src/api/routes/` — 13 route modules
- Prefix: `/api/v1/`
- Auth: `Depends(get_current_device)` or `Depends(require_admin)` from `src/api/dependencies.py`
- Key routes: `pairing`, `status`, `devices`, `services`, `display`, `folders`, `contributors`, `cloud`, `settings`, `logs`, `photos`, `tools`, `contributor`

**Dashboard Routes (web):**
- Purpose: Server-rendered HTML pages for LAN management
- Location: `src/dashboard/routes.py`
- Prefix: none (root-level)
- Auth: None — protected by `LANOnlyDashboardMiddleware` at IP level
- Contains: All dashboard tab logic (status, source switching, tools, settings, pairing QR, log viewer, update management)
- Depends on: All service modules, config manager, storage layers

**Middleware:**
- Purpose: Restrict dashboard paths to LAN/Tailscale IPs; block public internet (Funnel) from dashboard
- Location: `src/api/middleware.py`
- Mechanism: Checks `X-Forwarded-For` then `request.client.host` against RFC 1918 prefixes + `100.x.x.x` (Tailscale CGNAT)
- Protected paths: `/`, `/settings`, `/devices`, `/pairing`, `/logs`, `/static/`

**Auth Layer:**
- Purpose: JWT token lifecycle and pairing code management
- Location: `src/auth/`
  - `jwt_handler.py` — create/verify HS256 tokens; secret stored at `~/.picframe/jwt_secret` (mode 600)
  - `pairing.py` — in-memory 6-char pairing codes (5-min TTL, 3 attempts max, 3/hour rate limit)
  - `models.py` — Pydantic models: `Device`, `PairingRequest`, `PairingResponse`, `QRCodeData`
- Used by: `src/api/dependencies.py` (per-request token validation), `src/dashboard/routes.py` (QR generation)

**Dependencies (per-request auth):**
- Purpose: FastAPI `Depends()` callables for route protection
- Location: `src/api/dependencies.py`
- Functions: `get_current_device()` — verifies JWT then checks device still exists in storage (blocks revoked devices on every request); `require_admin()`, `require_contributor()`

**Config Layer:**
- Purpose: Settings access and file-based config management
- Location: `src/config/`
  - `settings.py` — `Settings` Pydantic model loaded from `~/.picframe/config.yaml`; `get_settings()` with `@lru_cache`; `reload_settings()` clears cache
  - `manager.py` — `ConfigManager` with `FileLock` for atomic YAML writes; `config_manager` singleton targets `~/.picframe/config.yaml`
  - `schema.py` — input validation schemas (path traversal checks, rclone flag blocklist)

**Service Layer:**
- Purpose: Business logic for display control, photo sync, source management, status aggregation, system updates
- Location: `src/services/`
  - `display_service.py` — controls Pi3D via HTTP API (port 9000) with config-file + service-restart fallback; `display_service` singleton
  - `sync_service.py` — wraps rclone for cloud-to-local sync; tracks `_is_syncing`, `_last_sync`; `sync_service` singleton
  - `source_manager.py` — CRUD for photo sources in `~/.picframe/sources.yaml`; auto-configures Koofr rclone remote on create; `source_manager` singleton
  - `status_service.py` — shared status logic (source resolution, photo counting, sync status, disk usage) used by both API and dashboard routes
  - `systemd_service.py` — async wrappers around `systemctl --user` for service start/stop/restart/status
  - `update_service.py` — git-based update checks (`git rev-list --count`), background scheduler, `apply_update()` (git pull + service restart)
  - `photo_tools_service.py` — filename cleaning, duplicate detection, video file management
  - `backup_service.py` — tar.gz photo backups to `~/Pictures/backups/`

**Storage Layer:**
- Purpose: Persistent data storage (file-backed, no database)
- Location: `src/storage/`
  - `devices.py` — `DeviceStorage` singleton; paired devices in `~/.picframe/devices.json`; `FileLock` for concurrency; atomic write via temp file + rename; mode 600
  - `sources.py` — thin wrapper delegating to `source_manager`
  - `invites.py` — contributor invite management

**Utilities:**
- Location: `src/utils/`
  - `rclone.py` — async rclone wrappers (`rclone_sync`, `rclone_count`, `rclone_list_remotes`, `count_local_files`); all use `asyncio.create_subprocess_exec()`
  - `logging.py` — dual-file rotating log setup (ops log + security log) in `~/.picframe/logs/`
  - `qr_generator.py` — QR code generation for pairing flow

---

## Data Flow

**Mobile App Pairing Flow:**
1. Dashboard generates 6-char code via `generate_pairing_code()` (in-memory, 5-min TTL) and renders QR
2. QR encodes JSON: `{url: funnel_url, code: "ABC-XYZ", name: frame_name}` via `QRCodeData`
3. iOS app scans QR, POSTs `{code, device_name}` to `POST /api/v1/pairing/pair`
4. Backend calls `verify_pairing_code()` (single-use, invalidates immediately)
5. Creates `Device` record in `~/.picframe/devices.json` via `device_storage.add_device()`
6. Issues JWT token (HS256, 365-day expiry) containing `device_id`, `device_name`, `role`, `frame_id`
7. All subsequent API calls include `Authorization: Bearer <token>`; `get_current_device()` validates JWT + checks device not revoked in storage on every request

**Photo Display (Source Switch) Flow:**
1. User selects source in dashboard or iOS app → `POST /api/v1/display/switch` or dashboard form POST
2. `display_service.switch_folder(source_path)` called
3. Pi3D config (`~/picframe_data/config/configuration.yaml`) updated for persistence across reboots
4. If path is inside `~/Pictures`: send `GET http://localhost:9000/?subdirectory=<rel>` to Pi3D HTTP API — seamless fade, no restart
5. If outside `~/Pictures` or HTTP API unreachable: restart `picframe` systemd user service via `systemctl --user restart picframe`
6. Settings `display.current_source` updated in `~/.picframe/config.yaml` via `config_manager.set()`; `reload_settings()` called to clear `lru_cache`

**Photo Sync Flow:**
1. `picframe-sync.timer` fires → `picframe-sync.service` → `POST /sync` on the API
2. `sync_service.sync_source()` resolves active source, runs `rclone sync <remote> <local_path>`
3. `sync_service._is_syncing` flag set during operation (prevents concurrent syncs)
4. Result stored in `sync_service._last_sync` (in-memory only — lost on restart)
5. Dashboard and API read sync status from `status_service.determine_sync_status()`

**Dashboard Status Refresh Flow:**
1. Dashboard page auto-refreshes every 15 seconds via AJAX to `/dashboard/status`
2. `status_service.get_current_source()` reads `settings.display.current_source` → resolves `PhotoSource`
3. `get_photo_counts()` counts local files synchronously + counts remote via `rclone_count()` (15-second timeout)
4. Traffic light: green = match, amber = mismatch, red = error/no photos

---

## Key Abstractions

**PhotoSource:**
- Purpose: Represents one named photo collection with a local path and optional rclone remote
- Definition: `src/services/source_manager.py` — `PhotoSource(id, name, local_path, rclone_remote, enabled)`
- Storage: `~/.picframe/sources.yaml`
- Pattern: Loaded fresh from disk on every read (no in-memory cache)

**Settings (lru_cache):**
- Purpose: Unified config access with performance caching
- Definition: `src/config/settings.py` — `get_settings()` returns `@lru_cache`-wrapped `Settings`
- Critical rule: Always call `reload_settings()` after any `config_manager.set()` call to avoid stale cache
- Config file: `~/.picframe/config.yaml`

**TokenClaims:**
- Purpose: Typed JWT payload carried through authenticated requests
- Definition: `src/auth/jwt_handler.py` — `TokenClaims(device_id, device_name, role, frame_id, iat, exp)`
- Usage: Returned by `get_current_device()` dependency; used in route handlers for device context

**Device:**
- Purpose: Persistent record of a paired mobile device
- Definition: `src/auth/models.py` — `Device(id, name, role, paired_at, last_seen)`
- Storage: `~/.picframe/devices.json` (FileLock, atomic writes, mode 600)
- Revocation: Removing the `Device` record immediately blocks that device's token on the next request (token itself is still cryptographically valid until expiry)

---

## Entry Points

**API Server:**
- Location: `src/main.py` → `src/api/app.py`
- Invocation: `uvicorn src.api.app:app --host 0.0.0.0 --port 8000`
- Service: `~/.config/systemd/user/picframe-api.service`

**Sync Trigger:**
- Location: `src/api/routes/` (POST /sync endpoint in cloud.py or services.py)
- Invocation: systemd timer → `picframe-sync.service` → HTTP POST to self
- Service: `~/.config/systemd/user/picframe-sync.service`

**Phase 6 Setup Scripts:**
- Location: `scripts/setup/install_setup.sh` (run as sudo)
- Invocation: `sudo bash scripts/setup/install_setup.sh` from project root

---

## Authentication Model

**Two-tier access control:**

| Surface | Auth Method | Who Can Access |
|---------|-------------|----------------|
| Web Dashboard (`/`, `/settings`, etc.) | IP allowlist via middleware | LAN (192.168.x, 10.x, 172.16-31.x) + Tailscale VPN peers (100.x) |
| Mobile API (`/api/v1/`) | JWT Bearer token | Any IP (designed for Tailscale Funnel / public internet) |

**Roles:**
- `admin` — full access to all API routes
- `contributor` — limited access (photo upload, contributor-scoped operations)

**Token revocation:** HS256 tokens cannot be cryptographically revoked. Revocation works by removing the `Device` record from `devices.json` — `get_current_device()` checks storage after every successful JWT decode, returning 401 immediately if the device is gone. The last admin device cannot be removed.

---

## Error Handling

**Strategy:** Explicit exception handling at service boundaries; HTTP exceptions raised in route handlers; no bare `except:` clauses.

**Patterns:**
- External process failures (rclone, git, systemctl): caught at utility layer; logged with details; service methods return `False`/`None`/`SyncResult(success=False)`
- Config file errors: return empty dict/defaults; log error
- JWT validation failures: return `None` from `verify_token()`; `get_current_device()` raises `HTTPException 401`
- Pi3D HTTP API unreachable: logged as warning; falls back to service restart
- rclone timeout (15s for count operations): caught with `asyncio.wait_for`; remote count returned as 0

---

## Cross-Cutting Concerns

**Logging:**
- Setup: `src/utils/logging.py` — dual rotating file handlers
- Ops log: `~/.picframe/logs/picframe.log` (configurable retention, default 7 days)
- Security log: `~/.picframe/logs/security.log` (90-day retention)
- All modules use `logging.getLogger(__name__)`

**Validation:**
- Input schemas in `src/config/schema.py` (Pydantic validators with path traversal checks, rclone flag blocklist)
- Source IDs: `^[a-z0-9_-]+$` pattern enforced at schema level
- External commands: never `shell=True` with user input; all args passed as lists to `asyncio.create_subprocess_exec()`

**Configuration:**
- `~/.picframe/config.yaml` — app settings (frame identity, display, sync, logging, updates)
- `~/.picframe/sources.yaml` — photo source definitions
- `~/picframe_data/config/configuration.yaml` — Pi3D display config (pic_dir, time_delay, subdirectory)
- `/var/lib/picframe/state.yaml` — Phase 6 provisioning state

**Known Issue:**
- `revoke_token()` in `src/auth/jwt_handler.py` is a stub (returns False, TODO comment). True revocation relies entirely on device record removal from `devices.json`.
- `remote_count` in `SyncStatusInfo` is hardcoded to 0 in the API route (tracked in `docs/PARKING_LOT.md`).
- Debug token endpoint `GET /debug/token` in `src/api/app.py` is marked "REMOVE IN PRODUCTION" but is still present.

---

## Gaps / Unknowns

- MQTT integration referenced in `display_service.py` (`send_mqtt_command`) is stubbed — no MQTT client is wired up; `_mqtt` is always `None`
- `src/storage/invites.py` content not read — contributor invite flow details unknown
- Phase 6 BLE setup flow (`scripts/setup/ble_setup.py`, `scripts/setup/watchdog.py`) not analyzed in depth
- Spotlight feature (`~/Pictures/spotlight/`) referenced in `CLAUDE.md` but not traced in source
- `contributor.py` vs `contributors.py` route distinction not fully analyzed

# PicFrame 4.0 — External Integrations

## Overview

PicFrame 4.0 integrates with six external systems:

1. **Koofr / rclone** — cloud photo synchronization
2. **Pi3D PictureFrame** — GPU-accelerated display, controlled over HTTP and config file
3. **Tailscale** — VPN mesh for dashboard access and Funnel for mobile app
4. **GitHub (git)** — update checks and deployment
5. **systemd** — service lifecycle management
6. **JWT / pairing** — mobile device authentication

---

## 1. Koofr / rclone

### How it works

All cloud photo sync goes through rclone. There is no Koofr SDK — rclone is the only interface. The backend wraps rclone with `asyncio.create_subprocess_exec()` (never `shell=True`).

### Key file

`src/utils/rclone.py`

### Operations

| Function | rclone command | Purpose |
|---|---|---|
| `rclone_sync(source, dest)` | `rclone sync` | Sync remote folder → local dir |
| `rclone_count(remote)` | `rclone size --json` | Count files on remote (returns `.count`) |
| `rclone_check(remote)` | `rclone lsd --max-depth 0` | Test if remote is reachable |
| `rclone_list_remotes()` | `rclone listremotes` | List configured rclone remotes |
| `rclone_copyto(local_file, remote_dest)` | `rclone copyto` | Upload a single file to remote |
| `rclone_deletefile(remote, filename)` | `rclone deletefile` | Delete a single file from remote |
| `rclone_movefile(remote, old, new)` | `rclone moveto` | Rename a file on remote |

Variants `rclone_deletefile_raw` and `rclone_movefile_raw` accept filenames with special characters (discovered from local filesystem, never from user input).

### Input validation

All remote specs are validated by `_validate_remote()` before use:
- Local paths: must start with `/`, no `..`
- Remote specs: must be `name:path` where name matches `[a-zA-Z0-9_-]+`
- Filenames: no path separators, no traversal, image extension required (strict); or path-traversal-only check (raw variant)
- rclone flags: blacklist filters dangerous flags like `--config`, `--delete-*`

### Sync flow

`POST /sync` (dashboard) or the systemd timer calling `POST /sync` triggers `sync_service.sync_source()`, which calls `rclone_sync(rclone_remote, str(local_path))` with `--stats-one-line -v` flags. The stat line is parsed for transferred file count.

`status_service.py` calls `rclone_count()` with a 15-second timeout when serving the dashboard status endpoint. Cloud count is cached in the dashboard's 15-second auto-refresh cycle.

### rclone config

rclone is configured externally (via `rclone config` or the Koofr setup step in Phase 6). The API reads configured remote names via `rclone_list_remotes()` when the user browses for a source. The remote name is typically `koofr` and the folder path is appended with `:` (e.g. `koofr:KFR_kframe`).

### Source model

Photo sources are stored in `~/.picframe/sources.yaml` (managed by `src/services/source_manager.py`). Each source has:
- `id` — unique slug
- `name` — display name
- `rclone_remote` — rclone remote spec (e.g. `koofr:KFR_kframe`) or `None` for local-only
- `local_path` — local directory (under `~/Pictures/` by convention)
- `enabled` — bool

---

## 2. Pi3D PictureFrame HTTP API

### Overview

Pi3D is the GPU-accelerated slideshow process (`picframe.service`). It exposes an HTTP control server on `localhost:9000`. The backend uses this API to switch photo directories and change settings without restarting the service.

### Key file

`src/services/display_service.py`

### HTTP control endpoint

```
GET http://localhost:9000/?<key>=<value>
```

Values are URL-encoded. Requests are made via `urllib.request.urlopen()` wrapped in `asyncio.get_event_loop().run_in_executor()` with a 3-second timeout.

### Supported control keys

| Key | Type | Effect |
|---|---|---|
| `subdirectory` | string | Switch to subdirectory of `pic_dir` (seamless fade, no restart) |
| `paused` | `"true"` / `"false"` | Pause / resume slideshow |
| `time_delay` | float string | Seconds between images |

### Source-switching strategy

`display_service.switch_folder(source_path)` uses a two-path strategy:

1. **If `source_path` is inside `~/Pictures`**: compute relative subdirectory, send `GET /?subdirectory=<rel>` to Pi3D HTTP API. Seamless fade, no restart.
2. **If HTTP API fails or path is outside `~/Pictures`**: fall back to updating `~/picframe_data/config/configuration.yaml` and restarting `picframe.service` via systemd.

In both cases the YAML config is always updated first for persistence across reboots.

### Pi3D config file

Path: `~/picframe_data/config/configuration.yaml`

The backend reads and writes the `model` section:
- `model.pic_dir` — base pictures directory
- `model.subdirectory` — subdirectory within `pic_dir`
- `model.time_delay` — rotation interval in seconds

Changes to `time_delay` (rotation interval) go through `display_service.set_delay()` which calls the HTTP API, and also update the YAML directly. After YAML changes the picframe service is restarted.

### MQTT (stub)

`display_service.send_mqtt_command()` is implemented but MQTT client is not yet wired up. Methods like `set_shuffle()` and `previous_image()` route through MQTT stubs that log but do not transmit.

---

## 3. Tailscale

### Roles

| Role | Mechanism | Purpose |
|---|---|---|
| Dashboard access (VPN peers) | Direct WireGuard connection | LAN users + tailnet peers access dashboard |
| Mobile app (Funnel) | Tailscale Funnel HTTPS | Public HTTPS endpoint for iOS app |

### Dashboard access control

`src/api/middleware.py` — `LANOnlyDashboardMiddleware`

Dashboard paths (`/`, `/settings`, `/devices`, `/pairing`, `/logs`, `/static/`) are restricted to:
- RFC 1918 private ranges: `192.168.*`, `10.*`, `172.16-31.*`
- Loopback: `127.*`
- Tailscale CGNAT range: `100.*` (direct VPN peer connections)

Funnel traffic is blocked: Funnel proxies public requests and sets `X-Forwarded-For` to the real public IP, which fails the `100.*` check. The middleware reads `X-Forwarded-For` first, then falls back to `request.client.host`.

### Funnel URL

Stored in `~/.picframe/config.yaml` as `frame.funnel_url`. Displayed in the Settings tab and encoded in the pairing QR code. The mobile app uses this URL as its `baseURL` for all API calls.

### Pairing QR code

`QRCodeData` encodes `{"url": "<funnel_url>", "code": "<pairing_code>", "name": "<frame_name>"}` as JSON, then the QR code generator (`src/utils/qr_generator.py`) renders it as an image for the dashboard.

---

## 4. GitHub / Git — Update Checks

### Key file

`src/services/update_service.py`

### Mechanism

The update service does not call the GitHub API. It uses local git operations on the repo at `~/picframe_4.0`:

1. `git fetch --quiet` (30-second timeout)
2. `git rev-parse --short HEAD` → local commit hash
3. `git rev-parse --short @{u}` → upstream (remote tracking) commit hash
4. `git rev-list --count HEAD` and `@{u}` → commit counts for friendly version strings (e.g. `4.0.52`)

Hashes are compared: `local == remote` → up to date; otherwise update available.

### Version format

`4.0.<commit_count>` where count comes from `git rev-list --count`. The dashboard shows this as the version number.

### Background scheduler

`start_update_scheduler()` is launched as an asyncio task on app startup (via FastAPI lifespan). It reads schedule config from `settings.updates` each iteration, sleeps until the next scheduled time, then runs `check_for_updates()`.

Schedule config (`~/.picframe/config.yaml` under `updates`):
- `auto_check` — bool, default `True`
- `frequency` — `"daily"` | `"weekly"` | `"monthly"`, default `"monthly"`
- `day` — day of month (1–28) or day of week (0–6, Mon=0)
- `check_time` — `"HH:MM"` 24-hour
- `auto_apply` — bool, default `False`; if true, auto-runs `git pull` on update available

Results are saved to `settings.updates.last_checked`, `last_result`, `available_commit` via `config_manager.set()` followed by `reload_settings()`.

### Applying updates

`apply_update()` runs `git pull` (60-second timeout) in `~/picframe_4.0`. After a successful pull the dashboard triggers an API self-restart (via `POST /api/v1/services/picframe-api/restart`) and auto-reloads the page 8 seconds later.

---

## 5. systemd Services

### Key file

`src/services/systemd_service.py`

### Service whitelist

Only these services can be controlled by the API:
- `picframe` — Pi3D display service
- `picframe-api` — the FastAPI backend itself

All `systemctl` calls use `--user` flag (user-level services, not system).

### Operations

| Method | Command |
|---|---|
| `get_status(name)` | `systemctl --user is-active`, `is-enabled` |
| `restart(name)` | `systemctl --user restart <name>.service` |
| `start(name)` | `systemctl --user start <name>.service` |
| `stop(name)` | `systemctl --user stop <name>.service` |

### Sync timer

`update_sync_timer(interval_seconds)` rewrites `~/.config/systemd/user/picframe-sync.timer` with a new `OnCalendar` expression, then runs `daemon-reload` + `restart picframe-sync.timer`. Valid intervals (seconds): 0 (disabled), 300, 600, 900, 1800, 2700, 3600, 7200, 21600, 43200, 86400. Timer is written atomically (write to `.timer.tmp`, then rename).

### Phase 6 system services (run as root, not user)

These are controlled outside the API by install scripts:
- `picframe-watchdog` — WiFi monitor
- `picframe-ble-setup` — BLE WiFi setup
- `picframe-ap-setup` — AP hotspot + captive portal

---

## 6. Authentication — JWT + Pairing

### JWT tokens

**Key file:** `src/auth/jwt_handler.py`

Algorithm: HS256. Secret: 256-bit random hex stored at `~/.picframe/jwt_secret` with mode `0o600`, auto-generated on first use.

Token claims:
- `device_id` — UUID string
- `device_name` — human-readable string
- `role` — `"admin"` or `"contributor"`
- `frame_id` — frame identifier
- `iat`, `exp` — issued/expiry timestamps

Default expiry: 365 days.

### Revocation

Token revocation is enforced at request time via `get_current_device()` in `src/api/dependencies.py`. After verifying the JWT signature, the dependency checks `device_storage.get_device(claims.device_id)`. If the device is not in `~/.picframe/devices.json`, a 401 is returned immediately. Removing a device from storage is the revocation mechanism — there is no token blacklist.

### Device storage

**Key file:** `src/storage/devices.py`

Devices are persisted in `~/.picframe/devices.json` (mode `0o600`, atomic write via temp file + rename, protected by `filelock.FileLock`). The last admin device cannot be removed. `update_last_seen()` is called on every authenticated request.

### Pairing flow

**Key file:** `src/auth/pairing.py`

1. Dashboard generates a 6-character code (format `ABC-XYZ`, 36^6 combinations) via `generate_pairing_code()`. Rate limit: 3 codes per hour.
2. Code expires in 5 minutes. Max 3 failed attempts before invalidation. Single use (deleted on success).
3. Mobile app scans QR code, extracts `{url, code, name}`, POSTs `{code, device_name}` to `POST /api/v1/pairing/pair`.
4. On success: a `Device` is stored, a JWT token is returned in `PairingResponse`.

### Dashboard (no auth)

Dashboard routes are served without JWT. Access is controlled purely by network: `LANOnlyDashboardMiddleware` enforces LAN + Tailscale VPN only (see Tailscale section). Dashboard endpoints call service layer directly, bypassing `get_current_device()`.

---

## 7. Logging

### Key file

`src/utils/logging.py`

### Two log files

| File | Logger | Retention | Contents |
|---|---|---|---|
| `~/.picframe/logs/picframe.log` | root logger | 7 days | All operations (sync, display, errors, debug) |
| `~/.picframe/logs/security.log` | `logging.getLogger("security")` | 90 days | Auth events only; `propagate=False` prevents duplication |

Both use `TimedRotatingFileHandler` rotating at midnight. Log directory is mode `0o700`.

### Format

```
YYYY-MM-DD HH:MM:SS LEVEL [logger_name] message
```

### Security events

`log_auth_event(event_type, success, details, ip)` writes structured lines to the security logger:
```
PAIR_ATTEMPT_SUCCESS ip=1.2.3.4 device_id=abc123
```

### Log API

`GET /api/v1/logs` returns recent log lines for the dashboard log viewer. Ops and security logs are toggled separately in the UI. Auto-refresh is configurable.

---

## 8. Deployment / Branch Integration

### Branch policy

| Branch | Tracks | Consumers |
|---|---|---|
| `dev` | Active development | tkframe (test) |
| `main` | Tagged, stable | kframe, mnbframe (production) |

### Pi update mechanism

Frames pull updates via `git pull` in `~/picframe_4.0`. The API's `apply_update()` endpoint triggers this on demand. Automatic scheduled checks (`auto_check`) run via the background scheduler. Frames never push.

### Version display

The dashboard Updates card shows the friendly version (`4.0.X` from commit count), active branch, and a DEV/MAIN badge. It compares `local_version` vs `remote_version` from `check_for_updates()`.

### Promotion gate

Tag format: `v4.0.X`. A tag on `dev` is required before merging to `main`. Merging `dev → main` requires explicit user authorization (never done automatically).

---

## Integration Dependency Map

```
Mobile App (iOS)
  └─> Tailscale Funnel (HTTPS :443)
        └─> FastAPI /api/v1/* (JWT required)
              ├─> rclone (Koofr sync)
              ├─> Pi3D HTTP API (localhost:9000)
              ├─> systemd --user (picframe, picframe-api)
              └─> git (update checks + pull)

Web Dashboard (LAN / Tailscale VPN)
  └─> LANOnlyMiddleware (100.x.x.x + RFC1918 allowed)
        └─> FastAPI /dashboard/* (no auth)
              ├─> rclone (status, sync)
              ├─> Pi3D HTTP API
              ├─> systemd --user
              └─> git
```

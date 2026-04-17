# PicFrame 4.0 - Project Context

## Overview

PicFrame 4.0 is a Raspberry Pi picture frame management system:
- **FastAPI backend** with JWT authentication (port 8000)
- **Web dashboard** for LAN-based management (no auth, Jinja2 + vanilla JS)
- **Mobile app** via Tailscale Funnel (separate repo: `picframe_mgr`)
- **Pi3D PictureFrame** integration for GPU-accelerated display
- **rclone sync** for cloud photo synchronization

## Architecture

```
Mobile App ──(Tailscale Funnel)──> Pi API (JWT) ──> Pi3D Display
Web Dashboard ──(LAN or Tailscale VPN)──> Pi API (no auth) ──> Pi3D Display
Cloud (Koofr) ──────────────────────────> rclone sync ──> local photos
```

## Device Connection Info

| Device | IP (LAN) | IP (VPN) | Dashboard URL | User | Branch | Notes |
|--------|----------|----------|---------------|------|--------|-------|
| **tkframe** | 192.168.102.210 | 100.83.164.79 | `http://tkframe.whale-ayu.ts.net:8000` | matt | `dev` | Test frame — tracks dev branch |
| **kframe** | 192.168.102.200 | 100.69.17.26 | `http://kframe.whale-ayu.ts.net:8000` | pi | `main` | Home frame (production) |
| **mnbframe** | 192.168.1.154 | 100.125.51.92 | `http://mnbframe.whale-ayu.ts.net:8000` | pi | `main` | Remote only (production) |
| **fuckms** | 192.168.102.100 | 100.82.140.119 | — | matt | — | Main PC (dev) |

Dashboard URLs require Tailscale connected (MagicDNS on tailnet `whale-ayu.ts.net`). LAN IPs also work directly on port 8000.

Pi frames are **pull-only** from GitHub. All dev/push happens on PC.

## Key File Locations (on Pi)

| File | Purpose |
|------|---------|
| `~/picframe_data/config/configuration.yaml` | Pi3D display config (rotation interval, pic_dir, etc.) |
| `~/.picframe/config.yaml` | Dashboard config (frame name, sync interval, current source) |
| `~/.picframe/sources.yaml` | Photo source definitions |
| `~/.picframe/logs/picframe.log` | Operations log |
| `~/.picframe/logs/security.log` | Auth/security log |
| `~/.local/share/systemd/timers/stamp-picframe-sync.timer` | Last sync timestamp |
| `~/.config/systemd/user/picframe-api.service` | API service unit |
| `~/.config/systemd/user/picframe-sync.service` | Sync service unit (calls POST /sync) |
| `~/.config/systemd/user/picframe-sync.timer` | Sync timer unit |
| `~/.config/systemd/user/picframe.service` | Pi3D display service unit |
| `/var/lib/picframe/state.yaml` | Phase 6 state (provisioned, koofr_configured, needs_setup, frame_name) |
| `/var/lib/picframe/install.conf` | Written by install_setup.sh — frame user, home dir, project path |
| `/etc/hostapd/picframe-hostapd.conf` | AP hotspot config (SSID, random password from Pi serial) |
| `~/picframe_data/data/no_pictures.jpg` | Shown by Pi3D when no photos exist; replaced with setup instruction image during first-run |
| `~/Pictures/spotlight/` | Persistent spotlight dir — Pi3D keeps it indexed; contents cleared after each spotlight |

## Deployment Workflow

### Branch Policy
- `dev` — all active development. tkframe tracks this.
- `main` — production. kframe and mnbframe track this. **Only receives tagged merges from `dev`.**
- Tag format: `v4.0.X` where X matches the commit count shown in the dashboard (e.g. `v4.0.52`).
- The dashboard Updates card shows each frame's active branch (DEV/MAIN badge).

### Dev Branch (daily work → tkframe)
1. Work on `dev` branch on PC
2. `git add && git commit && git push origin dev`
3. Pull on tkframe: `ssh matt@192.168.102.210 "cd ~/picframe_4.0 && git pull"`
4. Restart API: `ssh matt@192.168.102.210 "systemctl --user restart picframe-api"`
5. Test dashboard: `http://192.168.102.210:8000`

### Promoting dev → main (kframe, mnbframe)
1. Tag the commit: `git tag v4.0.X && git push origin v4.0.X`
2. Merge to main: `git checkout main && git merge dev && git push origin main`
3. Prod frames pull on next scheduled check, or manually:
   - kframe: `ssh pi@192.168.102.200 "cd ~/picframe_4.0 && git pull"`
   - mnbframe: `ssh pi@100.125.51.92 "cd ~/picframe_4.0 && git pull"`
4. Restart API on prod frames as needed
5. `git checkout dev` to return to dev work

### One-Time Branch Setup (tkframe)
```bash
ssh matt@192.168.102.210 "cd ~/picframe_4.0 && git fetch origin && git checkout dev"
```
kframe and mnbframe are already on `main` — no action needed.

User services (`systemctl --user`): `picframe-api`, `picframe-sync`, `picframe-sync.timer`, `picframe`

**Phase 6 system services** (run as root, `systemctl` without `--user`):
- `picframe-watchdog` — WiFi monitor, enabled at boot
- `picframe-ble-setup` — BLE WiFi setup, started on demand by watchdog
- `picframe-ap-setup` — AP hotspot + captive portal, started on demand by watchdog

## Dashboard Architecture

Single-page four-tab interface (`dashboard.html`). No standalone pages — all features are consolidated into tabs.

Tab order: **Frame Status | Switch Photos | Tools | Settings**

- **Frame Status Tab**: Traffic light (green/amber/red), photo counts (cloud + local), current image thumbnail, quick actions (Sync Now, Restart Frame, Restart API)
- **Switch Photos Tab**: Source table, add new source form with rclone folder browser, source switching
- **Tools Tab**: Source selector (shared by all cards), Filename Cleaner (spaces→underscores, long-name >20 chars renamed to YYYYMMDD_HHMMSS, Google ID tokens, numbered suffixes, ext case/wrong-ext), Duplicate Finder, Video File Manager, Rename File (scan all files → editable table → batch cloud-first rename, blank inputs, dup guardrails), Photo Backups (tar.gz to `~/Pictures/backups/`, list + delete)
- **Settings Tab**: Frame settings (name, rotation interval, sync interval, log level, read-only Frame ID + Funnel URL), Network sub-card (LAN IP + WiFi SSID, nested in Frame Settings), device pairing (QR code, manual code, countdown, Tailscale IP, instructions), manage devices (inline table with AJAX revoke via `GET /api/devices`), log viewer (expandable, ops/security toggle, line count, auto-refresh), software updates (check/apply, auto-check schedule, DEV/MAIN branch badge)

### Key Behaviors
- Rotation interval changes write to `~/picframe_data/config/configuration.yaml` (model.time_delay) and auto-restart picframe service
- Sync interval is stored in seconds but displayed as minutes in UI
- `POST /sync` syncs the **active display source** (falls back to first enabled source if active has no remote)
- Photo counts (cloud/local) reflect the active source only, not all sources combined
- Traffic light goes AMBER when cloud/local counts don't match
- Dashboard auto-refreshes every 15 seconds via AJAX to `/dashboard/status`
- Cloud photo count uses shared `rclone_count()` via `status_service.py` with 15-second timeout
- "Last restart" queries systemd `ActiveEnterTimestamp` (survives log rotation)
- **Source switching uses Pi3D's HTTP API** (`GET http://localhost:9000/?subdirectory=<rel>`) for seamless fade with no service restart; falls back to config + restart only when the HTTP API is unreachable or the path is outside `~/Pictures`
- **Revoked devices blocked on every request**: `get_current_device()` checks device storage after token validation — revoked tokens return 401 immediately
- Tools tab card headers are **clickable**: clicking the header expands/collapses the card; scan cards (Filename Cleaner, Duplicate Finder, Video Manager, Rename File) trigger a scan directly when clicked from collapsed state

## Mobile App Scope

**Android is permanently on hold. iOS only.** Do NOT suggest, plan, or reference Android work.

The iOS app has been built in Xcode and tested on simulator against live tkframe API. Core features verified working. See `docs/TEST_PLAN.md` for the comprehensive manual test plan covering both backend and iOS app.

## Cross-Repo Relationship

| Repo | Purpose | API Role |
|------|---------|----------|
| `picframe_4.0` (this) | Pi backend + dashboard | Defines API |
| `picframe_mgr` | Mobile app (iOS only) | Consumes API |

Known issues tracked in `docs/PARKING_LOT.md`.
Phase 4, 5 & 6 plan in `docs/PHASE_4_5_PLAN.md` - **always reference this for next steps**.
Test plan in `docs/TEST_PLAN.md` - covers backend, dashboard, and iOS app. Test runs stored in `docs/test_runs/`.
Phase 6 setup guide in `docs/PI_SETUP.md` — includes WiFi recovery usage guide and troubleshooting.

## Phase 6: First-Run & WiFi Recovery

Two-step first-run flow:
1. **Portal (Step 1):** Frame broadcasts `PicFrame-[name]` AP hotspot. User connects, enters WiFi SSID/password + frame name. Frame reboots.
2. **Dashboard banner (Step 2):** After WiFi connects, dashboard shows Koofr setup banner. User enters Koofr email + password (validated live). Once saved, normal operation begins.

While waiting for Step 2, Pi3D displays a PIL instruction image (`no_pictures.jpg`) with the dashboard URL. Image is restored to the original once Koofr is configured.

WiFi recovery (existing frame): same AP portal, Step 1 only (no frame name or Koofr — already configured).

Phase 6 install: `sudo bash scripts/setup/install_setup.sh` (run from project root as sudo).

When making API changes, update `docs/API.md` so mobile repo can reference it.

## Coding Standards

- Python: PEP 8, type hints, docstrings, no bare except
- Validate all user input (regex for IDs, paths, remote names)
- Never interpolate user input into shell commands
- Use `asyncio.create_subprocess_exec()` for external commands (rclone, systemctl)
- Use `systemctl --user` (not system-level) for all service operations

### Settings Cache Pattern

`get_settings()` uses `@lru_cache` for performance. After modifying config via `config_manager.set()`, you **must** call `reload_settings()` to clear the cache:

```python
from src.config.settings import get_settings, reload_settings

config_manager.set("display.current_source", source_id)
reload_settings()  # Required! Otherwise get_settings() returns stale data
```

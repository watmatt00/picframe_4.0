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
Web Dashboard ──(LAN only)──────> Pi API (no auth) ──> Pi3D Display
Cloud (Koofr) ──────────────────> rclone sync ──> local photos
```

## Device Connection Info

| Device | IP (LAN) | IP (VPN) | User | Notes |
|--------|----------|----------|------|-------|
| **tkframe** | 192.168.102.210 | 100.83.464.79 | matt | Test frame for 4.0 dev |
| **kframe** | 192.168.102.200 | 100.69.17.26 | pi | Home frame (production) |
| **mnbframe** | none | 100.125.51.92 | pi | Remote only |
| **fuckms** | 192.168.102.100 | 100.82.140.119 | matt | Main PC (dev) |

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

## Deployment Workflow

1. Make changes on PC in this repo
2. `git add && git commit && git push`
3. Pull on Pi: `ssh matt@192.168.102.210 "cd ~/picframe_4.0 && git pull"`
4. Restart API: `ssh matt@192.168.102.210 "systemctl --user restart picframe-api"`
5. Test dashboard: `http://192.168.102.210:8000`

All systemd services are **user services** (`systemctl --user`), not system services.

## Dashboard Architecture

Three-tab interface:
- **Status Tab**: Traffic light (green/amber/red), photo counts (cloud + local), current image thumbnail, quick actions (Sync Now, Restart Frame, Restart API), activity logs
- **Switch Photos Tab**: Source table, add new source form with rclone folder browser, source switching
- **Settings Tab**: Frame name, rotation interval (seconds), sync interval (minutes), log level, device pairing links

### Key Behaviors
- Rotation interval changes write to `~/picframe_data/config/configuration.yaml` (model.time_delay) and auto-restart picframe service
- Sync interval is stored in seconds but displayed as minutes in UI
- Traffic light goes AMBER when cloud/local counts don't match
- Dashboard auto-refreshes every 15 seconds via AJAX to `/dashboard/status`
- Cloud photo count uses `rclone ls` with 30-second timeout

## Mobile App Scope

**Android is permanently on hold. iOS only.** Do NOT suggest, plan, or reference Android work.

## Cross-Repo Relationship

| Repo | Purpose | API Role |
|------|---------|----------|
| `picframe_4.0` (this) | Pi backend + dashboard | Defines API |
| `picframe_mgr` | Mobile app (iOS only) | Consumes API |

Known issues tracked in `docs/PARKING_LOT.md`.

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

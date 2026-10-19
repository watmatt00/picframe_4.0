# PicFrame 4.0 - API Reference

## Base URL

- **Local (LAN)**: `http://<pi-ip>:8000`
- **Local (Tailscale VPN / MagicDNS)**: `http://<hostname>.whale-ayu.ts.net:8000` (dashboard + API, no JWT for dashboard)
- **Remote (mobile app)**: `https://<hostname>.whale-ayu.ts.net` (via Tailscale Funnel, JWT required)

## Authentication

Most endpoints require JWT authentication via Bearer token:

```
Authorization: Bearer <token>
```

Tokens are obtained through the pairing flow (see [Security](SECURITY.md)).

### Network Access

`LANOnlyMiddleware` (`src/api/middleware.py`) is deny-by-default. Callers outside the LAN and tailnet (RFC 1918, loopback, Tailscale `100.64.0.0/10`) can reach only `/api/v1/*`, `/health` and `/version`. Every other route, including the dashboard, `/docs` and `/api/updates/*`, returns `403` to them. The caller address is uvicorn's `request.client.host`, which is rewritten from `X-Forwarded-For` only when the TCP peer is `127.0.0.1` (the Tailscale Funnel/Serve proxy).

## Endpoints

### Public Endpoints (No Auth)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/version` | GET | API version |
| `/api/v1/pair` | POST | Exchange pairing code for JWT |

### Admin Endpoints (JWT Required, `/api/v1` prefix)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/pairing/generate` | POST | Generate new pairing QR code |
| `/api/v1/status` | GET | Frame status, capacity |
| `/api/v1/devices` | GET | List paired devices |
| `/api/v1/devices/{id}` | DELETE | Revoke device |
| `/api/v1/services` | GET | List services + status |
| `/api/v1/services/{name}/restart` | POST | Restart service |
| `/api/v1/system/reboot` | POST | Reboot the frame (202; back in about 1-2 minutes) |
| `/api/v1/display/folder` | GET | Current display folder |
| `/api/v1/display/folder` | POST | Switch folder |
| `/api/v1/display/spotlight` | POST | Spotlight a single photo for N seconds, then auto-restore |
| `/api/v1/display/spotlight` | DELETE | Cancel active spotlight immediately |
| `/api/v1/folders` | GET | List folders |
| `/api/v1/folders` | POST | Create folder |
| `/api/v1/folders/{id}` | DELETE | Delete an album and its photos on the frame (cloud folder kept) |
| `/api/v1/contributors` | GET | List contributor invites |
| `/api/v1/contributors/invite` | POST | Generate Koofr invite |
| `/api/v1/sync` | POST | Trigger manual sync |
| `/api/v1/logs` | GET | Recent log entries |
| `/api/v1/updates/settings` | GET | Update schedule, last check result, installed version |
| `/api/v1/updates/check` | POST | Check for available updates now |
| `/api/v1/updates/schedule` | POST | Save update schedule |
| `/api/v1/updates/apply` | POST | Apply update (git pull), then restart the API |
| `/api/v1/auth/refresh` | POST | Swap the caller's token for a new 90-day token (any paired role); the old one stops working 2 minutes later |
| `/api/v1/sleep-schedule` | POST | Update display sleep schedule (JWT required) |

---

## Endpoint Details

### GET /health

Health check endpoint.

**Response:**
```json
{"status": "ok"}
```

---

### GET /version

API version endpoint.

**Response:**
```json
{"version": "4.0.0", "api": "picframe"}
```

---

### POST /api/v1/pair

Exchange a pairing code for a JWT token.

**Request:**
```json
{
  "code": "A3B-X7K",
  "device_name": "Matt's iPhone"
}
```

**Response (200):**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "frame_id": "tkframe",
  "frame_name": "Test Frame",
  "role": "admin",
  "api_port": 8000
}
```

**Response (401):**
```json
{"detail": "Invalid or expired pairing code"}
```

**Demo codes (PL-015).** On a frame with `demo.allowed: true` and demo mode turned on (dashboard Settings → Demo Mode), two reusable codes also pair. They don't expire for 14 days, have no attempt or rate limits, and aren't used up:

| Code | `requested_role: "admin"` (Manager) | `requested_role: "contributor"` (Contributor) |
|------|------|------|
| Demo admin code | 200, `role: "admin"` | 200, `role: "contributor"` |
| Demo contributor code | 403 `"This is an invite code. Use the PicFrame Contributor app to pair with it."` | 200, `role: "contributor"` |
| Demo code after demo mode ended, or replaced by new codes | 401 `"This demo code has expired. Contact the frame owner for a new code."` | same |

Devices paired with a demo code are revoked when demo mode ends (turned off, or 14 days after it was turned on); their next call gets 401 `"Device has been revoked"`.

---

### POST /pairing/generate

Generate a new pairing code and QR code. Admin only.

**Headers:**
```
Authorization: Bearer <token>
```

**Response (200):**
```json
{
  "qr_code_base64": "iVBORw0KGgo...",
  "code": "A3B-X7K",
  "expires_at": "2026-02-02T18:00:00+00:00"
}
```

**Response (429):**
```json
{"detail": "Rate limit exceeded. Maximum 3 codes per hour."}
```

**Response (500):**
```json
{"detail": "Funnel URL not configured. Set frame.funnel_url in config."}
```

---

### GET /api/v1/status

Get frame status including sync state and capacity. Admin only.

**Headers:**
```
Authorization: Bearer <token>
```

**Response (200):**
```json
{
  "frame_id": "tkframe",
  "frame_name": "Test Frame",
  "current_source": "koofr_main",
  "photo_count": 1234,
  "services": [
    {
      "name": "picframe.service",
      "display_name": "PicFrame Display",
      "active": true,
      "status": "running",
      "can_restart": true
    },
    {
      "name": "picframe-api.service",
      "display_name": "PicFrame API",
      "active": true,
      "status": "running",
      "can_restart": true
    }
  ],
  "sync": {
    "last_sync": "2026-02-02T10:00:00+00:00",
    "status": "match",
    "local_count": 1234,
    "remote_count": 0,
    "is_syncing": false,
    "current_source": null
  },
  "capacity": {
    "total_gb": 64.0,
    "used_gb": 12.5,
    "available_gb": 51.5,
    "percent_used": 19.5,
    "total_bytes": 68719476736,
    "used_bytes": 13421772800,
    "free_bytes": 55297703936
  }
}
```

---

### GET /devices

List all paired devices. Admin only.

**Response (200):**
```json
{
  "devices": [
    {
      "id": "abc123",
      "name": "Matt's iPhone",
      "role": "admin",
      "paired_at": "2026-01-15T10:00:00+00:00",
      "last_seen": "2026-02-02T09:00:00+00:00"
    }
  ]
}
```

---

### POST /api/v1/system/reboot

Reboot the frame (PL-142). Admin only. The answer comes first; the reboot starts `delay_seconds` later. Poll `GET /health` until it answers again (about 1-2 minutes).

**Response (202):**
```json
{"rebooting": true, "message": "Rebooting. The frame will be back in about 1-2 minutes.", "delay_seconds": 3}
```

**Response (503):** the frame hasn't had `install_setup.sh` re-run since reboot was added (its polkit rule has no reboot permission):
```json
{"detail": "Reboot isn't set up on this frame yet. Run: sudo bash scripts/setup/install_setup.sh"}
```

---

### DELETE /api/v1/folders/{id}

Delete an album (PL-147). Admin only. Removes it from the album list and deletes its photos on the frame (`~/Pictures/<id>`). The cloud folder and backups in `~/Pictures/backups` are kept. The folder is only deleted if it is a direct child of `~/Pictures`, isn't `spotlight` or `backups`, and no other album uses it.

**Response (200):**
```json
{"deleted": "trip", "name": "Trip", "photos_removed": 42, "local_folder_removed": true, "cloud_folder": "koofr:KFR_trip", "error": null}
```
`error` is set (and `local_folder_removed` false) when the album was removed but its folder couldn't be deleted.

**Response (409):** the album is showing, or syncing:
```json
{"detail": "This album is showing on the frame. Show another album first, then delete it."}
```

**Response (404):** unknown album. Changed 2026-10-19: was `204` with no body, and kept the photos.

---

### DELETE /devices/{id}

Revoke a paired device. Admin only.

**Response (200):**
```json
{"status": "revoked", "device_id": "abc123"}
```

**Response (400):**
```json
{"detail": "Cannot revoke last admin device"}
```

---

### POST /services/{name}/restart

Restart a service. Admin only.

**Allowed services:** `picframe`, `picframe-api`

**Response (200):**
```json
{"status": "restarted", "service": "picframe"}
```

**Response (400):**
```json
{"detail": "Service 'foo' not in allowed list"}
```

---

### GET /display/folder

Get current display folder/source. Admin only.

**Response (200):**
```json
{
  "current_source": "koofr_main",
  "source_name": "Main Photos",
  "path": "/home/matt/Pictures/koofr_main"
}
```

---

### POST /display/folder

Switch display folder/source. Admin only.

**Request:**
```json
{"source_id": "google_drive"}
```

**Response (200):**
```json
{
  "status": "switched",
  "source_id": "google_drive",
  "source_name": "Google Drive"
}
```

---

### GET /api/v1/folders

List all configured photo sources with current source. Admin only.

**Response (200):**
```json
{
  "folders": [
    {
      "id": "koofr_main",
      "name": "Main Photos",
      "path": "/home/matt/Pictures/koofr_main",
      "photo_count": 150
    }
  ],
  "current_source": "koofr_main"
}
```

---

### POST /api/v1/display/spotlight

Display a single photo on the frame for a fixed duration, then automatically restore the previous source. Uses Pi3D's HTTP API for a seamless fade — no service restart.

**Headers:**
```
Authorization: Bearer <token>
```

**Request:**
```json
{
  "source_id": "koofr_main",
  "filename": "2025/vacation/photo.jpg",
  "duration_seconds": 30
}
```

- `duration_seconds`: 1–3600. Defaults to 30.
- `filename`: Relative path within the source's `local_path`.

**Response (200):**
```json
{
  "success": true,
  "filename": "2025/vacation/photo.jpg",
  "duration_seconds": 30,
  "message": "Displaying 'photo.jpg' for 30s, then restoring 'Main Photos'"
}
```

**Notes:**
- Copies the photo to `~/Pictures/spotlight/` (persistent dir Pi3D keeps indexed).
- Waits 2.5s for Pi3D to index the file, then switches via HTTP API.
- Waits 4.5s for fade transition to complete, then pauses Pi3D to freeze the photo.
- After `duration_seconds`, resumes Pi3D and restores the previous source.
- Starting a new spotlight while one is active cancels the previous one.

---

### DELETE /api/v1/display/spotlight

Cancel an active spotlight immediately and restore the normal display.

**Headers:**
```
Authorization: Bearer <token>
```

**Response (200):**
```json
{"cancelled": true}
```

Or, if no spotlight is active:
```json
{"cancelled": false, "message": "No active spotlight"}
```

---

### POST /sync

Trigger a manual sync (dashboard, no auth on LAN).

Syncs the **currently active display source**. If the active source has no remote configured, falls back to the first enabled source with a remote.

**Response (200):**
```json
{
  "status": "started",
  "source": "koofr_main"
}
```

---

## Error Responses

All errors follow this format:

```json
{"detail": "Error message here"}
```

| Status Code | Meaning |
|-------------|---------|
| 400 | Bad request (invalid input) |
| 401 | Unauthorized (missing or invalid token) |
| 403 | Forbidden (insufficient permissions) |
| 404 | Not found |
| 429 | Rate limit exceeded |
| 500 | Internal server error |

## Implementation Status

### Admin API Endpoints (JWT Required)

| Endpoint | Status |
|----------|--------|
| `/health` | ✅ Implemented |
| `/version` | ✅ Implemented |
| `/pair` | ✅ Implemented |
| `/pairing/generate` | ✅ Implemented |
| `/status` | ✅ Implemented |
| `/devices` | ✅ Implemented |
| `/devices/{id}` | ✅ Implemented |
| `/services` | ✅ Implemented |
| `/services/{name}/restart` | ✅ Implemented |
| `/display/folder` | ✅ Implemented |
| `/display/spotlight` | ✅ Implemented |
| `/display/spotlight` (DELETE) | ✅ Implemented |
| `/folders` | ✅ Implemented |
| `/contributors` | Stub only |
| `/sync` | ✅ Implemented |
| `/logs` | ✅ Implemented |
| `/sleep-schedule` | ✅ Implemented |

---

## Dashboard API Endpoints (LAN Only - No Auth)

The web dashboard at `http://<pi-ip>:8000` provides browser-based management accessible only from the LAN or tailnet (see [Network Access](#network-access)); other callers get `403`. These endpoints are used by the dashboard JavaScript.

### Dashboard Pages

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Dashboard home page (status overview) |
| `/settings` | GET | Settings page |
| `/devices` | GET | Device management page |
| `/pairing` | GET | Pairing QR code page |
| `/logs` | GET | Log viewer page |

### Dashboard API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/dashboard/status` | GET | Dashboard status JSON (sync state, counts, services) |
| `/current-image` | GET | Proxy current image from Pi3D (port 9000) |
| `/sync` | POST | Trigger manual sync |
| `/switch-source` | POST | Switch display source |
| `/services/{name}/restart` | POST | Restart service (picframe, picframe-api) |
| `/api/settings` | POST | Save frame settings |
| `/api/settings/log-level` | POST | Set log level |
| `/api/settings/sleep-schedule` | POST | Save display sleep schedule (on/off times, systemd timers) |
| `/api/settings/party` | POST | Enable or disable party mode |
| `/system/reboot` | POST | Reboot the frame (`{"ok": true}` or `{"ok": false, "error": ...}`) |
| `/api/albums/recoverable` | GET | Unused `KFR_*` cloud folders (with photo counts) and every backup, deleted albums' included |
| `/api/albums/recover-cloud` | POST | `{folder, name}`: re-add an album pointed at an unused cloud folder, then sync it |
| `/api/albums/restore-backup` | POST | `{filename, target_id \| new_name}`: add a backup's photos to an album and its cloud folder |
| `/api/albums/upload-archive` | POST | Raw body = .zip or .tar.gz (max 2 GB), query `target_id` or `new_name`: add its photos/videos to an album and its cloud folder |
| `/api/settings/demo` | POST | Turn demo mode on (`{"enabled": true}`, 14 days) or off (revokes demo devices). 403 unless `demo.allowed` |
| `/api/settings/demo/regenerate` | POST | New demo codes and a fresh 14 days; paired demo phones stay paired. 403 unless `demo.allowed` |
| `/dashboard/test-lights` | POST | Override indicator light state for manual testing |
| `/api/updates/settings` | GET | Get update check schedule settings |
| `/api/updates/check` | POST | Check for available updates |
| `/api/updates/schedule` | POST | Save auto-check schedule |
| `/api/updates/apply` | POST | Apply available update (git pull + update_app.sh, then restarts API) |

### Source Management API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/sources` | GET | List all photo sources |
| `/api/v1/sources/create` | POST | Create a new photo source |
| `/api/v1/sources/delete` | POST | Delete a photo source |
| `/api/v1/frame-live` | POST | Switch to source and trigger sync |

### rclone Integration API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/rclone/remotes` | GET | List configured rclone remotes |
| `/api/v1/rclone/list-dirs` | POST | Browse directories in rclone remote |
| `/api/v1/local/list-dirs` | GET | List directories in ~/Pictures |
| `/api/v1/config/test-remote` | POST | Test rclone remote connection |

### Other Dashboard Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/logs` | GET | Get recent log entries as JSON |
| `/pairing/generate` | POST | Generate new pairing code (AJAX) |
| `/devices/{id}/revoke` | POST | Revoke a paired device |

---

## Dashboard Status Response

**GET /dashboard/status**

Includes a `demo` object: `allowed`, `enabled`, `admin_code`, `contributor_code` (empty unless allowed), `expires_at`, `days_left`, `demo_devices`.

Returns real-time dashboard data for AJAX updates.

```json
{
  "sync_status": "idle|syncing|match|error",
  "local_count": 150,
  "remote_count": 150,
  "current_source": "Family Photos",
  "services": [
    {"name": "picframe", "active": true, "status": "running"},
    {"name": "picframe-api", "active": true, "status": "running"}
  ],
  "storage_used": 12.5,
  "storage_total": 64.0,
  "storage_percent": 19.5,
  "last_sync": "2026-02-04 10:30:00",
  "last_restart": "2026-02-04 08:00:00",  // from systemd ActiveEnterTimestamp
  "logs": ["2026-02-04 10:30:00 INFO Sync completed", "..."]
}
```

### Traffic Light Status Logic

The dashboard displays a traffic light indicator:
- **GREEN**: Sync status is "match" or "idle" AND cloud/local counts match
- **AMBER**: Cloud and local photo counts don't match (sync needed)
- **RED**: Sync error occurred
- **BLUE (animated)**: Sync currently in progress

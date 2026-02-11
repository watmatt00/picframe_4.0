# PicFrame 4.0 - API Reference

## Base URL

- **Local**: `http://<pi-ip>:8000`
- **Remote**: `https://<hostname>.<tailnet>.ts.net` (via Tailscale Funnel)

## Authentication

Most endpoints require JWT authentication via Bearer token:

```
Authorization: Bearer <token>
```

Tokens are obtained through the pairing flow (see [Security](SECURITY.md)).

## Endpoints

### Public Endpoints (No Auth)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/version` | GET | API version |
| `/api/pair` | POST | Exchange pairing code for JWT |

### Admin Endpoints (JWT Required, `/api` prefix)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/pairing/generate` | POST | Generate new pairing QR code |
| `/api/status` | GET | Frame status, capacity |
| `/api/devices` | GET | List paired devices |
| `/api/devices/{id}` | DELETE | Revoke device |
| `/api/services` | GET | List services + status |
| `/api/services/{name}/restart` | POST | Restart service |
| `/api/display/folder` | GET | Current display folder |
| `/api/display/folder` | POST | Switch folder |
| `/api/folders` | GET | List folders |
| `/api/folders` | POST | Create folder |
| `/api/contributors` | GET | List contributor invites |
| `/api/contributors/invite` | POST | Generate Koofr invite |
| `/api/sync` | POST | Trigger manual sync |
| `/api/logs` | GET | Recent log entries |

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

### POST /api/pair

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

### GET /api/status

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

### GET /api/folders

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
| `/folders` | ✅ Implemented |
| `/contributors` | Stub only |
| `/sync` | ✅ Implemented |
| `/logs` | ✅ Implemented |

---

## Dashboard API Endpoints (LAN Only - No Auth)

The web dashboard at `http://<pi-ip>:8000` provides browser-based management accessible only on the local network. These endpoints are used by the dashboard JavaScript.

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
| `/current-image` | GET | Proxy current image from Pi3D |
| `/sync` | POST | Trigger manual sync |
| `/switch-source` | POST | Switch display source |
| `/services/{name}/restart` | POST | Restart service (picframe, picframe-api) |
| `/api/settings` | POST | Save frame settings |

### Source Management API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/sources` | GET | List all photo sources |
| `/api/sources/create` | POST | Create a new photo source |
| `/api/sources/delete` | POST | Delete a photo source |
| `/api/frame-live` | POST | Switch to source and trigger sync |

### rclone Integration API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/rclone/remotes` | GET | List configured rclone remotes |
| `/api/rclone/list-dirs` | POST | Browse directories in rclone remote |
| `/api/local/list-dirs` | GET | List directories in ~/Pictures |
| `/api/config/test-remote` | POST | Test rclone remote connection |

### Other Dashboard Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/logs` | GET | Get recent log entries as JSON |
| `/pairing/generate` | POST | Generate new pairing code (AJAX) |
| `/devices/{id}/revoke` | POST | Revoke a paired device |

---

## Dashboard Status Response

**GET /dashboard/status**

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

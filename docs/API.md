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
| `/pair` | POST | Exchange pairing code for JWT |

### Admin Endpoints (JWT Required)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/pairing/generate` | POST | Generate new pairing QR code |
| `/status` | GET | Frame status, capacity |
| `/devices` | GET | List paired devices |
| `/devices/{id}` | DELETE | Revoke device |
| `/services` | GET | List services + status |
| `/services/{name}/restart` | POST | Restart service |
| `/display/folder` | GET | Current display folder |
| `/display/folder` | POST | Switch folder |
| `/folders` | GET | List folders |
| `/folders` | POST | Create folder |
| `/contributors` | GET | List contributor invites |
| `/contributors/invite` | POST | Generate Koofr invite |
| `/sync` | POST | Trigger manual sync |
| `/logs` | GET | Recent log entries |

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

### POST /pair

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
  "frame_name": "Test Frame"
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

### GET /status

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
  "sync_status": "MATCH",
  "local_count": 1234,
  "remote_count": 1234,
  "last_sync": "2026-02-02T10:00:00+00:00",
  "services": {
    "picframe": "running",
    "picframe-api": "running"
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

### POST /sync

Trigger a manual sync. Admin only.

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

| Endpoint | Status |
|----------|--------|
| `/health` | Implemented |
| `/version` | Implemented |
| `/pair` | Implemented |
| `/pairing/generate` | Implemented |
| `/status` | Stub only |
| `/devices` | Implemented |
| `/devices/{id}` | Stub only |
| `/services` | Stub only |
| `/services/{name}/restart` | Stub only |
| `/display/folder` | Stub only |
| `/folders` | Stub only |
| `/contributors` | Stub only |
| `/sync` | Not implemented |
| `/logs` | Not implemented |

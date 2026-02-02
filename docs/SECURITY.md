# PicFrame 4.0 - Security Model

## Overview

PicFrame 4.0 prioritizes security with:
- **JWT authentication** for all API access
- **Tailscale Funnel** for secure HTTPS-only remote access
- **Time-limited pairing codes** with rate limiting
- **Dual logging** with security event tracking

## Access Model

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

## Authentication Flow

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

## JWT Security

| Property | Value |
|----------|-------|
| **Algorithm** | HS256 |
| **Secret** | 256-bit random, unique per Pi |
| **Secret Location** | `~/.picframe/jwt_secret` (600 permissions) |
| **Expiry** | 1 year with refresh capability |
| **Claims** | `device_id`, `device_name`, `role`, `frame_id`, `iat`, `exp` |

### Roles

| Role | Permissions |
|------|-------------|
| **admin** | Full access - service restarts, folder switching, device management |
| **contributor** | Upload photos only via Koofr (no direct Pi access) |

## Pairing Code Security

| Property | Value |
|----------|-------|
| **Format** | 6 alphanumeric, case-insensitive (e.g., `A3B-X7K`) |
| **Keyspace** | 36^6 = 2.17 billion combinations |
| **Attempt limit** | 3 failures = code invalidated |
| **Expiry** | 5 minutes |
| **Rate limit** | 3 codes per hour |

## Logging

### Dual Log Strategy

| Log | Purpose | Location | Retention |
|-----|---------|----------|-----------|
| `picframe.log` | Operations (sync, display, errors) | `~/.picframe/logs/` | 7 days |
| `security.log` | Auth events, API access, failures | `~/.picframe/logs/` | 90 days |

### Security Log Events

```
PAIR_CODE_GENERATE_SUCCESS ip=100.64.1.5 admin=Matt's iPhone expires=2026-02-02T18:00:00
PAIR_ATTEMPT_SUCCESS ip=100.64.1.5 code=A3B*** device_name=New Device
PAIR_SUCCESS ip=100.64.1.5 device_id=abc123 device_name=New Device
PAIR_FAILURE ip=100.64.1.5 reason=invalid_or_expired_code
```

## Security Checklist

- [x] JWT secret: 256-bit random, unique per Pi, 600 permissions
- [x] Config files: 600 permissions, YAML (no code execution)
- [x] Pairing codes: cryptographically random, 3 attempts, 5-min expiry
- [ ] Last admin protection: cannot remove last admin
- [ ] SSH recovery: `picframe-cli emergency-reset` command
- [x] Input validation: Pydantic models for all inputs
- [ ] Path validation: No traversal in folder operations
- [ ] Rate limiting: Per-endpoint limits
- [ ] Service whitelist: Only allowed services can restart
- [x] Tailscale Funnel: HTTPS only, no direct port exposure
- [x] Security log: 90-day retention, 700 permissions on directory

## Network Security

### Tailscale Funnel

- All remote access goes through Tailscale Funnel
- HTTPS only (TLS termination at Tailscale edge)
- No direct port exposure to the internet
- Funnel URL format: `https://<hostname>.<tailnet>.ts.net`

### LAN Access

- Web dashboard accessible only on local network
- No authentication required for LAN access
- Assumes physical network security

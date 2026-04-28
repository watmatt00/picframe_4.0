# PicFrame 4.0 - Parking Lot

Future tasks and improvements tracked for later work.

**Note: Android is permanently on hold. iOS only. Do not create Android tasks.**

---

## Security Audit (2026-04-15)

Items identified during expert code audit. All confirmed real issues — no false positives included.

### Remove /debug/token endpoint
**Priority:** High  
**File:** `src/api/app.py:62-74`  
Delete the unauthenticated debug token endpoint. It's dead code never called anywhere. Tokens it mints are already rejected by the device-existence check in `src/api/dependencies.py:40`, but the endpoint should not exist.

### Remove dead revoke_token() stub from jwt_handler.py
**Priority:** Low  
**File:** `src/auth/jwt_handler.py:116-132`  
The function always returns `False` and is never called. Token revocation is handled by deleting the device record in device storage. Safe to delete with no impact.

### Fix fragile DASHBOARD_PATHS allowlist in middleware
**Priority:** High  
**File:** `src/api/middleware.py:12`  
The LAN-restriction only covers explicitly listed paths. The dashboard has ~35 routes, most not in the list (including `POST /sync`, `POST /services/{name}/restart`, `POST /api/updates/apply`). Fix: flip to a blocklist — deny non-LAN IPs from everything *except* `/api/v1/`, `/health`, and `/version`. New dashboard routes are then protected automatically.

### Remove X-Forwarded-For trust from LAN middleware
**Priority:** High  
**File:** `src/api/middleware.py:73-76`  
The middleware trusts the `X-Forwarded-For` header, allowing any Tailscale peer to spoof a LAN IP and bypass the dashboard restriction. The Pi runs without a reverse proxy, so this header should not be trusted. Remove it and use only `request.client.host`.

### Fix contributor upload memory risk
**Priority:** Medium  
**File:** `src/api/routes/contributor.py:114-115`  
The full file is read into RAM (`await file.read()`) before the 50 MB size check fires. A large upload exhausts memory before being rejected. Fix by streaming with a chunked read loop that aborts early once the limit is exceeded.

---

## Infrastructure

### Installer Script Distribution Strategy
**Priority:** Low  
**File:** `scripts/setup/install_picframe.sh`  
Repo is currently public to allow `curl | bash` from the Pi during fresh installs. Evaluate long-term options: keep public (simplest), move script to a public Gist (repo private again), use GitHub PAT (read-only token stored on Pi), or attach script as a public release asset. Decision should consider whether the repo ever needs to be private again and the maintenance burden of each approach.

---

## picframe_4.0 (Backend)

### Sync Interval - systemd Timer Integration
**Priority:** Low
**Status:** Partial

Sync interval is configurable in Settings (dashboard + mobile app) and stored in `config.yaml`. However, the systemd timer (`picframe-sync.timer`) still uses a fixed 15-minute interval. Future improvement: update the systemd timer when sync interval changes, or replace with an in-process scheduler.

Manual sync via "Sync Now" button does not reset the timer.

### ~~Open-Box Fresh Install - Cloud Storage Chicken-and-Egg Problem~~
**Status:** Done (Phase 6)

Two-step first-run flow: Step 1 (captive portal) collects WiFi + frame name → Step 2 (dashboard banner) collects Koofr credentials with live validation. Frame displays a PIL instruction image on the TV guiding the user to the dashboard URL. See Phase 6 in `docs/PHASE_4_5_PLAN.md`.

### ~~Generate OpenAPI Spec~~
**Status:** Done

FastAPI auto-generates OpenAPI spec at `/openapi.json` (48 paths, 23 versioned under `/api/v1/`). Interactive Swagger UI at `/docs`.

### ~~Add API Versioning (/api/v1/ prefix)~~
**Status:** Done

All JWT-authenticated mobile API routes use `/api/v1/` prefix. Dashboard LAN-only routes are unaffected. iOS app updated to use `/api/v1` base URL.

### ~~Consolidate Duplicated Status Logic~~
**Status:** Done

Extracted shared logic into `src/services/status_service.py`. Both API `status.py` and dashboard `routes.py` now use shared functions for source resolution, photo counting, sync status, and disk capacity.

---

## picframe_mgr (iOS Mobile App)

### ~~Build, Test, and Verify iOS App~~
**Status:** Done

iOS app has been built in Xcode, deployed to simulator, and tested against live tkframe API. Pairing, status, folder listing, source switching, uploads, and service restart all verified working.

### ~~Fix FoldersResponse Mismatch~~
**Status:** Done

Backend `GET /api/v1/folders` now returns wrapped response `{ folders: [...], current_source: "..." }` matching iOS expectations.

### ~~Fix Port Mismatch (5000 -> 8000)~~
**Status:** Done

Port is now configurable (stored in PairedFrame, defaults to 8000). Backend includes `api_port` in pairing response.

### ~~Fix iOS FrameStatus Model Mismatch~~
**Status:** Done

iOS `FrameStatus` model matches backend response. Backend `ServiceStatus` enriched with `display_name`, `can_restart`, and mobile-friendly status strings.

### ~~Revert Pairing Code Rate Limit~~
**Status:** Done — already at 3 per hour (`MAX_CODES_PER_HOUR = 3` in `src/auth/pairing.py`).

### ~~TestFlight Distribution~~
**Status:** Done

App Store Connect configured, signing/provisioning set up, archived and uploaded to TestFlight. Family added as beta testers.

---

## Phase 6: WiFi Recovery & Setup Mode

### ~~Console Setup Prompt~~
**Status:** Done

During setup mode, `/etc/issue` is replaced with WiFi setup instructions (SSID, password, portal URL). Shown above the login prompt so the terminal stays fully usable. Restored automatically on next normal boot via `_restore_issue()` in `watchdog.py`. Only appears when `needs_setup=true`.

### ~~BLE Service UUID / GATT Characteristic Spec~~
**Status:** Done — UUIDs finalized: Service `4fafc201-1fb5-459e-8fcc-c5c9c331914b`, Characteristic `beb5483e-36e1-4688-b7f5-ea07361b26a8`. Implemented in `ble_setup.py`.

### ~~AP Password — Random Per-Frame Password~~
**Status:** Done — `install_setup.sh` generates 8-char password from Pi serial number. Displayed in `/etc/issue` during setup mode.

### ~~First-Run Sync Failure UX~~
**Status:** Done — Koofr credentials validated live via rclone in the Step 2 dashboard banner before saving. Frame never proceeds with bad creds.

### Status Overlay
**Priority:** Low
**Status:** Deferred — implement after WiFi watchdog + setup mode core logic is working

Dots in upper right corner (12–16px), hidden during healthy operation. States: hidden / grey / yellow / red / orange+blue pulse / spinner. See Phase 6 in `docs/PHASE_4_5_PLAN.md`.

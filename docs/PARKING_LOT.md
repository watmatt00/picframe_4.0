# PicFrame 4.0 - Parking Lot

Future tasks and improvements tracked for later work.

**Note: Android is permanently on hold. iOS only. Do not create Android tasks.**

## picframe_4.0 (Backend)

### Sync Interval - systemd Timer Integration
**Priority:** Low
**Status:** Partial

Sync interval is configurable in Settings (dashboard + mobile app) and stored in `config.yaml`. However, the systemd timer (`picframe-sync.timer`) still uses a fixed 15-minute interval. Future improvement: update the systemd timer when sync interval changes, or replace with an in-process scheduler.

Manual sync via "Sync Now" button does not reset the timer.

### ~~Open-Box Fresh Install - Cloud Storage Chicken-and-Egg Problem~~
**Status:** Addressed in Phase 6

First-run flow is designed: setup mode (BLE + AP captive portal) collects WiFi + Koofr creds + frame name before provisioning. See Phase 6 in `docs/PHASE_4_5_PLAN.md`.

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

### Revert Pairing Code Rate Limit
**Priority:** Last step before prod
**Status:** Pending — do this immediately before promoting to production

The pairing code generation rate limit was increased from 3 to 50 codes per hour to allow rapid testing. Revert to 3 per hour before going to prod to prevent brute-force pairing attempts.

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

### AP Password — Random Per-Frame Password
**Priority:** Last step before prod
**Status:** Code ready in `install_setup.sh` — generates 8-char password from Pi serial number. Currently hardcoded to `"picframe"` for testing. Switch to random before final production test stage.

### ~~First-Run Sync Failure UX~~
**Status:** Resolved — portal validates Koofr credentials live (via temp rclone config) before accepting the form. Frame never reboots with bad creds.

### Status Overlay
**Priority:** Low
**Status:** Deferred — implement after WiFi watchdog + setup mode core logic is working

Dots in upper right corner (12–16px), hidden during healthy operation. States: hidden / grey / yellow / red / orange+blue pulse / spinner. See Phase 6 in `docs/PHASE_4_5_PLAN.md`.

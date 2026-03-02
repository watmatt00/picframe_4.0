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

### Revert Pi Rate Limit
**Priority:** Medium
**Status:** Pending (tabled until testing complete)

Pi rate limit was increased from 3 to 50 pairing codes per hour for testing. Revert to 3 when testing is complete.

### TestFlight Distribution
**Priority:** Medium
**Status:** Not started

Set up App Store Connect, configure signing/provisioning, archive and upload to TestFlight for family beta testing.

---

## Phase 6: WiFi Recovery & Setup Mode

### BLE Service UUID / GATT Characteristic Spec
**Priority:** High (blocks 6.2 implementation)
**Status:** Open question — finalize before implementing BLE setup service

### AP Password Strategy
**Priority:** Low
**Status:** Open question — hardcoded `"picframe"` or derived from Pi serial number?

### First-Run Sync Failure UX
**Priority:** Medium
**Status:** Open question — on bad Koofr creds during first sync: drop back to setup mode or show error screen?

### Status Overlay
**Priority:** Low
**Status:** Deferred — implement after WiFi watchdog + setup mode core logic is working

Dots in upper right corner (12–16px), hidden during healthy operation. States: hidden / grey / yellow / red / orange+blue pulse / spinner. See Phase 6 in `docs/PHASE_4_5_PLAN.md`.

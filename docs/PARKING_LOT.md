# PicFrame 4.0 - Parking Lot

Future tasks and improvements tracked for later work.

**Note: Android is permanently on hold. iOS only. Do not create Android tasks.**

## picframe_4.0 (Backend)

### Sync Interval Improvements
**Priority:** Medium
**Status:** Not started

Questions to resolve:
- Should sync run on a fixed 15-minute interval or be configurable?
- Does triggering a manual sync (via "Sync Now" button) reset the timer countdown?
- Should the settings UI offer preconfigured intervals (15 min, 30 min, 1 hour) or allow custom entry?

Current state: Sync interval is configurable in Settings tab (minutes). systemd timer triggers `/sync` endpoint. Manual sync via dashboard doesn't reset the timer.

### Generate OpenAPI Spec
**Priority:** Medium
**Status:** Not started

FastAPI has built-in OpenAPI generation. Export to `docs/openapi.json` so mobile app can reference it as the API contract. Optionally add CI check to detect unversioned changes.

### Add API Versioning (/api/v1/ prefix)
**Priority:** Medium
**Status:** Not started

Add version prefix to API routes (`/api/v1/`) to allow breaking changes without immediately breaking mobile clients. Return version in response headers.

Files: `src/api/app.py`, all route modules in `src/api/routes/`

### Consolidate Duplicated Status Logic
**Priority:** Low
**Status:** Not started

Status gathering code is duplicated between dashboard routes and API routes. Extract into a shared service function that both can call.

Files:
- `src/dashboard/routes.py` (get_dashboard_status, lines ~433-516)
- `src/api/routes/status.py` (lines ~95-153)

---

## picframe_mgr (Mobile App)

### ~~Fix Port Mismatch (5000 -> 8000)~~
**Priority:** High
**Status:** Done

Fixed: Port is now configurable (stored in PairedFrame, defaults to 8000). Backend includes `api_port` in pairing response. Also fixed missing `/api` prefix on all mobile API URLs.

### ~~Fix iOS FrameStatus Model Mismatch~~
**Priority:** High
**Status:** Done

Fixed: iOS and Kotlin `FrameStatus` models updated to match backend response. Backend `ServiceStatus` enriched with `display_name`, `can_restart`, and mobile-friendly status strings. `CapacityInfo` now includes byte-level fields for mobile.

### Fix FoldersResponse Mismatch
**Priority:** Medium
**Status:** Not started

Backend `GET /api/folders` returns `list[PhotoSourceResponse]` (flat list), but mobile expects `{ folders: [...], current_source: "..." }` (wrapped with current source). JSON decoding will fail for folder listing.

Files:
- `picframe_4.0/src/api/routes/folders.py`
- `picframe_mgr/iosApp/iosApp/Models/FrameStatus.swift` (FoldersResponse)
- `picframe_mgr/shared/.../models/frame/FrameStatus.kt` (FoldersResponse)

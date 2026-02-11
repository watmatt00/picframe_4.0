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

### Open-Box Fresh Install - Cloud Storage Chicken-and-Egg Problem
**Priority:** High (future planning)
**Status:** Needs design discussion

On a fresh "open box" install, there's a chicken-and-egg problem with cloud storage setup. The frame needs rclone/Koofr credentials configured before it can sync, but the mobile app now pulls those credentials from the frame. What comes first?

Questions to resolve:
- Does the user set up Koofr on the Pi first (via dashboard), then pair the mobile app?
- Or should the mobile app be able to push Koofr credentials TO the frame?
- Could the pairing flow include a "configure cloud storage" step?
- What's the minimal setup path for a non-technical user?

This requires significant thought and planning around the first-run experience.

### Consolidate Duplicated Status Logic
**Priority:** Low
**Status:** Not started

Status gathering code is duplicated between dashboard routes and API routes. Extract into a shared service function that both can call.

Files:
- `src/dashboard/routes.py` (get_dashboard_status, lines ~433-516)
- `src/api/routes/status.py` (lines ~95-153)

---

## picframe_mgr (iOS Mobile App)

### Build, Test, and Verify iOS App on Real Device
**Priority:** HIGH
**Status:** Not started

The entire iOS app has been written on a PC without ever being compiled or run. It has NEVER been built in Xcode or tested on a device/simulator. This must happen before any other mobile work.

**Prerequisites:**
- Access to Mac with Xcode installed
- Apple Developer account (for device testing / TestFlight)

**Steps:**
1. Open `picframe_mgr` project in Xcode on Mac
2. Build and fix any compile errors
3. Run on simulator - verify all screens load
4. Test against live tkframe API (192.168.102.210:8000):
   - Pairing flow (QR code scan)
   - Status display (verify FrameStatus model works)
   - Folder listing (known FoldersResponse mismatch - see below)
   - Service restart
   - Photo upload to Koofr
5. Fix any runtime issues found
6. TestFlight beta once stable

**Known issues to hit during testing:**
- FoldersResponse mismatch (see below)
- Untested Koofr upload flow
- Untested QR scanner / pairing flow

### Fix FoldersResponse Mismatch
**Priority:** High (will block iOS testing)
**Status:** Not started

Backend `GET /api/folders` returns `list[PhotoSourceResponse]` (flat list), but mobile expects `{ folders: [...], current_source: "..." }` (wrapped with current source). JSON decoding will fail for folder listing.

Files:
- `picframe_4.0/src/api/routes/folders.py`
- `picframe_mgr/iosApp/iosApp/Models/FrameStatus.swift` (FoldersResponse)

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

# PicFrame 4.0 - Parking Lot

Future tasks and improvements tracked for later work.

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

### Fix Port Mismatch (5000 -> 8000)
**Priority:** High
**Status:** Not started

Mobile app hardcodes port 5000 in `PairedFrame.swift` line 44, but picframe_4.0 backend listens on port 8000. Mobile app will fail to connect.

Fix: Update port or make it configurable.

File: `picframe_mgr/iosApp/iosApp/Models/PairedFrame.swift`

### Fix iOS FrameStatus Model Mismatch
**Priority:** High
**Status:** Not started

iOS `FrameStatus` struct expects fields that don't exist in backend (`online`, `uptime`, `currentFolder`). Backend sends different structure (`sync.status`, `current_source`). JSON decoding will fail.

Files:
- `picframe_mgr/iosApp/iosApp/Models/FrameStatus.swift`
- `picframe_4.0/src/api/routes/status.py`

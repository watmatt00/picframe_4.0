# PicFrame Ecosystem - Comprehensive Test Plan

## 1. Overview & How to Use This Plan

### Purpose

This document is the master test plan for the PicFrame ecosystem covering:
- **Raspberry Pi Backend** (`picframe_4.0`) - FastAPI, web dashboard, services
- **iOS Manager App** (`picframe_mgr`) - SwiftUI mobile management app

It validates every screen, every displayed data element, every configurable setting, and the interactions between the web dashboard and the iOS app.

### Test Run Workflow

This document is a **master template**. For each test run:

1. **Copy the template:**
   ```bash
   cp docs/TEST_PLAN.md docs/test_runs/run_$(date +%Y-%m-%d).md
   ```

2. **If testing a different Pi**, find-and-replace `192.168.102.210:8000` with your frame's IP:port.

3. **Fill in the run header** at the top of the copy:
   ```
   Run Date: 2026-02-15
   Tester: Matt
   Pi Target: tkframe (192.168.102.210:8000)
   App Build: Xcode 16, iPhone 14 Pro Simulator
   Notes: Pre-TestFlight validation
   ```

4. **Execute tests** - Check boxes as you go:
   - `[x]` = Pass
   - `[-]` = Skip (note reason)
   - Leave unchecked = Not yet tested

5. **Annotate failures** inline:
   ```
   - [ ] Test description <!-- FAIL: what happened vs what was expected -->
   ```

6. **Diff between runs** to track regression:
   ```bash
   diff docs/test_runs/run_2026-02-15.md docs/test_runs/run_2026-02-20.md
   ```

### Failure Annotation Convention

Use HTML comments for machine-parseable failure notes:
```
<!-- FAIL: Expected 200, got 500. Service was not running. -->
```

These are invisible in rendered markdown but searchable with `grep "FAIL:"`.

---

## 2. Environment Setup

### Prerequisites

| Item | Required | Notes |
|------|----------|-------|
| Raspberry Pi 4/5 | Yes | Running picframe_4.0 backend |
| Tailscale | Yes | Funnel enabled on Pi |
| Mac with Xcode | Yes | For iOS simulator builds |
| iPhone Simulator | Yes | iPhone 14 Pro recommended |
| Koofr account | Yes | With email + password (not OAuth) |
| Sample photos | Yes | 5-10 JPG files for upload testing |
| curl / httpie | Yes | For API validation section |
| Web browser | Yes | For dashboard testing (Safari/Chrome) |

### Test Environment (tkframe)

All commands in this plan use hardcoded values for tkframe. If testing a different frame, find-and-replace `192.168.102.210:8000` with your frame's IP:port in your test run copy.

| Setting | Value |
|---------|-------|
| Pi LAN IP | `192.168.102.210` |
| API Port | `8000` |
| Dashboard | `http://192.168.102.210:8000` |
| Funnel URL | `https://tkframe.tail7de60a.ts.net` |
| Koofr Email | `koofr.obtain355@passmail.net` |

### How to Reset to Clean State

**Pi backend:**
```bash
# Stop services
systemctl --user stop picframe-api picframe

# Clear paired devices
rm ~/.picframe/devices.json

# Reset config to defaults
# (backup first, then edit ~/.picframe/config.yaml)

# Restart
systemctl --user start picframe-api picframe
```

**iOS app (Simulator):**
- Device > Erase All Content and Settings, or
- Delete and reinstall the app from Xcode

### Test Data Requirements

- 5-10 sample JPG photos (various sizes, 1-5 MB each)
- At least 2 different Koofr folders with photos for source switching
- At least one photo source with known photo count for sync verification

---

## 3. Component Tests

---

### 3.1 Health & Connectivity

**Endpoints:** `GET /health`, `GET /version`

- [ ] `GET http://192.168.102.210:8000/health` returns `{"status": "ok"}` with HTTP 200
- [ ] `GET http://192.168.102.210:8000/version` returns `{"version": "4.0.0", "api": "picframe"}` with HTTP 200
- [ ] Dashboard loads at `http://192.168.102.210:8000/` without authentication
- [ ] **Negative:** Request to unreachable IP times out gracefully (no crash)
- [ ] **Negative:** Request to wrong port returns connection refused

> **Automation candidate:** curl health/version checks are trivially scriptable.

---

### 3.2 Pairing

**Endpoints:** `POST /api/v1/pairing/generate`, `POST /api/v1/pair`

#### Dashboard: Generate Pairing Code

- [ ] Navigate to `http://192.168.102.210:8000/pairing`
- [ ] QR code image is displayed and non-empty
- [ ] Manual code is displayed in `ABC-XYZ` format (6 alphanumeric characters)
- [ ] Expiry countdown is shown (starts at ~5 minutes)
- [ ] Funnel URL is displayed on the page
- [ ] 4-step pairing instructions are visible
- [ ] "Regenerate Code" button generates a new code
- [ ] Page auto-reloads when countdown expires

#### iOS: Pair a Frame

- [ ] Open app → Frame list shows empty state with "Pair a Frame" button
- [ ] Tap "Pair a Frame" → PairingView opens
- [ ] Enter Tailscale IP, pairing code, and device name
- [ ] "Pair Device" button is disabled until all 3 fields are filled
- [ ] Pairing code field validates 6-7 character length
- [ ] Tap "Pair Device" → spinner appears during pairing
- [ ] On success: frame appears in frame list with name, role, IP
- [ ] JWT token is stored in iOS Keychain (verify via frame operations working)
- [ ] After pairing, app auto-fetches cloud credentials and source list

#### Negative Cases

- [ ] Wrong pairing code → error message displayed, frame not added
- [ ] Expired code (wait >5 min) → error message displayed
- [ ] Rate limit: generate 3 codes within an hour, 4th attempt returns 429
- [ ] **Negative:** Empty fields → "Pair Device" button stays disabled

> **Automation candidate:** Full API-level pairing flow scriptable via curl.

---

### 3.3 Dashboard - Home Page

**URL:** `http://192.168.102.210:8000/`
**API:** `GET /dashboard/status`

#### Status Display

- [ ] Traffic light indicator is visible (circle/dot)
- [ ] Traffic light is GREEN when sync status = "match" and counts match
- [ ] Traffic light is AMBER when local and remote counts differ
- [ ] Traffic light is RED when sync error has occurred
- [ ] Traffic light is BLUE (animated) when sync is in progress
- [ ] Cloud photo count is displayed and matches remote count
- [ ] Frame (local) photo count is displayed and matches local count
- [ ] Current display source name is shown
- [ ] Current image thumbnail is displayed (from Pi3D)

#### Service Health

- [ ] PicFrame Display service status shown (running/stopped)
- [ ] PicFrame API service status shown (running/stopped)

#### Storage

- [ ] Storage usage shown in GB (e.g., "12.5 GB / 64.0 GB")
- [ ] Storage percentage displayed (e.g., "19.5%")

#### Quick Actions

- [ ] "Sync Now" button triggers sync → traffic light goes BLUE
- [ ] After sync completes, traffic light returns to appropriate color
- [ ] "Restart Frame" button restarts picframe service
- [ ] "Restart API" button restarts picframe-api service (page may briefly disconnect)
- [ ] "Refresh" button updates all displayed data

#### Source Switching

- [ ] Source dropdown/selector lists all configured sources
- [ ] Switching source updates "Current Source" display
- [ ] Switching source auto-triggers sync for the new source

#### Advanced Mode

- [ ] Advanced toggle reveals technical details (JSON, API paths)

---

### 3.4 Dashboard - Settings Page

**URL:** `http://192.168.102.210:8000/settings`
**API:** `GET /api/v1/settings`, `POST /api/v1/settings`

- [ ] Frame ID displayed (read-only)
- [ ] Frame Name displayed and editable
- [ ] Funnel URL displayed (read-only)
- [ ] Rotation Interval field shown with current value (seconds)
- [ ] Rotation Interval accepts values 5-3600
- [ ] Sync Interval field shown with current value (seconds)
- [ ] Sync Interval accepts values 60-86400
- [ ] Log Level dropdown: DEBUG, INFO, WARNING, ERROR
- [ ] Submit form → success message displayed
- [ ] Reload page → saved values persist
- [ ] **Negative:** Rotation interval < 5 → validation error
- [ ] **Negative:** Sync interval < 60 → validation error

---

### 3.5 Dashboard - Device Management Page

**URL:** `http://192.168.102.210:8000/devices`
**API:** `GET /api/v1/devices`, `DELETE /api/v1/devices/{id}`

- [ ] Page lists all paired devices
- [ ] Each device shows: name, role, paired date, last seen
- [ ] "Revoke" button present for each device
- [ ] Revoke a device → device removed from list
- [ ] After revoking, that device's JWT no longer works (app shows unauthorized)
- [ ] **Negative:** Cannot revoke the last admin device → error message

---

### 3.6 Dashboard - Pairing Page

**URL:** `http://192.168.102.210:8000/pairing`

_(Covered in section 3.2 above - Dashboard: Generate Pairing Code)_

---

### 3.7 Dashboard - Logs Page

**URL:** `http://192.168.102.210:8000/logs`
**API:** `GET /api/v1/logs`

- [ ] Page loads with operations log displayed by default
- [ ] Toggle between "Operations" and "Security" log types
- [ ] Line count selector works (adjustable 1-500)
- [ ] Log entries display with timestamps
- [ ] Security log shows pairing attempts and auth events
- [ ] Operations log shows sync events and service actions
- [ ] Refresh loads latest entries

---

### 3.8 iOS - Splash & Main Menu

**Views:** `SplashView.swift`, `MainMenuView.swift`

#### Splash Screen

- [ ] App launches with splash animation
- [ ] Splash transitions to main content automatically

#### Main Menu (MainMenuView)

- [ ] Header shows app icon and connected user email
- [ ] Koofr storage card shows used/free/total (progress bar)
- [ ] "Your Frames" card shows up to 3 paired frames
- [ ] Each frame card shows: name, status dot (green=online, red=offline), role, current source, sync status, photo counts
- [ ] Menu buttons visible: Upload Photos, Switch Source, About
- [ ] Settings gear button in toolbar
- [ ] Auto-selects first frame on appearance
- [ ] Auto-fetches Koofr credentials and quota on appearance
- [ ] Tapping a frame card navigates to Frame Detail

---

### 3.9 iOS - Frame List & Pairing

**Views:** `FrameListView.swift`, `PairingView.swift`

#### Frame List

- [ ] Empty state shows message and "Pair a Frame" button when no frames paired
- [ ] Paired frames listed with: name, role badge, IP address
- [ ] Online status indicator: green dot = online, red dot = offline
- [ ] Online status is accurate (ping frame, compare to displayed status)
- [ ] Swipe left on frame → "Unpair" action appears
- [ ] Confirm unpair → frame removed from list
- [ ] Pull-to-refresh updates online status
- [ ] "Add Another Frame" button at bottom of list
- [ ] Tapping a frame navigates to Frame Detail

#### Pairing Flow

_(Covered in section 3.2 above - iOS: Pair a Frame)_

---

### 3.10 iOS - Frame Detail View

**View:** `FrameDetailView.swift`

#### Status Header

- [ ] Frame icon displayed
- [ ] Online/offline indicator matches actual state
- [ ] Role badge shows "Admin" or "Contributor"
- [ ] IP address displayed

#### Storage Card

- [ ] Storage capacity shown (used / total)
- [ ] Progress bar reflects storage usage
- [ ] Progress bar turns red when >90% used
- [ ] Raw byte values are human-readable (GB/MB format)

#### Quick Actions

- [ ] "Upload Photos" button → navigates to upload flow
- [ ] "Switch Source" button → navigates to DestinationsView

#### Services Section (Admin only)

- [ ] Lists services: PicFrame Display, PicFrame API
- [ ] Each service shows running/stopped status with colored dot
- [ ] Restart button present for each service
- [ ] Tap restart → confirmation → service restarts → status updates
- [ ] **Negative:** Restart non-existent service → error handled gracefully

#### Device Management (Admin only)

- [ ] Paired device count displayed
- [ ] Tapping shows device list (name, role, paired date)

#### Navigation

- [ ] Settings button → opens SettingsView sheet
- [ ] Refresh button in toolbar updates all data

---

### 3.11 iOS - Switch Source (Destinations)

**View:** `DestinationsView.swift` (SwitchPhotosView, AddSourceView, SourceDetailView)

#### Currently Displaying Section

- [ ] Current source name shown
- [ ] Sync status displayed: "In Sync" / "Out of Sync" / "Syncing" / "Sync Error"
- [ ] Local photo count (photos on frame) displayed
- [ ] Cloud photo count displayed
- [ ] Last sync timestamp shown
- [ ] "Sync Now" button visible (admin only)
- [ ] Tap "Sync Now" → sync triggers → status updates

#### Source List

- [ ] All configured sources listed
- [ ] Each source shows: name, photo count, path
- [ ] Active source has a badge/indicator
- [ ] Tapping a source opens SourceDetailView sheet

#### Activate Source

- [ ] Tap inactive source → "Activate" button in detail view
- [ ] Activate → source becomes active, auto-sync triggers
- [ ] Verify "Currently Displaying" section updates to new source
- [ ] Verify traffic light / sync status reflects the switch

#### Add New Source (Admin only)

- [ ] "Add New Source" button visible
- [ ] Enter folder name → tap "Create Source"
- [ ] New source appears in list
- [ ] Backend auto-configures rclone remote (KFR_{source_id} folder created)
- [ ] **Negative:** Empty name → button disabled or error

#### Source Detail View

- [ ] Source name displayed
- [ ] Status: Active / Inactive
- [ ] Photo count shown
- [ ] Path displayed
- [ ] Sync status details: cloud files, local files, sync status badge
- [ ] "Activate" button (if not active, admin only)
- [ ] "Sync Now" button (admin only)

#### Navigation

- [ ] Pull-to-refresh reloads source list and sync status

---

### 3.12 iOS - Upload Photos

**Views:** `UploadSheetView.swift`, `UploadView.swift`

#### Destination Picker

- [ ] Segmented control shown when 2 or fewer destinations
- [ ] Menu picker shown when more than 2 destinations
- [ ] All configured Koofr destinations appear
- [ ] Default destination is pre-selected

#### Photo Selection

- [ ] Photo picker opens iOS photo library
- [ ] Can select up to 20 photos
- [ ] Selected photos show as thumbnail grid (4 columns)
- [ ] Photo count displayed

#### Upload Flow

- [ ] "Upload" button triggers upload to Koofr
- [ ] Progress indicator shows current/total (e.g., "3/10")
- [ ] Success message: "Photos will sync to your frame automatically"
- [ ] Koofr quota refreshes after upload
- [ ] **Negative:** No Koofr credentials configured → appropriate error message
- [ ] **Negative:** Upload failure (network issue) → error message, no crash
- [ ] **Negative:** Select 0 photos → upload button disabled

> **Automation candidate:** Koofr upload via API is scriptable for quota/file verification.

---

### 3.13 iOS - Settings

**View:** `SettingsView.swift`

#### Account Section

- [ ] Connected email address displayed
- [ ] "Test Connection" button → tests Koofr connection → result shown

#### Storage Section

- [ ] Progress bar shows Koofr storage usage
- [ ] Used/free values displayed (human-readable)
- [ ] Only appears when quota data is available

#### Frame Actions (Admin only)

- [ ] "Sync Now" button → triggers sync on selected frame
- [ ] Service restart buttons with status dots (green=running, red=stopped)
- [ ] "View Logs" button → opens LogViewerView sheet

#### Sync Settings (Admin only)

- [ ] Sync interval slider: 1-60 minutes
- [ ] Slider shows current value
- [ ] "Save" button saves interval (sends value × 60 as seconds to API)
- [ ] Saved value persists on reload

#### Danger Zone

- [ ] "Change Credentials" → prompts for new Koofr email/password
- [ ] "Unpair All Frames" → confirmation dialog → removes all frames
- [ ] "Clear All Data" → confirmation dialog → wipes credentials, frames, destinations
- [ ] Each danger action has a confirmation dialog before executing

#### App Info

- [ ] Version "1.0.0" displayed at bottom
- [ ] Success/error messages shown for operations

---

### 3.14 iOS - Log Viewer

**View:** `LogViewerView.swift`
**API:** `GET /api/v1/logs?lines={n}&log_type={type}`

- [ ] Segmented picker: "Operations" / "Security"
- [ ] Defaults to "Operations" log
- [ ] Log entries displayed in scrollable list
- [ ] Color-coded dots: ERROR=red, WARNING=orange, INFO=blue, other=gray
- [ ] Text uses monospaced caption font
- [ ] Refresh button in toolbar reloads entries
- [ ] Fetches 200 lines by default
- [ ] Loading spinner while fetching
- [ ] Empty state when no log entries
- [ ] Switching log type triggers reload

---

### 3.15 iOS - File Browser

**View:** `FileBrowserView.swift`

- [ ] Directory listing shows folders and files
- [ ] Files show: name, size (human-readable), date, type icon
- [ ] Folders are distinguishable from files
- [ ] Swipe to delete on a file → confirmation alert
- [ ] Confirm delete → file removed from list
- [ ] Pull-to-refresh reloads file list
- [ ] Empty state displayed when folder is empty
- [ ] Navigation title shows current path/folder name

---

### 3.16 iOS - About View

**View:** `AboutView.swift`

- [ ] App name and info displayed
- [ ] Version information shown
- [ ] "How it works" explanation present
- [ ] Koofr link/reference included
- [ ] No broken links or placeholder text

---

### 3.17 iOS - Setup View

**View:** `SetupView.swift`

- [ ] Initial Koofr connection setup screen
- [ ] Email and password fields
- [ ] Connection test on submit
- [ ] Success → credentials saved, proceed to main app
- [ ] Failure → error message displayed

---

### 3.18 iOS - Add Destination View

**View:** `AddDestinationView.swift`

- [ ] Custom Koofr upload destination creation
- [ ] Folder browser (FolderBrowserView) for selecting Koofr path
- [ ] Label input for destination name
- [ ] Save creates destination in local storage
- [ ] New destination appears in upload destination picker

---

### 3.19 Role-Based Access

**Model:** `FrameRole` in `PairedFrame.swift`

#### Admin Role

- [ ] All features accessible: restart, settings, device management, source create, sync

#### Contributor Role (Placeholder)

- [ ] Cannot restart services (buttons hidden/disabled)
- [ ] Cannot access settings
- [ ] Cannot manage devices
- [ ] Cannot create new sources
- [ ] Can view status and upload photos

> **Note:** Contributor role is not yet fully implemented on the backend. This section serves as a placeholder for when contributor invite flow is complete.

---

## 4. End-to-End Scenarios

---

### 4.1 First-Time Setup

**Goal:** Validate the complete onboarding flow from scratch.

- [ ] Start with clean iOS app (no stored data)
- [ ] Generate pairing code on dashboard (`http://192.168.102.210:8000/pairing`)
- [ ] In app: enter IP, code, device name → pair successfully
- [ ] Frame appears in app with online status
- [ ] Configure Koofr credentials in Settings (or via SetupView)
- [ ] Test Koofr connection → success
- [ ] Upload 3-5 sample photos via Upload screen
- [ ] Verify photos appear in Koofr (via web or file browser)
- [ ] Trigger sync from app or wait for auto-sync
- [ ] Verify photo count on frame matches uploaded count
- [ ] Dashboard shows matching counts and GREEN traffic light

---

### 4.2 Daily Photo Management

**Goal:** Validate the typical photo upload workflow.

- [ ] Open app → main menu shows current frame status
- [ ] Tap "Upload Photos" → select 5 photos → choose destination
- [ ] Upload completes with progress indicator → success message
- [ ] Koofr quota updates (used space increases)
- [ ] Trigger sync (or wait for scheduled sync)
- [ ] Frame local count increases to match cloud count
- [ ] Dashboard traffic light is GREEN after sync completes
- [ ] Photo is visible on the physical frame display (if testing on real Pi)

---

### 4.3 Source Management

**Goal:** Validate creating and switching between photo sources.

- [ ] In app: Switch Source → tap "Add New Source"
- [ ] Enter name (e.g., "Test Source") → create
- [ ] New source appears in list with 0 photos
- [ ] Upload photos to the new source's Koofr folder
- [ ] Tap new source → "Activate" in detail view
- [ ] Frame switches to new source → sync triggers automatically
- [ ] "Currently Displaying" updates to new source name
- [ ] Photo count reflects the new source's photos
- [ ] Previous source is no longer marked as active

---

### 4.4 Dashboard <-> App Consistency

**Goal:** Validate that changes made in one interface are reflected in the other.

- [ ] **Dashboard → App:** Switch source on dashboard → refresh app → app shows new source
- [ ] **App → Dashboard:** Change sync interval in app Settings (e.g., 5 min) → reload dashboard Settings → shows new value
- [ ] **App → Dashboard:** Restart a service from app → dashboard shows service restarting/recovering
- [ ] **App → Dashboard:** Upload photos in app → trigger sync → dashboard counts update
- [ ] **Dashboard → App:** Revoke a device on dashboard → app for that device gets unauthorized errors

---

### 4.5 Admin Maintenance

**Goal:** Validate administrative operations.

- [ ] Open app Settings → "View Logs" → operations log loads
- [ ] Switch to security log → security events displayed
- [ ] Restart PicFrame Display service from app → service recovers
- [ ] Restart PicFrame API service from app → brief disconnect, then reconnects
- [ ] Check sync status after restart → services resume normally
- [ ] Trigger manual sync → verify it completes and counts match

---

### 4.6 Device Management

**Goal:** Validate multi-device pairing and revocation.

- [ ] Pair a second device (or simulate with different device name)
- [ ] Dashboard devices page shows both devices
- [ ] App Frame Detail shows paired device count = 2
- [ ] Revoke second device from app → device removed
- [ ] Dashboard devices page updates to show only 1 device
- [ ] **Negative:** Attempt to revoke last admin → error: "Cannot revoke last admin device"

---

### 4.7 Error Recovery

**Goal:** Validate graceful handling of error conditions.

- [ ] Stop the Pi API service → app shows frame as offline (red dot)
- [ ] Restart the API service → app detects frame is back online (green dot)
- [ ] Enter wrong Koofr credentials → "Test Connection" fails with auth error
- [ ] Fix credentials → "Test Connection" succeeds
- [ ] Attempt upload with bad credentials → error message, no crash
- [ ] Fix credentials → retry upload → succeeds
- [ ] Trigger source activation during an active sync → verify behavior (should queue or reject gracefully)
- [ ] **Negative:** Open app with Pi completely offline → frame shows offline, no crash, graceful error messages

---

## 5. API Validation (curl commands)

### Before You Start: Get Your JWT Token

Most curl commands below require a JWT token. Set it once in your terminal session:

**Option A** — Pull from the Pi's device file (if already paired):
```bash
TOKEN=$(ssh matt@192.168.102.210 "python3 -c \"import json; d=json.load(open('.picframe/devices.json')); print(d['devices'][0]['token'])\"")
```

**Option B** — Pair via curl (run tests 5.3 + 5.4 first, then copy the token from the response):
```bash
TOKEN=eyJhbG...paste_your_token_here...
```

Verify it works:
```bash
curl -s http://192.168.102.210:8000/api/v1/status -H "Authorization: Bearer $TOKEN" | head -c 100
```

`$TOKEN` is the **only variable** in this section. All other values are hardcoded.

### Health & Version

```bash
# 5.1 Health check
curl -s http://192.168.102.210:8000/health
# Expected: {"status":"ok"}

# 5.2 Version
curl -s http://192.168.102.210:8000/version
# Expected: {"version":"4.0.0","api":"picframe"}
```

- [ ] 5.1 Health returns `{"status": "ok"}` with HTTP 200
- [ ] 5.2 Version returns `{"version": "4.0.0", "api": "picframe"}` with HTTP 200

### Pairing Flow

```bash
# 5.3 Generate pairing code (requires existing admin token)
curl -s -X POST http://192.168.102.210:8000/api/v1/pairing/generate \
  -H "Authorization: Bearer $TOKEN"
# Expected: {"qr_code_base64":"...","code":"ABC-XYZ","expires_at":"..."}

# 5.4 Exchange code for token
curl -s -X POST http://192.168.102.210:8000/api/v1/pair \
  -H "Content-Type: application/json" \
  -d '{"code":"ABC-XYZ","device_name":"curl-test"}'
# Expected: {"token":"...","frame_id":"...","frame_name":"...","role":"admin","api_port":8000}
```

- [ ] 5.3 Pairing code generation returns code in ABC-XYZ format
- [ ] 5.4 Pairing exchange returns valid JWT token

### Status

```bash
# 5.5 Frame status
curl -s http://192.168.102.210:8000/api/v1/status \
  -H "Authorization: Bearer $TOKEN"
```

- [ ] 5.5 Status returns frame_id, frame_name, current_source, photo_count, services array, sync object, capacity object
- [ ] 5.5 Services array contains picframe and picframe-api entries
- [ ] 5.5 Capacity includes total_bytes, used_bytes, free_bytes, percent_used

### Folder/Source Management

```bash
# 5.6 List folders
curl -s http://192.168.102.210:8000/api/v1/folders \
  -H "Authorization: Bearer $TOKEN"
# Expected: {"folders":[...],"current_source":"..."}

# 5.7 Create folder
curl -s -X POST http://192.168.102.210:8000/api/v1/folders \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"curl_test_source"}'
# Expected: 201 with id, name, local_path, rclone_remote, enabled, photo_count

# 5.8 Switch display folder
curl -s -X POST http://192.168.102.210:8000/api/v1/display/folder \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source_id":"curl_test_source"}'
# Expected: {"success":true,"source_id":"...","source_name":"...","path":"...","message":"..."}
```

- [ ] 5.6 Folders list returns array with id, name, path, photo_count and current_source
- [ ] 5.7 Create folder returns 201 with auto-configured rclone remote
- [ ] 5.8 Switch folder returns success and triggers background sync

### Sync

```bash
# 5.9 Trigger sync all
curl -s -X POST http://192.168.102.210:8000/api/v1/folders/sync/all \
  -H "Authorization: Bearer $TOKEN"
# Expected: {"message":"...","sources_queued":[...]}

# 5.10 Get sync status for a source
curl -s http://192.168.102.210:8000/api/v1/folders/{source_id}/sync/status \
  -H "Authorization: Bearer $TOKEN"
# Expected: {"is_syncing":...,"local_count":...,"remote_count":...,"sync_status":"..."}
```

- [ ] 5.9 Sync all returns sources_queued array
- [ ] 5.10 Sync status returns is_syncing, local_count, remote_count, sync_status

### Service Management

```bash
# 5.11 Restart picframe service
curl -s -X POST http://192.168.102.210:8000/api/v1/services/picframe/restart \
  -H "Authorization: Bearer $TOKEN"
# Expected: {"success":true,"message":"Service 'picframe' restarted successfully"}

# 5.12 Invalid service name
curl -s -X POST http://192.168.102.210:8000/api/v1/services/invalid_service/restart \
  -H "Authorization: Bearer $TOKEN"
# Expected: 400 with error
```

- [ ] 5.11 Restart returns success for valid service
- [ ] 5.12 Invalid service name returns 400 error

### Settings

```bash
# 5.13 Get settings
curl -s http://192.168.102.210:8000/api/v1/settings \
  -H "Authorization: Bearer $TOKEN"
# Expected: {"sync_interval":...,"rotation_interval":...,"frame_name":"..."}

# 5.14 Update sync interval
curl -s -X PUT http://192.168.102.210:8000/api/v1/settings/sync-interval \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"interval":600}'
# Expected: {"success":true,"message":"Sync interval updated to 600 seconds"}

# 5.15 Invalid sync interval (too low)
curl -s -X PUT http://192.168.102.210:8000/api/v1/settings/sync-interval \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"interval":10}'
# Expected: 422 or 400 validation error
```

- [ ] 5.13 Settings returns sync_interval, rotation_interval, frame_name
- [ ] 5.14 Update sync interval returns success
- [ ] 5.15 Invalid interval (< 60) returns validation error

### Device Management

```bash
# 5.16 List devices
curl -s http://192.168.102.210:8000/api/v1/devices \
  -H "Authorization: Bearer $TOKEN"
# Expected: array of devices with id, name, role, paired_at, last_seen

# 5.17 Revoke device (use a non-critical device ID)
curl -s -X DELETE http://192.168.102.210:8000/api/v1/devices/{device_id} \
  -H "Authorization: Bearer $TOKEN"
# Expected: {"status":"revoked","device_id":"..."}
```

- [ ] 5.16 Device list returns array with expected fields
- [ ] 5.17 Device revocation succeeds (test with expendable device)

### Logs

```bash
# 5.18 Operations logs
curl -s "http://192.168.102.210:8000/api/v1/logs?lines=50&log_type=ops" \
  -H "Authorization: Bearer $TOKEN"
# Expected: {"entries":[...],"log_type":"ops","count":...}

# 5.19 Security logs
curl -s "http://192.168.102.210:8000/api/v1/logs?lines=50&log_type=security" \
  -H "Authorization: Bearer $TOKEN"
# Expected: {"entries":[...],"log_type":"security","count":...}
```

- [ ] 5.18 Operations logs return entries array with count
- [ ] 5.19 Security logs return entries array with count

### Cloud Credentials

```bash
# 5.20 Get cloud credentials
curl -s http://192.168.102.210:8000/api/v1/cloud/credentials \
  -H "Authorization: Bearer $TOKEN"
# Expected: {"credentials":{"provider":"koofr","email":"...","password":"..."},"message":"..."}
```

- [ ] 5.20 Cloud credentials return provider, email, password

### Authentication Negative Cases

```bash
# 5.21 No token
curl -s http://192.168.102.210:8000/api/v1/status
# Expected: 401

# 5.22 Invalid token
curl -s http://192.168.102.210:8000/api/v1/status \
  -H "Authorization: Bearer invalid_token_here"
# Expected: 401
```

- [ ] 5.21 Missing token returns 401
- [ ] 5.22 Invalid token returns 401

### Services List

```bash
# 5.23 List services
curl -s http://192.168.102.210:8000/api/v1/services \
  -H "Authorization: Bearer $TOKEN"
# Expected: array of services with name, display_name, active, status, can_restart
```

- [ ] 5.23 Services list returns picframe and picframe-api with status fields

### Display Folder (GET)

```bash
# 5.24 Get current display folder
curl -s http://192.168.102.210:8000/api/v1/display/folder \
  -H "Authorization: Bearer $TOKEN"
# Expected: {"current_source":"...","source_name":"...","path":"..."}
```

- [ ] 5.24 Display folder returns current_source, source_name, path

### Direct Sync Trigger

```bash
# 5.25 Trigger sync (dashboard endpoint, no auth on LAN)
curl -s -X POST http://192.168.102.210:8000/api/v1/sync
# Expected: {"status":"started","source":"..."}
```

- [ ] 5.25 Sync trigger returns started status with source name

### Dashboard-Specific APIs

```bash
# 5.26 Dashboard status (no auth, LAN only)
curl -s http://192.168.102.210:8000/dashboard/status
# Expected: JSON with sync_status, counts, services, storage

# 5.27 Current image proxy
curl -s -o /dev/null -w "%{http_code}" http://192.168.102.210:8000/current-image
# Expected: 200 with image data (or 404/502 if Pi3D not running)

# 5.28 Switch source (dashboard endpoint)
curl -s -X POST http://192.168.102.210:8000/switch-source \
  -H "Content-Type: application/json" \
  -d '{"source_id":"koofr_main"}'
# Expected: success response

# 5.29 Save settings (dashboard endpoint)
curl -s -X POST http://192.168.102.210:8000/api/v1/settings \
  -H "Content-Type: application/json" \
  -d '{"frame_name":"Test Frame","rotation_interval":30,"sync_interval":900,"log_level":"INFO"}'
# Expected: success response
```

- [ ] 5.26 Dashboard status returns sync_status, local_count, remote_count, services, storage fields
- [ ] 5.27 Current image endpoint responds (200 with image or appropriate error if Pi3D offline)
- [ ] 5.28 Dashboard switch source changes active source
- [ ] 5.29 Dashboard settings save persists values

### Source Management (Dashboard)

```bash
# 5.30 List sources (dashboard)
curl -s http://192.168.102.210:8000/api/v1/sources
# Expected: source list with id, name, local_path, rclone_remote, enabled

# 5.31 Create source (dashboard)
curl -s -X POST http://192.168.102.210:8000/api/v1/sources/create \
  -H "Content-Type: application/json" \
  -d '{"name":"Dashboard Test","rclone_remote":"koofr:KFR_dashboard_test"}'
# Expected: created source object

# 5.32 Delete source (dashboard)
curl -s -X POST http://192.168.102.210:8000/api/v1/sources/delete \
  -H "Content-Type: application/json" \
  -d '{"source_id":"dashboard_test"}'
# Expected: success response

# 5.33 Frame live - switch and sync (dashboard)
curl -s -X POST http://192.168.102.210:8000/api/v1/frame-live \
  -H "Content-Type: application/json" \
  -d '{"source_id":"koofr_main"}'
# Expected: switches source and triggers sync
```

- [ ] 5.30 Sources list returns array with expected fields
- [ ] 5.31 Source creation returns new source with auto-configured rclone remote
- [ ] 5.32 Source deletion removes source (test with expendable source)
- [ ] 5.33 Frame-live switches source and triggers sync

### rclone Integration (Dashboard)

```bash
# 5.34 List rclone remotes
curl -s http://192.168.102.210:8000/api/v1/rclone/remotes
# Expected: list of configured rclone remotes

# 5.35 Browse rclone directories
curl -s -X POST http://192.168.102.210:8000/api/v1/rclone/list-dirs \
  -H "Content-Type: application/json" \
  -d '{"remote":"koofr:","path":"/"}'
# Expected: directory listing

# 5.36 List local directories
curl -s http://192.168.102.210:8000/api/v1/local/list-dirs
# Expected: list of directories in ~/Pictures

# 5.37 Test remote connection
curl -s -X POST http://192.168.102.210:8000/api/v1/config/test-remote \
  -H "Content-Type: application/json" \
  -d '{"remote":"koofr:"}'
# Expected: connection test result
```

- [ ] 5.34 rclone remotes list returns configured remotes (at least koofr)
- [ ] 5.35 rclone directory browse returns folder listing
- [ ] 5.36 Local directories list returns ~/Pictures contents
- [ ] 5.37 Remote connection test returns success for valid remote

### Device Revocation (Dashboard)

```bash
# 5.38 Revoke device via dashboard endpoint
curl -s -X POST http://192.168.102.210:8000/devices/{device_id}/revoke
# Expected: device revoked
```

- [ ] 5.38 Dashboard device revocation works (test with expendable device)

### Contributor Endpoints (Stubs)

```bash
# 5.39 List contributors (stub)
curl -s http://192.168.102.210:8000/api/v1/contributors \
  -H "Authorization: Bearer $TOKEN"
# Expected: 501 Not Implemented (or empty list)

# 5.40 Create contributor invite (stub)
curl -s -X POST http://192.168.102.210:8000/api/v1/contributors/invite \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
# Expected: 501 Not Implemented
```

- [ ] 5.39 Contributors list returns 501 or empty (stub endpoint)
- [ ] 5.40 Contributor invite returns 501 (not yet implemented)

> **Automation candidate:** This entire section is scriptable as a pytest or bash test suite.

---

## 6. Automation Candidates Summary

| Section | Automatable | Priority | Tool |
|---------|-------------|----------|------|
| 3.1 Health & Connectivity | Fully | High | curl / pytest |
| 3.2 Pairing (API level) | Fully | High | pytest |
| 3.2 Pairing (iOS UI) | Partially | Medium | XCUITest |
| 3.3 Dashboard Home | Partially | Medium | Selenium / Playwright |
| 3.4 Dashboard Settings | Partially | Medium | Selenium / Playwright |
| 3.5 Dashboard Devices | Partially | Medium | Selenium / Playwright |
| 3.7 Dashboard Logs | Partially | Low | Selenium / Playwright |
| 3.8-3.18 iOS Views | Partially | Medium | XCUITest |
| 4.x End-to-End Scenarios | Partially | High | pytest + XCUITest |
| 5.x API Validation | Fully | High | pytest / bash script |

### Recommended Priority Order

1. **API Validation (Section 5)** - Highest ROI, fully scriptable, catches backend regressions
2. **Health & Connectivity (3.1)** - Quick smoke test, run on every deploy
3. **Pairing Flow (3.2 API)** - Critical path, automatable without UI
4. **End-to-End Scenarios (4.x)** - Combined API + manual UI verification
5. **Dashboard Pages (3.3-3.7)** - Browser automation if resources allow
6. **iOS UI Tests (3.8-3.18)** - XCUITest for critical flows

### Suggested Tools

| Tool | Use Case |
|------|----------|
| **pytest** | API endpoint testing, pairing flow, sync verification |
| **requests** (Python) | HTTP client for API tests |
| **XCUITest** | iOS UI automation (pairing, upload, source switching) |
| **Playwright** | Dashboard browser testing |
| **bash/curl** | Quick smoke tests, CI health checks |

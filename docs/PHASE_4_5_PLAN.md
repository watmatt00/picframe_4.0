# Plan: Complete Phase 4 & Phase 5

## Context

Phases 1-3 are complete (API, services, web dashboard). Phases 4 and 5 have gaps:
- **Phase 4**: Scripts/services exist in repo but backend tests have never been run on v4. PI_SETUP.md has stale references ("coming in Phase 4" for systemd, which is done).
- **Phase 5**: iOS app code exists but has NEVER been built in Xcode or tested. Known API mismatches remain (FoldersResponse). FrameClient uses http://IP but needs https://Funnel URL support.

**Key constraints:**
- iOS only. Android is permanently on hold.
- Mac + Apple Developer account are available now.
- Manual pairing first, QR scanner added later after core functionality is verified.
- Mobile connects via Tailscale Funnel: `https://tkframe.tail7de60a.ts.net` (HTTPS + JWT)
- Dashboard connects via LAN: `http://192.168.102.210:8000` (HTTP, no auth)

---

## Phase 4: Pi Deployment - Remaining Work

### 4.1 Update PI_SETUP.md
**What:** Step 8 still says "systemd service - coming in Phase 4" but systemd is already implemented and running.
**File:** `picframe_4.0/docs/PI_SETUP.md` (lines 222-227)
**Action:** Update to show the actual `systemctl --user enable/start` commands as production-ready.

### 4.2 Run and Fix Backend Tests
**What:** Tests exist in `tests/unit/` and `tests/integration/` but have never been executed on v4.
**Files:**
- `picframe_4.0/tests/unit/test_auth.py`
- `picframe_4.0/tests/unit/test_config.py`
- `picframe_4.0/tests/unit/test_sync.py`
- `picframe_4.0/tests/integration/test_api.py`
- `picframe_4.0/tests/integration/test_pairing.py`
- `picframe_4.0/tests/integration/test_dashboard.py`
**Action:**
1. Run `pytest` locally on PC
2. Fix any failures
3. Run on tkframe Pi via SSH to verify in production environment
4. Document test results

### 4.3 Validate Install Script on Fresh Pi (Optional)
**What:** `scripts/install.sh` exists but hasn't been tested on a truly fresh Pi.
**File:** `picframe_4.0/scripts/install.sh`
**Action:** Defer unless setting up a new Pi. tkframe is already running.

---

## Phase 5: iOS Mobile App - Completion Steps

### 5.1 Fix FoldersResponse Mismatch (Pre-Build)
**What:** Backend `GET /api/folders` returns `list[PhotoSourceResponse]` (flat list), but iOS expects `{ folders: [...], current_source: "..." }` (wrapped object). Must fix BEFORE testing or folder listing will crash.
**Files:**
- `picframe_4.0/src/api/routes/folders.py` - wrap response
- `picframe_mgr/iosApp/iosApp/Models/FrameStatus.swift` - verify FoldersResponse struct matches
**Action:** Update backend to return wrapped response matching what iOS expects. Push to Pi.

### 5.2 Fix FrameClient Funnel URL Support (Pre-Build)
**What:** `FrameClient.swift` hardcodes `http://` with IP addresses. Tailscale Funnel uses `https://hostname.ts.net`. App will fail to connect remotely.
**File:** `picframe_mgr/iosApp/iosApp/FrameClient.swift` (line 49, 83)
**Current:** `"http://\(tailscaleIP):\(effectivePort)/api"`
**Needed:** Support both LAN (`http://IP:8000`) and Funnel (`https://hostname.ts.net`) URLs.
**Action:**
- Store full base URL in PairedFrame (from pairing response) instead of constructing from IP
- Backend pairing response already includes `funnel_url` - use it
- Fall back to IP-based URL for LAN access

### 5.3 Build iOS App in Xcode
**What:** First ever compile of the app.
**Where:** Wife's Mac
**Action:**
1. Clone `picframe_mgr` repo on Mac
2. Open `iosApp/iosApp.xcodeproj` in Xcode
3. Build for simulator (iPhone 15 or similar)
4. Fix compile errors (expect some - code was written without Xcode)
5. Iterate until clean build

### 5.4 Test Against Live Pi API
**What:** Verify each feature works against tkframe (192.168.102.210:8000 / Funnel URL).
**Test sequence:**
1. **Manual pairing**: Enter tkframe IP + pairing code from dashboard → verify JWT received, frame appears in app
2. **Status view**: Open frame detail → verify FrameStatus displays (photo count, services, sync status, capacity)
3. **Folder listing**: View folders → verify list loads (depends on 5.1 fix)
4. **Folder switching**: Switch active source → verify dashboard reflects change
5. **Service restart**: Restart picframe service → verify it restarts
6. **Koofr upload**: Upload a photo → verify it appears in Koofr web interface
7. **Funnel access**: Disconnect from home WiFi, connect via Funnel URL → verify all above works over HTTPS

### 5.5 Fix Runtime Issues
**What:** Fix bugs discovered during 5.4 testing.
**Action:** Iterative - fix, rebuild, retest until core flows work.

### 5.6 TestFlight Beta
**What:** Distribute to family for testing.
**Action:**
1. Set up App Store Connect (if not already done)
2. Configure signing & provisioning in Xcode
3. Archive and upload to TestFlight
4. Add family as beta testers
5. Collect feedback

### 5.7 QR Scanner (After Core is Stable)
**What:** Add camera-based QR code scanning as alternative to manual IP entry.
**File:** New `QRScannerView.swift` using AVFoundation
**Action:** Implement after manual pairing is verified working. QR contains Funnel URL + pairing code (already generated by backend).

---

## Execution Order

```
Phase 4:
  4.1 Update PI_SETUP.md docs          (PC - quick)
  4.2 Run/fix backend tests            (PC + Pi SSH)

Phase 5 (on Mac):
  5.1 Fix FoldersResponse mismatch     (PC - backend fix, push to Pi)
  5.2 Fix FrameClient Funnel URLs      (PC - iOS code fix)
  5.3 Build in Xcode                   (Mac)
  5.4 Test against live Pi             (Mac + tkframe)
  5.5 Fix runtime issues               (Mac - iterative)
  5.6 TestFlight beta                  (Mac)
  5.7 QR scanner                       (Mac - after core stable)
```

Steps 4.1, 4.2, 5.1, and 5.2 can be done on PC now.
Steps 5.3-5.7 require Mac.

---

## Key Files

**Backend (picframe_4.0):**
- `src/api/routes/folders.py` - FoldersResponse fix
- `src/api/routes/status.py` - Status API
- `docs/PI_SETUP.md` - Setup guide updates
- `tests/` - Backend test suite

**iOS (picframe_mgr):**
- `iosApp/iosApp/FrameClient.swift` - HTTP client (Funnel URL fix)
- `iosApp/iosApp/Models/PairedFrame.swift` - Frame model
- `iosApp/iosApp/Models/FrameStatus.swift` - Status + FoldersResponse models
- `iosApp/iosApp/PairingView.swift` - Manual pairing UI
- `iosApp/iosApp.xcodeproj` - Xcode project

---

## Verification

- Phase 4 done when: PI_SETUP.md updated, `pytest` passes on PC and Pi
- Phase 5 done when: iOS app builds clean, all 7 test scenarios in 5.4 pass, TestFlight build uploaded

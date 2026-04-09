# Plan: Complete Phase 4 & Phase 5

## Current Status

**Phase 4: Mostly complete.** Backend deployed and running on tkframe Pi.
**Phase 5: Core functionality complete.** iOS app builds, runs on simulator, and works against live Pi API.

**Key constraints:**
- iOS only. Android is permanently on hold.
- Mac + Apple Developer account are available now.
- Mobile connects via Tailscale Funnel: `https://tkframe.tail7de60a.ts.net` (HTTPS + JWT)
- Dashboard connects via LAN: `http://192.168.102.210:8000` (HTTP, no auth)

---

## Phase 4: Pi Deployment - Status

### 4.1 ~~Update PI_SETUP.md~~ - DONE
systemd services documented as production-ready.

### 4.2 ~~Run and Fix Backend Tests~~ - DONE
All 48 tests pass on PC. Fixed stale route references (`/api/` → `/api/v1/`), removed obsolete standalone dashboard page tests (consolidated into single-page tab UI), migrated Pydantic v1 `Config` to `ConfigDict`, and fixed `TemplateResponse` argument order.

### 4.3 Validate Install Script on Fresh Pi (Optional)
**What:** `scripts/install.sh` exists but hasn't been tested on a truly fresh Pi.
**Action:** Defer unless setting up a new Pi. tkframe is already running.

---

## Phase 5: iOS Mobile App - Status

### 5.1 ~~Fix FoldersResponse Mismatch~~ - DONE
Backend returns wrapped response matching iOS expectations.

### 5.2 ~~Fix FrameClient Funnel URL Support~~ - DONE
`PairedFrame.baseURL` supports both LAN (`http://IP:8000/api/v1`) and Funnel (`https://hostname.ts.net/api/v1`) URLs. Backend pairing response includes `funnel_url`.

### 5.3 ~~Build iOS App in Xcode~~ - DONE
App builds and runs on iPhone 14 Pro simulator.

### 5.4 ~~Test Against Live Pi API~~ - DONE
All core features verified:
- Pairing flow (manual code entry)
- Status display (photo count, services, sync status, capacity)
- Source listing and switching (Activate)
- Auto-sync on source activation
- Photo upload to Koofr
- Service restart (Frame, API)
- Settings (sync interval, log viewer)

### 5.5 ~~Fix Runtime Issues~~ - DONE (iterative)
Multiple rounds of testing and fixes completed. See task list for details.

### 5.5b ~~Manual Test Plan~~ - DONE
Comprehensive test plan created at `docs/TEST_PLAN.md`. 308 test cases covering backend API (40 endpoints), web dashboard (5 pages), iOS app (16 views), and 7 end-to-end scenarios. Copy-per-run workflow with `docs/test_runs/` directory.

### 5.6 ~~TestFlight Beta~~ - DONE
Distributed to family via TestFlight. App Store Connect configured, signing/provisioning set up, archived and uploaded.

### 5.7 ~~QR Scanner~~ - DONE
Camera-based QR code scanning implemented and tested in picframe_mgr repo.

---

## Completed Work Summary

| Task | Status |
|------|--------|
| API versioning (`/api/v1/`) | Done |
| Status logic consolidation (`status_service.py`) | Done |
| OpenAPI spec (auto-generated at `/openapi.json`) | Done |
| iOS build in Xcode | Done |
| Pairing flow | Done |
| Status display | Done |
| Source switching (Activate) | Done |
| Auto-sync on activation | Done |
| Photo upload via Koofr | Done |
| Service restart | Done |
| Sync interval settings | Done |
| Log viewer | Done |
| Manual test plan (308 test cases) | Done |
| TestFlight beta distribution | Done |
| Dashboard pairing improvements | Done |
| FoldersResponse fix | Done |
| FrameClient Funnel URL support | Done |

## Remaining Work

| Task | Priority |
|------|----------|
| ~~Run backend test suite (`pytest`)~~ | Done |
| ~~TestFlight beta distribution~~ | Done |
| ~~QR scanner for pairing~~ | Done |
| Revert pairing code rate limit (50 → 3 per hour) | **Last step before prod** |

---

## Phase 6: WiFi Recovery & Setup Mode

**Status:** Design complete — ready for implementation
**Problem:** Frames deployed to family have no recovery path when WiFi changes. Fix requires physical SD card removal today.

### Design Decisions (finalized 2026-03-02)

- **WiFi check = association only** (`iw dev wlan0 link`). Never ping 8.8.8.8. Internet down ≠ WiFi down.
- **Display runs during WiFi outages** — the `needs_setup` flag is set silently in the background. Display only stops when setup mode is actively entered on reboot (Situation B: extended outage), or was never started (Situation A: first boot with no photos).
- **10-minute outage threshold** → set `needs_setup = true` in `state.yaml`. If WiFi recovers at any time, clear flag immediately.
- **`needs_setup` only acts on next reboot** — no mid-session disruption ever.
- **Setup mode = BLE + AP simultaneously.** First to complete wins. No app required (AP/captive portal covers it).
- **Updates** only when WiFi associated AND internet reachable. Skipped silently otherwise.
- **No separate boot grace period** — the 10-min timer is the grace period.

### State File: `state.yaml`

```yaml
frame_name: kframe
provisioned: true/false          # false = never configured
first_run_complete: true/false   # false = awaiting initial sync
koofr_configured: true/false
needs_setup: false               # true = enter setup mode on next boot
last_wifi_connected: "2026-03-01T10:23:00"
setup_mode_reason: null          # "boot_no_wifi" | "extended_outage" | "unprovisioned"
```

### 6.1 WiFi Watchdog (`picframe-watchdog.service`)

- Polls every 30s via `iw dev wlan0 link`
- Starts 10-min countdown on loss; sets `needs_setup = true` at expiry
- Clears flag immediately when WiFi recovers
- Fully independent of display process

### 6.2 BLE Setup Service (`picframe-ble-setup.service`)

- Active only in setup mode
- Advertises `picframe-[framename]-setup`
- Accepts WiFi credentials via GATT: `{ "ssid": "...", "password": "..." }`
- On receive: writes `wpa_supplicant.conf`, clears flag, reboots
- Service UUID: `4fafc201-1fb5-459e-8fcc-c5c9c331914b`, Characteristic UUID: `beb5483e-36e1-4688-b7f5-ea07361b26a8`. Implemented in `ble_setup.py`.

### 6.3 AP / Captive Portal (`picframe-ap-setup.service`)

- Active simultaneously with BLE during setup mode
- hostapd hotspot: `PicFrame-[framename]`
- dnsmasq: DHCP + DNS hijack → any URL opens portal
- Flask page at `192.168.4.1`
- First run: collects WiFi + Koofr creds + frame name
- Reconfiguration: collects WiFi SSID/password only
- Random per-frame password generated from Pi serial in `install_setup.sh`. Currently set to `"picframe"` for testing — switch to random for final production test stage.

### 6.4 First-Run Flow

```
Boot (provisioned = false)
  └─► Skip watchdog
  └─► Enter setup mode (BLE + AP)
  └─► Write config, provisioned = true, first_run_complete = false
  └─► Reboot → connect WiFi → verify Koofr → initial sync
  └─► first_run_complete = true → normal operation
```

Resolved — portal validates Koofr credentials live before accepting the form. Frame never reboots with bad creds.

### 6.5 `picframe-config` Bash Wrapper

SSH/Tailscale maintenance tool. No UI or app required.

```bash
picframe-config --wifi-ssid "Name" --wifi-password "secret"
picframe-config --frame-name "kframe"
picframe-config --koofr-user "user" --koofr-pass "secret"
picframe-config --show
picframe-config --clear-setup   # manually clear flag
picframe-config --force-setup   # manually trigger setup mode on next boot
```

### 6.6 Status Overlay (Deferred — after core logic)

Small dots, upper right corner, hidden during healthy operation.

| State | Overlay |
|-------|---------|
| Normal, WiFi + internet | Hidden |
| WiFi associated, no internet | Grey dot |
| WiFi down < 10 min | Yellow dot |
| WiFi down > 10 min | Red dot |
| Setup mode active | Orange pulse + blue pulse (BLE) |
| First run syncing | Spinner |

### Rejected Approaches

- Separate 3-min boot grace period (redundant with 10-min timer)
- Mid-session AP activation (flag only acts on reboot)
- `maintenance_reboot` flag (use `--clear-setup` instead)
- Internet reachability for WiFi check (association only)
- Staged BLE-before-AP (both run simultaneously)

---

## Key Files

**Backend (picframe_4.0):**
- `src/api/app.py` - FastAPI app with `/api/v1` prefix
- `src/api/routes/` - API route modules
- `src/services/status_service.py` - Shared status logic
- `src/dashboard/routes.py` - Dashboard routes (LAN-only)
- `tests/` - Backend test suite

**iOS (picframe_mgr):**
- `iosApp/iosApp/FrameClient.swift` - HTTP client (uses `/api/v1` base URL)
- `iosApp/iosApp/Models/PairedFrame.swift` - Frame model with baseURL
- `iosApp/iosApp/Models/FrameStatus.swift` - Status + response models
- `iosApp/iosApp/MainViewModel.swift` - View model with all API calls
- `iosApp/iosApp/DestinationsView.swift` - Switch Source view
- `iosApp/iosApp/SettingsView.swift` - Settings with sync interval + log viewer
- `iosApp/iosApp/LogViewerView.swift` - Log viewer (ops/security)

---

## Verification

- Phase 4 done when: `pytest` passes on PC and Pi
- Phase 5 done when: TestFlight build uploaded, QR scanner implemented

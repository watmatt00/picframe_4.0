# Concerns & Technical Debt
_Last updated: 2026-04-19_

## Summary

PicFrame 4.0 is in solid shape for a single-user home appliance. The security posture is appropriate for the threat model (LAN + Tailscale VPN, family only). However, there are four confirmed high-priority security issues formally tracked in `docs/PARKING_LOT.md` that have not yet been fixed: a live debug token endpoint, a spoofable X-Forwarded-For header, an incomplete dashboard path allowlist, and a memory-exhaustion risk on large contributor uploads. Outside of security, the main weaknesses are shallow test coverage, in-memory state that evaporates on restart, `remote_count` hardcoded to 0 in the initial dashboard render, and `dashboard/routes.py` growing large enough (1,456 lines) to become a maintenance liability.

---

## Security Concerns

### [HIGH] Debug token endpoint still live
- **File:** `src/api/app.py:62-74`
- **Issue:** `GET /debug/token` is an unauthenticated endpoint that mints a valid JWT for any caller. It is not protected by middleware because it is not in `DASHBOARD_PATHS`. Tokens it produces are blocked by the device-existence check in `src/api/dependencies.py:40`, but the endpoint should not exist at all.
- **Tracked:** `docs/PARKING_LOT.md` — Priority: High
- **Fix:** Delete lines 62-74 of `src/api/app.py`.

### [HIGH] X-Forwarded-For trusted without a proxy
- **File:** `src/api/middleware.py:73-76`
- **Issue:** `LANOnlyDashboardMiddleware` reads `X-Forwarded-For` first and uses it as the authoritative client IP. The Pi runs uvicorn directly — no reverse proxy is in front of it. Any Tailscale peer or internet client can set this header to a LAN IP (e.g. `192.168.1.1`) and bypass the LAN-only restriction on all dashboard routes.
- **Tracked:** `docs/PARKING_LOT.md` — Priority: High
- **Fix:** Remove lines 74-78 from `dispatch()`; use only `request.client.host`.

### [HIGH] Dashboard middleware uses an allowlist, not a blocklist
- **File:** `src/api/middleware.py:12`
- **Issue:** `DASHBOARD_PATHS = ["/", "/settings", "/devices", "/pairing", "/logs"]` covers only 5 of ~35 dashboard routes. Uncovered routes include `POST /sync`, `POST /services/{name}/restart`, `POST /api/updates/apply`, all tool scan/apply endpoints, and backup endpoints. These are accessible from the public internet via Tailscale Funnel without authentication.
- **Tracked:** `docs/PARKING_LOT.md` — Priority: High
- **Fix:** Flip to a blocklist — deny non-LAN/VPN IPs from everything *except* `/api/v1/`, `/health`, and `/version`. New dashboard routes are then protected automatically.

### [MEDIUM] Contributor upload reads full file into RAM before size check
- **File:** `src/api/routes/contributor.py:105-108`
- **Issue:** `contents = await file.read()` reads the entire upload body before the 50 MB guard fires. A large upload (e.g. 500 MB) exhausts process memory before being rejected.
- **Tracked:** `docs/PARKING_LOT.md` — Priority: Medium
- **Fix:** Stream with a chunked read loop that aborts early once `_MAX_UPLOAD_BYTES` is exceeded.

### [LOW] Dead `revoke_token()` stub with misleading TODO
- **File:** `src/auth/jwt_handler.py:116-132`
- **Issue:** The function always returns `False` and is never called. Token revocation is handled correctly by deleting the device record in `src/storage/devices.py`. The stub implies revocation is broken when it is not.
- **Tracked:** `docs/PARKING_LOT.md` — Priority: Low
- **Fix:** Delete the function.

### [LOW] Dashboard test client uses X-Forwarded-For to bypass middleware
- **File:** `tests/integration/test_dashboard.py:12`
- **Issue:** `LAN_HEADERS = {"X-Forwarded-For": "127.0.0.1"}` relies on the same vulnerability described above to make tests pass. When the middleware is fixed, these tests will break (correctly) and will need to be updated to use a properly mocked client IP.

---

## Technical Debt

### In-memory pairing code state lost on restart
- **File:** `src/auth/pairing.py:35-36`
- **Issue:** `_active_codes` and `_generation_timestamps` are module-level dicts. A service restart during an active pairing session silently invalidates any outstanding code and resets the rate-limit counter. A user mid-pairing would see an unexplained failure.
- **Impact:** Low probability but confusing UX when it occurs.
- **Fix approach:** Persist to `~/.picframe/pairing_state.json` with TTL cleanup on load, or accept the limitation given the short 5-minute code lifetime.

### `remote_count` hardcoded to 0 on dashboard initial render
- **Files:** `src/dashboard/routes.py:280`, `src/api/routes/folders.py:185`
- **Issue:** The dashboard homepage passes `"remote_count": 0` to the template on initial page load, so the traffic light always shows amber until the first AJAX refresh (15s). The `sync_status` determination at line 254 also passes `0` as `remote_count`, meaning `determine_sync_status()` always returns `"idle"` instead of `"mismatch"` on the server-rendered page.
- **Impact:** Dashboard shows incorrect sync state for up to 15 seconds on every page load. Not a correctness issue for the AJAX-refreshed tab, but the initial render misleads.
- **Fix approach:** Either fire the async `rclone_count()` during initial render (with a timeout guard) or accept the 15-second stale-state window as intentional for performance.

### `SyncService` exposes private state via underscore attributes
- **File:** `src/services/status_service.py:75-77`, `src/api/routes/status.py:152`
- **Issue:** `sync_service._is_syncing` and `sync_service._current_source` are accessed directly from outside the class in two different files. This bypasses encapsulation and will require coordinated updates if the internal representation changes.
- **Fix approach:** Add `is_syncing` and `current_source` as public `@property` accessors on `SyncService`.

### `dashboard/routes.py` is a monolith (1,456 lines)
- **File:** `src/dashboard/routes.py`
- **Issue:** All dashboard route handlers, helper functions, Koofr validation, network info helpers, photo tools integration, backup integration, source management, and update logic are in a single file. This is the largest file in the project by a large margin and is difficult to navigate.
- **Impact:** High maintenance cost; hard to unit-test individual concerns.
- **Fix approach:** Extract helper modules: `src/dashboard/helpers/network.py`, `src/dashboard/helpers/config.py`, etc.

### `update_service.py` uses naive `datetime.now()` (no timezone)
- **File:** `src/services/update_service.py:267, 278, 285, 311`
- **Issue:** `calculate_next_check()` and `start_update_scheduler()` use `datetime.now()` without timezone, while `checked_at = datetime.now().isoformat()` at line 97 also omits timezone. Other datetime usage in the project (e.g. `jwt_handler.py`) correctly uses `datetime.now(timezone.utc)`. Mixed naive/aware datetimes can cause comparison errors.
- **Fix approach:** Replace `datetime.now()` with `datetime.now(timezone.utc)` throughout `update_service.py`.

### `subprocess.run()` used in dashboard helpers (blocking calls in async context)
- **Files:** `src/dashboard/routes.py:193`, `src/dashboard/routes.py:220`
- **Issue:** `_get_tailscale_ip()` and `_get_wifi_ssid()` use the synchronous `subprocess.run()` inside an async route handler. These calls block the event loop for up to 5 seconds if the subprocess hangs. Project standard is `asyncio.create_subprocess_exec()`.
- **Fix approach:** Convert to `asyncio.create_subprocess_exec()` or run in a thread executor.

### MQTT client passed but never used
- **File:** `src/services/display_service.py:48`, `src/services/display_service.py:211`
- **Issue:** `DisplayService.__init__` accepts an `mqtt_client` parameter and stores it as `self._mqtt`, but it is never used anywhere in the class. Line 211 has a `TODO: Publish to MQTT broker` comment. paho-mqtt is installed as a dependency but serves no current function.
- **Impact:** Dead dependency weight; potential confusion about what MQTT integration does.
- **Fix approach:** Either implement MQTT publishing or remove the parameter and dependency.

---

## Known Fragilities

### Sync concurrency lock is process-level only
- **File:** `src/services/sync_service.py:69`
- **Issue:** `self._is_syncing` is an in-memory boolean. If the API is restarted mid-sync (e.g. during an update apply), the flag resets to `False` while rclone may still be running in a child process. A subsequent sync call would spawn a second rclone process against the same local directory.
- **Safe modification:** Do not add concurrent sync triggers without understanding this race. The systemd sync timer mitigates frequency, but the API's `POST /sync` can be called at any time.

### Pi3D HTTP API fallback is silent
- **File:** `src/services/display_service.py` (switch_source logic)
- **Issue:** When Pi3D's HTTP API on port 9000 is unreachable, the display service falls back to a config-file write + service restart. The caller receives a success response in both cases, with no indication of which path was taken. A service restart takes ~5 seconds and has different UX (brief blank screen) vs. the seamless HTTP API path.
- **Impact:** Hard to diagnose display switching delays; no observability into which code path ran.

### `update_service.apply_update()` has no service restart
- **File:** `src/services/update_service.py:218-253`
- **Issue:** `apply_update()` runs `git pull` and returns. It does not restart `picframe-api.service`. The dashboard triggers a delayed self-restart via a separate mechanism (JavaScript 8-second countdown), but the API route itself does not ensure the service restarts if called programmatically or if the browser is closed.
- **Impact:** If the JS countdown is interrupted, the old code keeps running after a successful pull.

### `devices.json` updated on every authenticated request
- **File:** `src/storage/devices.py:145-158`
- **Issue:** `update_last_seen()` writes `devices.json` to disk on every API call from an authenticated mobile device. On a busy frame (15-second dashboard polling + any mobile app background calls), this generates constant file I/O. The file lock serializes all requests.
- **Impact:** Low on a single-device home frame; could degrade on frames with many paired devices or high polling rates.

### `get_settings()` `@lru_cache` requires manual `reload_settings()` calls
- **File:** `src/config/settings.py:122-138`
- **Issue:** Any code path that mutates config via `config_manager.set()` without calling `reload_settings()` afterward will leave the process with stale settings until restart. There is no automated invalidation. Several call sites exist; a missed `reload_settings()` is a silent bug.
- **Tracked pattern:** Documented in `CLAUDE.md` but not enforced programmatically.

---

## Architectural Weaknesses

### No separation between LAN dashboard API and mobile API for shared operations
- **Files:** `src/dashboard/routes.py`, `src/api/routes/`
- **Issue:** Operations like sync, source switching, and service restart are implemented in *both* dashboard routes and API routes. `status_service.py` consolidates read logic, but write/action logic is duplicated. If behavior needs to change (e.g. adding a confirmation step before restart), it must be updated in two places.
- **Fix approach:** Route all dashboard actions through the existing API routes internally, or extract shared action services analogous to `status_service.py`.

### Sync interval stored in config but timer is fixed at 15 minutes
- **File:** `~/.config/systemd/user/picframe-sync.timer` (on Pi), `src/config/settings.py`
- **Issue:** The `sync.interval` setting is configurable and displayed in the dashboard, but `systemd_service.update_sync_timer()` must be explicitly called to propagate changes to the actual systemd timer. The systemd timer was historically fixed at 15 minutes. It is now updateable via `update_sync_timer()`, but the gap between "config says X" and "timer fires at Y" still exists if the update path is not triggered.
- **Tracked:** `docs/PARKING_LOT.md` — Priority: Low (partial fix in place)

### `api_port` hardcoded to 8000 in dashboard render context
- **File:** `src/dashboard/routes.py:292`
- **Issue:** `"api_port": 8000` is a literal in the template context, not read from config or environment. If the port ever changes, this requires a code change rather than a config change.

### Phase 6 state split across two files
- **Files:** `/var/lib/picframe/state.yaml`, `~/.picframe/config.yaml`
- **Issue:** Setup state (`provisioned`, `koofr_configured`, `needs_setup`, `frame_name`) lives at `/var/lib/picframe/state.yaml` (requires sudo/root to write), while runtime config lives at `~/.picframe/config.yaml` (user-writable). `_is_koofr_configured()` in `dashboard/routes.py:75-113` must check three separate locations to determine if Koofr is set up. This multi-source check is fragile and order-dependent.

---

## Gaps / Unknowns

### Test coverage is thin and tests accept wide response code ranges
- **Files:** `tests/integration/test_api.py`, `tests/integration/test_dashboard.py`, `tests/unit/`
- **Issue:** Integration tests use broad assertions like `assert response.status_code in (200, 302, 303, 500)` which allow silent failures. There are no tests for: the middleware LAN restriction, contributor upload flow, photo tools operations, source switching, update apply, or any Phase 6 first-run paths. The unit test suite (`tests/unit/`) covers config and sync service basics only.
- **Impact:** Regressions in critical paths (sync, display switching, tools) will not be caught by the test suite.

### No test for the middleware spoofing vulnerability
- **File:** `tests/integration/test_dashboard.py`
- **Issue:** The test suite currently *relies on* the `X-Forwarded-For` header vulnerability to grant dashboard access (see `LAN_HEADERS`). There is no test verifying that a non-LAN IP without the header is correctly blocked, nor a test that the current unprotected dashboard routes (e.g. `POST /sync`) reject external IPs.

### rclone config file written to `/tmp` during Koofr credential validation
- **File:** `src/dashboard/routes.py:147-175`
- **Issue:** A temporary rclone config containing the Koofr password (in obscured form) is written to `/tmp`. It is cleaned up in a `finally` block. A crash or `proc.kill()` before the `finally` runs could leave the file on disk. The file is created with `0o600` permissions and the obscured password is not plaintext, limiting risk.
- **Residual risk:** Low, but worth noting if security audit is conducted.

### MQTT dependency installed but entirely unused
- **File:** `requirements.txt` (paho-mqtt), `src/services/display_service.py:48`
- **Unknown:** It is unclear whether MQTT integration is planned, deferred, or abandoned. The dependency adds ~1 MB and potential attack surface with no current benefit.

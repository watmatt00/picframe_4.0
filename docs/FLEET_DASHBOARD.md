# Fleet Health Dashboard — Technical Spec

Read-only overview of all Pi frames' health, served at `/fleet` by any Pi in the fleet.

---

## Hosting

New route in the existing FastAPI app. All Pis run the same code, so `/fleet` is available on every frame automatically. Server-side Python polls other Pis' `/dashboard/status` via Tailscale — no browser CORS issues, no new server.

---

## Key Research Findings

- `httpx>=0.26.0` already in `requirements.txt` — no new dependency
- `/dashboard/status` is NOT in `DASHBOARD_PATHS` in `middleware.py` — reachable from any IP already; inter-Pi polling needs no special auth
- `100.x.x.x` Tailscale IPs are trusted by `LANOnlyDashboardMiddleware` (in `LOCAL_PREFIXES`)
- New `/fleet` route must be added to `DASHBOARD_PATHS` so the fleet page and `/fleet/status` are LAN-only
- `FleetConfig` Pydantic model follows the established settings pattern

---

## Device List: Config YAML

Add a `fleet:` section to `~/.picframe/config.yaml` (and `config/config.example.yaml`):

```yaml
fleet:
  devices:
    - id: "tkframe"
      name: "tkframe"
      url: "http://tkframe.whale-ayu.ts.net:8000"
      branch: "dev"
    - id: "kframe"
      name: "kframe"
      url: "http://kframe.whale-ayu.ts.net:8000"
      branch: "main"
    - id: "mnbframe"
      name: "mnbframe"
      url: "http://mnbframe.whale-ayu.ts.net:8000"
      branch: "main"
```

---

## Files to Create

| File | Purpose |
|------|---------|
| `src/dashboard/fleet_devices.py` | Device polling logic (httpx, asyncio.gather, 5s timeout per device) |
| `src/dashboard/templates/fleet.html` | Standalone page — one card per device, no tabs |
| `src/dashboard/static/js/fleet.js` | Auto-refresh every 30s, vanilla JS, in-place card updates |

## Files to Modify

| File | Change |
|------|--------|
| `src/config/settings.py` | Add `FleetDeviceConfig` + `FleetConfig` models; add `fleet` field to `Settings` |
| `config/config.example.yaml` | Add `fleet:` section example |
| `src/dashboard/routes.py` | `GET /fleet` (HTML) and `GET /fleet/status` (JSON) |
| `src/api/middleware.py` | Add `"/fleet"` to `DASHBOARD_PATHS` |
| `src/dashboard/static/css/dashboard.css` | Append ~60 lines of fleet CSS |

---

## Settings Models

```python
# src/config/settings.py

class FleetDeviceConfig(BaseModel):
    id: str
    name: str
    url: str       # e.g. "http://tkframe.whale-ayu.ts.net:8000"
    branch: str = "main"

class FleetConfig(BaseModel):
    devices: list[FleetDeviceConfig] = Field(default_factory=list)

# Add to Settings class:
#   fleet: FleetConfig = Field(default_factory=FleetConfig)
```

---

## fleet_devices.py: Core Logic

```python
POLL_TIMEOUT = 5.0  # seconds — fast-fail for offline Pis

async def _poll_device(client, device, self_id) -> dict:
    try:
        resp = await client.get(f"{device.url}/dashboard/status", timeout=POLL_TIMEOUT)
        resp.raise_for_status()
        return {
            "id": device.id, "name": device.name, "branch": device.branch,
            "url": device.url, "is_self": device.id == self_id,
            "reachable": True, "status": resp.json(), "error": None,
        }
    except Exception as e:
        return {
            "id": device.id, "name": device.name, "branch": device.branch,
            "url": device.url, "is_self": device.id == self_id,
            "reachable": False, "status": None, "error": str(e),
        }

async def poll_all_devices() -> dict:
    settings = get_settings()
    self_id = settings.frame.id
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *[_poll_device(client, d, self_id) for d in settings.fleet.devices],
            return_exceptions=True,
        )
    # Coerce any stray BaseException (belt-and-suspenders alongside per-device try/except)
    coerced = []
    for i, r in enumerate(results):
        if isinstance(r, BaseException):
            d = settings.fleet.devices[i]
            coerced.append({"id": d.id, "name": d.name, "branch": d.branch,
                            "url": d.url, "is_self": d.id == self_id,
                            "reachable": False, "status": None, "error": str(r)})
        else:
            coerced.append(r)
    return {"devices": coerced, "polled_at": datetime.now(timezone.utc).isoformat()}
```

---

## Routes

```python
# src/dashboard/routes.py additions
from src.dashboard.fleet_devices import poll_all_devices

@router.get("/fleet", response_class=HTMLResponse)
async def fleet_dashboard(request: Request):
    settings = get_settings()
    return templates.TemplateResponse(request, "fleet.html", {
        "request": request,
        "frame_name": settings.frame.name,
        "frame_id": settings.frame.id,
    })

@router.get("/fleet/status")
async def get_fleet_status():
    return await poll_all_devices()
```

---

## /fleet/status Response Shape

```json
{
  "polled_at": "2026-05-09T12:00:00+00:00",
  "devices": [
    {
      "id": "tkframe",
      "name": "tkframe",
      "branch": "dev",
      "url": "http://tkframe.whale-ayu.ts.net:8000",
      "is_self": true,
      "reachable": true,
      "status": {
        "sync_status": "match",
        "local_count": 247,
        "remote_count": 247,
        "current_source": "koofr_main",
        "services": [{"name": "picframe", "active": true, "status": "running"}, ...],
        "storage_used": 15.2,
        "storage_total": 24.4,
        "storage_percent": 62.3,
        "last_sync": "2026-05-09 11:45:00",
        "last_restart": "2026-05-09 08:12:00",
        "wifi_connected": true
      },
      "error": null
    },
    {
      "id": "mnbframe",
      "name": "mnbframe",
      "branch": "main",
      "url": "http://mnbframe.whale-ayu.ts.net:8000",
      "is_self": false,
      "reachable": false,
      "status": null,
      "error": "timeout"
    }
  ]
}
```

---

## Per-Device Card Layout

Online frame:
```
┌─────────────────────────────────────────────┐
│ ● tkframe  [DEV]  [THIS FRAME]   Open ↗     │
├─────────────────────────────────────────────┤
│  🟢   ☁️ Cloud: 247    Display: ● RUNNING   │
│  ⚫   🖼️ Local:  247    API:     ● RUNNING   │
│  ⚫                                          │
│  💾 Storage ██████░░░░ 62% (15.2 / 24.4 GB)│
│  Last Sync: 2026-05-09 11:45                │
│  Last Restart: 2026-05-09 08:12             │
└─────────────────────────────────────────────┘
```

Offline frame:
```
┌─────────────────────────────────────────────┐
│ ○ mnbframe  [MAIN]                Open ↗    │
├─────────────────────────────────────────────┤
│ ⚠ Unreachable                               │
│ timeout                                      │
└─────────────────────────────────────────────┘
```

---

## fleet.js Pattern

```
DOMContentLoaded → loadFleetStatus() + setInterval(30s)
  └── fetch('/fleet/status')
        ├── first render → buildDeviceCard() per device → append to #fleet-grid
        └── subsequent  → updateDeviceCard() per device — in-place, no flicker

Traffic light severity logic (mirrors dashboard.js):
  sync_status === 'syncing'              → AMBER
  sync_status === 'error'               → RED
  local_count !== remote_count           → AMBER
  local_count === remote_count (& > 0)  → GREEN

Storage bar fill color:
  percent < 70  → green  (.ok)
  percent < 90  → amber  (.warn)
  percent >= 90 → red    (.error)

Header aggregate pill:
  all reachable, no errors → "OK"
  any unreachable or error → "ISSUES"
  mixed                    → "PARTIAL"
```

All user-visible strings pass through `escapeHtml()`.

---

## CSS Additions (appended to dashboard.css)

```css
/* Fleet Dashboard — ~60 lines */
.fleet-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 1.5rem; padding: 1.5rem 1.75rem 2.5rem; }
.fleet-loading { grid-column: 1 / -1; text-align: center; padding: 3rem; opacity: 0.6; }
.fleet-device-card { margin-bottom: 0; }
.fleet-device-title { display: flex; align-items: center; gap: 0.5rem; font-size: 1.1rem; font-weight: 650; }
.fleet-self-badge { font-size: 0.6rem; padding: 0.15rem 0.5rem; background: rgba(99,102,241,0.2); color: #a5b4fc; border: 1px solid rgba(99,102,241,0.4); }
.badge.branch-dev  { background: rgba(234,179,8,0.15); color: #fde68a; border: 1px solid rgba(234,179,8,0.4); }
.badge.branch-main { background: rgba(22,163,74,0.15);  color: #86efac; border: 1px solid rgba(22,163,74,0.4); }
.fleet-offline { color: #f87171; padding: 1rem 0 0.5rem; display: flex; flex-direction: column; gap: 0.25rem; }
.fleet-error-msg { font-size: 0.78rem; opacity: 0.8; }
.fleet-status-row { display: grid; grid-template-columns: auto 1fr; gap: 1rem; align-items: start; margin-top: 0.75rem; }
.fleet-traffic { width: 36px; height: 100px; }
.fleet-counts { display: flex; flex-direction: column; gap: 0.5rem; }
.fleet-services { display: grid; grid-template-columns: auto auto; column-gap: 0.5rem; row-gap: 0.2rem; font-size: 0.8rem; margin-top: 0.25rem; }
.fleet-storage { margin-top: 0.75rem; }
.fleet-storage-label { display: flex; justify-content: space-between; font-size: 0.75rem; opacity: 0.8; margin-bottom: 0.3rem; }
.fleet-storage-track { height: 6px; background: rgba(55,65,81,0.7); border-radius: 999px; overflow: hidden; }
.fleet-storage-fill { height: 100%; border-radius: 999px; transition: width 0.4s ease; }
.fleet-storage-fill.ok    { background: #22c55e; }
.fleet-storage-fill.warn  { background: #fbbf24; }
.fleet-storage-fill.error { background: #ef4444; }
.fleet-timestamps { display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; margin-top: 0.75rem; }
.fleet-timestamps .pill-block-value { font-size: 0.75rem; }
@media (max-width: 700px) {
  .fleet-grid { grid-template-columns: 1fr; padding: 1rem; }
  .fleet-status-row { grid-template-columns: 1fr; }
  .fleet-traffic { display: none; }
}
```

---

## Implementation Order

1. `src/api/middleware.py` — add `"/fleet"` to `DASHBOARD_PATHS` (security first — without it `/fleet` is public)
2. `src/config/settings.py` — add `FleetDeviceConfig` + `FleetConfig`; add `fleet` to `Settings`
3. `config/config.example.yaml` — add `fleet:` section
4. `src/dashboard/fleet_devices.py` — new polling module
5. `src/dashboard/routes.py` — add import + two routes
6. `src/dashboard/static/css/dashboard.css` — append fleet CSS
7. `src/dashboard/templates/fleet.html` — standalone template
8. `src/dashboard/static/js/fleet.js` — auto-refresh + card rendering

---

## Verification

1. Add `fleet:` section to `~/.picframe/config.yaml` on tkframe with the 3 devices
2. `systemctl --user restart picframe-api`
3. Browse to `http://192.168.102.210:8000/fleet`
4. Confirm 3 device cards render; tkframe shows "THIS FRAME" badge
5. Confirm 30s auto-refresh (watch "Last polled" timestamp update)
6. Confirm offline Pi shows "Unreachable" with error text, not a crash
7. Confirm `http://192.168.102.210:8000/fleet/status` returns JSON from LAN
8. Confirm `/fleet` returns 403 from a non-LAN IP (Funnel path)

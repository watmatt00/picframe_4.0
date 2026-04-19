# Testing
_Last updated: 2026-04-19_

## Summary
PicFrame 4.0 has 48 tests (all passing) split across unit and integration suites using pytest with pytest-asyncio. Test coverage is meaningful for auth and config modules but leaves large gaps in dashboard business logic, photo tools, and authenticated API happy paths.

## Framework & Tooling
- **Framework:** pytest 7.4+ with pytest-asyncio (`asyncio_mode = "auto"`)
- **Mocking:** `unittest.mock` (`patch`, `AsyncMock`, `MagicMock`)
- **HTTP testing:** FastAPI `TestClient` (synchronous wrapper)
- **No coverage tooling:** `pytest-cov` not in dev dependencies, no target configured

## Running Tests
```bash
.venv/bin/python -m pytest tests/               # all tests
.venv/bin/python -m pytest tests/unit/          # unit only
.venv/bin/python -m pytest tests/integration/   # integration only
```

## Test Structure
```
tests/
├── unit/
│   ├── test_auth.py          # JWT creation, validation, expiry, device storage
│   ├── test_config.py        # Config manager read/write, YAML persistence
│   └── test_sync.py          # Sync logic, rclone command construction
└── integration/
    ├── test_api.py           # API auth gates (401/403 responses), pairing flow
    └── test_dashboard.py     # Dashboard middleware (LAN header bypass), route availability
```

## Key Patterns
- Class-based test organization (`TestAuthRoutes`, `TestDashboardRoutes`)
- `tmp_path` fixture for isolated file system tests
- `patch()` at the call site (not import site)
- LAN header injection (`X-Forwarded-For: 192.168.1.1`) to bypass dashboard middleware in tests
- Wide `in (200, 404, 422)` status code assertions for Pi-specific routes that may not be reachable in CI

## Coverage Gaps
- **Dashboard business logic:** Entire `dashboard/routes.py` (Tools tab, source switching, sync trigger, Koofr setup) — no tests
- **Photo tools:** All of `photo_tools_service.py` — no tests
- **Backup service:** `backup_service.py` — no tests
- **Display service:** `display_service.py` — no tests
- **Update service:** `update_service.py` — no tests
- **Source manager:** `source_manager.py` — no tests
- **Authenticated API happy paths:** No test provisions a JWT token to exercise protected routes successfully
- **Pi3D integration:** No tests for HTTP API interaction on port 9000

## Gaps / Unknowns
- No CI pipeline configured — tests are run manually
- No coverage thresholds enforced

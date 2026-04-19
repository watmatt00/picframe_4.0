# Coding Conventions
_Last updated: 2026-04-19_

## Summary

PicFrame 4.0 is a Python 3.11+ FastAPI project that follows PEP 8 with type hints throughout. Code is organized into clear layers (API routes, services, storage, utils, config). Naming is consistent: snake_case for everything except Pydantic model classes. Ruff is the linter/formatter (line length 100, rules E/F/I/N/W/UP). All external subprocess calls use `asyncio.create_subprocess_exec()` — never `shell=True`. Module-level loggers are the standard pattern. f-strings are used everywhere.

---

## Naming Patterns

**Files:**
- All lowercase, underscores: `sync_service.py`, `jwt_handler.py`, `photo_tools_service.py`
- Route files match their resource: `status.py`, `devices.py`, `pairing.py`
- Service files end in `_service.py`: `sync_service.py`, `status_service.py`, `systemd_service.py`
- Storage files are short nouns: `devices.py`, `sources.py`, `invites.py`

**Classes:**
- PascalCase for all classes: `SyncService`, `TokenClaims`, `LANOnlyDashboardMiddleware`
- Pydantic models use descriptive noun phrases: `FrameStatus`, `SyncResult`, `PairingRequest`, `RcloneResult`
- Config sub-models append `Config`: `FrameConfig`, `DisplayConfig`, `SyncConfig`

**Functions:**
- snake_case: `get_settings()`, `verify_token()`, `generate_pairing_code()`
- Private helpers prefixed with `_`: `_validate_remote()`, `_validate_path()`, `_is_safe_flag()`, `_parse_transferred()`, `_map_service_status()`, `_get_service_status()`
- FastAPI dependency functions use `get_` or `require_` prefix: `get_current_device()`, `require_admin()`, `require_contributor()`

**Variables:**
- snake_case throughout
- Module-level singletons are lowercase: `sync_service`, `device_storage`, `source_manager`, `config_manager`
- Global constants are SCREAMING_SNAKE_CASE: `DEFAULT_EXPIRY_DAYS`, `SECRET_PATH`, `PICTURES_PATH`, `LOCAL_PREFIXES`

**Enums:**
- Class name PascalCase, members SCREAMING_SNAKE_CASE: `SyncStatus.MATCH`, `SyncStatus.ERROR`

---

## Code Style

**Formatter/Linter:** Ruff (`pyproject.toml`)
- Line length: 100 characters
- Target Python: 3.11+
- Selected rules: `E` (pycodestyle errors), `F` (pyflakes), `I` (isort), `N` (pep8-naming), `W` (pycodestyle warnings), `UP` (pyupgrade)
- Config: `pyproject.toml` `[tool.ruff]` section

**Type Hints:**
- Required on all function signatures (parameters and return types)
- Uses Python 3.10+ union syntax: `str | None` (not `Optional[str]`) in newer code; older code still uses `Optional[str]` from `typing`
- `list[str]` not `List[str]` (pyupgrade rule enforces modern generics)

**String Formatting:**
- f-strings exclusively — no `.format()` or `%` formatting

---

## Import Organization

Ruff's `I` ruleset (isort) enforces ordering. Observed pattern:

1. Standard library: `asyncio`, `logging`, `os`, `re`, `pathlib`, etc.
2. Third-party: `fastapi`, `pydantic`, `jwt`, `yaml`, `httpx`
3. First-party (project): `src.*` imports

Within each group: alphabetical order.

**Path style:** Always absolute from project root using `src.*`:
```python
from src.api.dependencies import require_admin
from src.config.settings import get_settings, reload_settings
from src.services.sync_service import sync_service
```

**Lazy imports:** Used occasionally for optional/heavy dependencies loaded at request time:
```python
from PIL import Image  # noqa: PLC0415 — lazy import, Pillow is optional at startup
```

---

## Module Structure Pattern

Each module follows this layout:
1. Module docstring (always present)
2. Standard library imports
3. Third-party imports
4. First-party imports
5. Module-level logger: `logger = logging.getLogger(__name__)`
6. Constants
7. Classes/functions

---

## Pydantic Model Conventions

- All request/response shapes are Pydantic `BaseModel` subclasses
- Fields use `Field(...)` with `description=` for documentation
- Custom serializers use `@field_serializer` decorator
- Settings use `pydantic-settings` `BaseSettings` with `env_prefix="PICFRAME_"` and `env_nested_delimiter="__"`
- `model_dump_json()` / `model_validate_json()` used for serialization (Pydantic v2 API)

---

## Error Handling

**API routes:** Raise `HTTPException` with explicit status codes from `fastapi.status`:
```python
raise HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Missing authorization header",
    headers={"WWW-Authenticate": "Bearer"},
)
```

**Service layer:** Returns result objects (e.g., `SyncResult`, `RcloneResult`) with `success: bool` and `error: Optional[str]`. Does not raise to callers unless exceptional (concurrent sync raises `RuntimeError`).

**Dashboard routes:** Heavy use of `except Exception as e` with `logger.error()`/`logger.warning()`, returning HTTP 500 or a JSON error response. This is the most permissive exception handling in the codebase — acceptable for a UI layer that must degrade gracefully on a Pi where systemd/rclone may be unavailable.

**Validation layer:** Pydantic models and explicit validator functions (`_validate_remote()`, `_validate_path()`) enforce input constraints before any subprocess call. `ValueError` is raised for invalid config schema inputs.

**Anti-pattern to avoid:** `except Exception` without binding (`as e`) loses error detail. `dashboard/routes.py` has several bare `except Exception:` (no `as e`) where the error is silently swallowed — not the standard pattern.

---

## Logging

**Setup:** Each module creates its own logger:
```python
logger = logging.getLogger(__name__)
```

**Levels in use:**
- `logger.info()` — normal operations: sync start/complete, device added/removed, config saved
- `logger.warning()` — degraded but recoverable: failed to read IP, sync stamp update failure
- `logger.error()` — operation failures: sync failed, config read/write failed, Koofr validation error
- `logger.debug()` — not consistently used; no structured debug logging observed

**Format pattern (f-strings):**
```python
logger.info(f"Starting sync for source '{source_id}'")
logger.error(f"Sync failed for '{source_id}': {sync_result.error}")
logger.warning(f"Failed to count remote files: {e}")
```

Includes quotes around identifiers and colon-separated detail. No timestamp in log calls (delegated to logging configuration at runtime).

---

## Subprocess / External Commands

**Mandatory pattern** — always use `asyncio.create_subprocess_exec()` with explicit argument list:
```python
proc = await asyncio.create_subprocess_exec(
    "systemctl", "--user", "is-active", service_name,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
stdout, _ = await proc.communicate()
```

Never use `shell=True`. Never interpolate user input into command arguments without prior validation through `_validate_remote()` / `_validate_path()` / `_is_safe_flag()`.

---

## Settings Cache Pattern

`get_settings()` uses `@lru_cache`. After any `config_manager.set()` or `config_manager.update()` call, `reload_settings()` **must** be called to clear the cache:
```python
from src.config.settings import get_settings, reload_settings

config_manager.set("display.current_source", source_id)
reload_settings()  # Required — clears lru_cache
```

---

## Comments

- Module-level docstrings present on all files describing purpose and exported names
- Function/method docstrings present on public functions, using Google-style Args/Returns format
- Inline comments used for non-obvious logic (e.g., Tailscale IP middleware reasoning)
- `# TODO:` used sparingly; one confirmed instance in `jwt_handler.py` for revocation list
- `# noqa:` used only for intentional lazy imports

---

## Gaps / Unknowns

- No pre-commit hook configuration found — Ruff may not be enforced automatically before commits
- No `mypy` or similar static type checker configured; type hints are unenforced at runtime beyond Pydantic
- `dashboard/routes.py` is a 1400+ line monolith — conventions are harder to enforce consistently at that scale, and it shows (more bare `except Exception:` than elsewhere)
- No consistent async vs. sync pattern in dashboard routes — some handlers are `async def`, some are sync; mixing is allowed by FastAPI but not documented as intentional

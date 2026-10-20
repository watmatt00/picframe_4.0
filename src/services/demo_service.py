"""
WanderWall - Demo Mode Service (PL-015).

Reusable pairing codes for an App Store reviewer. Demo mode only works on a frame
where `demo.allowed: true` was set by hand, and turns itself off 14 days after it
was turned on (or after new codes were made). When it ends, every phone that
paired with a demo code is revoked.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from src.auth.pairing import generate_demo_codes
from src.config.manager import config_manager
from src.config.settings import get_settings, reload_settings
from src.storage.devices import device_storage
from src.utils.logging import log_auth_event

logger = logging.getLogger(__name__)

DEMO_DURATION = timedelta(days=14)
MAX_PREVIOUS_CODES = 5


class DemoNotAllowedError(Exception):
    """Demo mode was requested on a frame without `demo.allowed: true`."""


def _save(updates: dict[str, Any]):
    """Write demo settings to config.yaml and refresh the settings cache."""
    config_manager.update({"demo": updates})
    reload_settings()


def _require_allowed():
    """Raise DemoNotAllowedError unless this frame allows demo mode."""
    if not get_settings().demo.allowed:
        raise DemoNotAllowedError("Demo mode is not allowed on this frame (demo.allowed is false)")


def enable_demo(now: Optional[datetime] = None) -> dict[str, Any]:
    """
    Turn demo mode on for 14 days, keeping existing codes (or making the first ones).

    Returns:
        demo_status()
    """
    _require_allowed()
    now = now or datetime.now(timezone.utc)
    demo = get_settings().demo
    updates: dict[str, Any] = {
        "enabled": True,
        "expires_at": (now + DEMO_DURATION).isoformat(),
    }
    if not demo.admin_code or not demo.contributor_code:
        updates["admin_code"], updates["contributor_code"] = generate_demo_codes()
    _save(updates)
    logger.info("Demo mode enabled")
    log_auth_event("DEMO_ENABLE", success=True, details={"expires": updates["expires_at"]})
    return demo_status(now)


def disable_demo(reason: str = "manual") -> int:
    """
    Turn demo mode off and revoke every demo-paired device. Codes are kept.

    Args:
        reason: "manual", "expired" or "not_allowed" (logged)

    Returns:
        Number of demo devices revoked
    """
    _save({"enabled": False})
    revoked = device_storage.remove_demo_devices()
    logger.info(f"Demo mode disabled ({reason}); revoked {revoked} demo device(s)")
    log_auth_event("DEMO_DISABLE", success=True, details={"reason": reason, "revoked": revoked})
    return revoked


def regenerate_demo_codes(now: Optional[datetime] = None) -> dict[str, Any]:
    """
    Replace both codes and restart the 14 days. Already-paired demo phones stay paired.

    The replaced codes are kept so they get the "expired" message rather than "invalid".

    Returns:
        demo_status()
    """
    _require_allowed()
    now = now or datetime.now(timezone.utc)
    demo = get_settings().demo
    old = [c for c in (demo.admin_code, demo.contributor_code) if c]
    admin_code, contributor_code = generate_demo_codes()
    _save({
        "enabled": True,
        "admin_code": admin_code,
        "contributor_code": contributor_code,
        "expires_at": (now + DEMO_DURATION).isoformat(),
        "previous_codes": (old + demo.previous_codes)[:MAX_PREVIOUS_CODES],
    })
    logger.info("Demo codes regenerated")
    log_auth_event("DEMO_REGENERATE", success=True)
    return demo_status(now)


def expire_if_due(now: Optional[datetime] = None) -> bool:
    """
    End demo mode once its 14 days are up, or if `allowed` was turned off by hand.

    Cheap when demo mode is off (cached settings only), so it's safe to call per request.

    Returns:
        True if demo mode was ended by this call
    """
    demo = get_settings().demo
    if not demo.enabled:
        return False
    now = now or datetime.now(timezone.utc)
    if not demo.allowed:
        disable_demo("not_allowed")
        return True
    if demo.expires_at is None or now >= demo.expires_at:
        disable_demo("expired")
        return True
    return False


def demo_status(now: Optional[datetime] = None) -> dict[str, Any]:
    """
    Demo mode state for the dashboard.

    Returns:
        allowed, enabled, both codes, expires_at (ISO), days_left and demo_devices
    """
    demo = get_settings().demo
    now = now or datetime.now(timezone.utc)
    days_left = None
    if demo.enabled and demo.expires_at:
        # Round up: 13 days 2 hours left reads as "14 days left"
        remaining = demo.expires_at - now
        days_left = max(0, -(-remaining // timedelta(days=1)))
    return {
        "allowed": demo.allowed,
        "enabled": demo.enabled,
        "admin_code": demo.admin_code if demo.allowed else "",
        "contributor_code": demo.contributor_code if demo.allowed else "",
        "expires_at": demo.expires_at.isoformat() if demo.expires_at else None,
        "days_left": days_left,
        "demo_devices": device_storage.count_demo_devices(),
    }

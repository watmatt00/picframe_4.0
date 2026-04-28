"""
PicFrame 4.0 - Party Mode Service.

Enables/disables party mode: stops cloud sync and WiFi watchdog so the
frame runs as a standalone local slideshow.
"""

import asyncio
import logging
from pathlib import Path

from src.services.systemd_service import update_sync_timer

logger = logging.getLogger(__name__)

_WATCHDOG_UNIT = Path("/etc/systemd/system/picframe-watchdog.service")


async def _run_sudo(*args: str) -> bool:
    """Run a sudo command. Returns True on success; logs and returns False on failure."""
    proc = await asyncio.create_subprocess_exec(
        "sudo", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.warning(f"sudo {' '.join(args)} failed: {stderr.decode().strip()}")
        return False
    return True


async def _run_user(*args: str) -> bool:
    """Run a user-level systemctl command. Returns True on success."""
    proc = await asyncio.create_subprocess_exec(
        "systemctl", "--user", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.warning(f"systemctl --user {' '.join(args)} failed: {stderr.decode().strip()}")
        return False
    return True


async def enable_party() -> dict:
    """
    Enable party mode: stop + disable watchdog (if installed) and stop sync timer.

    Returns a dict with ok, watchdog_installed, watchdog_ok, sync_ok.
    """
    watchdog_installed = _WATCHDOG_UNIT.exists()
    watchdog_ok = True

    if watchdog_installed:
        await _run_sudo("systemctl", "stop", "picframe-watchdog.service")
        watchdog_ok = await _run_sudo("systemctl", "disable", "picframe-watchdog.service")
        # Clear Phase 6 needs_setup flag so watchdog won't trigger hotspot on restart
        await _run_sudo("picframe-config", "--clear-setup")
        logger.info("Party mode: watchdog stopped and disabled")
    else:
        logger.info("Party mode: watchdog not installed, skipping")

    sync_ok = await _run_user("stop", "picframe-sync.timer")
    logger.info("Party mode: sync timer stopped")

    return {
        "ok": watchdog_ok and sync_ok,
        "watchdog_installed": watchdog_installed,
        "watchdog_ok": watchdog_ok,
        "sync_ok": sync_ok,
    }


async def disable_party(sync_interval: int) -> dict:
    """
    Disable party mode: re-enable watchdog (if installed) and restore sync timer.

    Args:
        sync_interval: Seconds between syncs to restore (from settings.sync.interval).

    Returns a dict with ok, watchdog_installed, watchdog_ok, sync_ok.
    """
    watchdog_installed = _WATCHDOG_UNIT.exists()
    watchdog_ok = True

    if watchdog_installed:
        await _run_sudo("systemctl", "enable", "picframe-watchdog.service")
        watchdog_ok = await _run_sudo("systemctl", "start", "picframe-watchdog.service")
        logger.info("Party mode: watchdog enabled and started")
    else:
        logger.info("Party mode: watchdog not installed, skipping")

    sync_ok = await update_sync_timer(sync_interval)
    logger.info(f"Party mode: sync timer restored (interval={sync_interval}s)")

    return {
        "ok": watchdog_ok and sync_ok,
        "watchdog_installed": watchdog_installed,
        "watchdog_ok": watchdog_ok,
        "sync_ok": sync_ok,
    }

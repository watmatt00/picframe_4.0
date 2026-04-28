"""
PicFrame 4.0 - Party Mode Service.

Enables/disables party mode: stops cloud sync and WiFi watchdog so the
frame runs as a standalone local slideshow.

Requires install_setup.sh to have run, which installs:
  - /etc/polkit-1/rules.d/50-picframe.rules  (allows systemctl via D-Bus)
  - state.yaml group-writable by sudo group   (for clear-setup)
"""

import asyncio
import logging
import os
from pathlib import Path

import yaml

from src.services.systemd_service import update_sync_timer

logger = logging.getLogger(__name__)

_WATCHDOG_UNIT = Path("/etc/systemd/system/picframe-watchdog.service")
_STATE_FILE = Path("/var/lib/picframe/state.yaml")


async def _systemctl(*args: str) -> bool:
    """Run a system-level systemctl command (via polkit, no sudo). Returns True on success."""
    proc = await asyncio.create_subprocess_exec(
        "systemctl", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.warning(f"systemctl {' '.join(args)} failed: {stderr.decode().strip()}")
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


def _clear_setup_flag() -> bool:
    """
    Clear the Phase 6 needs_setup flag in state.yaml so the watchdog
    won't trigger hotspot mode on the next reboot.

    Requires state.yaml to be group-writable (set by install_setup.sh).
    """
    if not _STATE_FILE.exists():
        return True
    try:
        state = yaml.safe_load(_STATE_FILE.read_text()) or {}
        state["needs_setup"] = False
        state["setup_mode_reason"] = None
        tmp = _STATE_FILE.with_suffix(".tmp")
        tmp.write_text(yaml.safe_dump(state, default_flow_style=False))
        os.replace(tmp, _STATE_FILE)
        return True
    except Exception as e:
        logger.warning(f"Could not clear needs_setup flag: {e}")
        return False


async def enable_party() -> dict:
    """
    Enable party mode: stop + disable watchdog (if installed) and stop sync timer.

    Returns a dict with ok, watchdog_installed, watchdog_ok, sync_ok.
    """
    watchdog_installed = _WATCHDOG_UNIT.exists()
    watchdog_ok = True

    if watchdog_installed:
        await _systemctl("stop", "picframe-watchdog.service")
        watchdog_ok = await _systemctl("disable", "picframe-watchdog.service")
        _clear_setup_flag()
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
        await _systemctl("enable", "picframe-watchdog.service")
        watchdog_ok = await _systemctl("start", "picframe-watchdog.service")
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

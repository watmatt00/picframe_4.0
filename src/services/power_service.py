"""
PicFrame 4.0 - Reboot Frame (PL-142).

The API runs with NoNewPrivileges=true, so it can't sudo. `systemctl reboot`
goes through logind over D-Bus instead, which install_setup.sh's polkit rule
allows for the sudo group. The reboot starts a few seconds after the request,
so the caller gets its answer first.
"""

import asyncio
import logging
from pathlib import Path

from src.utils.logging import log_auth_event

logger = logging.getLogger(__name__)

POLKIT_RULE = Path("/etc/polkit-1/rules.d/50-picframe.rules")
REBOOT_DELAY_SECONDS = 3

# Keeps the scheduled reboot task referenced so it isn't garbage-collected
_pending: set[asyncio.Task] = set()

NOT_SET_UP_MESSAGE = (
    "Reboot isn't set up on this frame yet. "
    "Run: sudo bash scripts/setup/install_setup.sh"
)


def reboot_available() -> bool:
    """True if the polkit rule that lets the API reboot the frame is installed."""
    try:
        return "org.freedesktop.login1.reboot" in POLKIT_RULE.read_text()
    except OSError:
        return False


async def _reboot_after_delay() -> None:
    """Wait, then ask logind to reboot; log the reason if it refuses."""
    await asyncio.sleep(REBOOT_DELAY_SECONDS)
    proc = await asyncio.create_subprocess_exec(
        "systemctl", "reboot",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error(f"Reboot failed: systemctl reboot exited {proc.returncode}: {stderr.decode().strip()}")


def schedule_reboot(requested_by: str, ip: str | None = None) -> None:
    """
    Reboot the frame in REBOOT_DELAY_SECONDS.

    Args:
        requested_by: Who asked (device name, or "dashboard"), for the logs
        ip: Client IP for the security log
    """
    logger.warning(f"Reboot requested by {requested_by}; rebooting in {REBOOT_DELAY_SECONDS}s")
    log_auth_event("REBOOT", success=True, details={"requested_by": requested_by}, ip=ip)
    task = asyncio.create_task(_reboot_after_delay())
    _pending.add(task)
    task.add_done_callback(_pending.discard)

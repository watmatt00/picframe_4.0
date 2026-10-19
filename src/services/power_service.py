"""
PicFrame 4.0 - Reboot Frame (PL-142).

The API runs with NoNewPrivileges=true, so it can't sudo. `systemctl reboot`
goes through logind over D-Bus instead, which install_setup.sh's polkit rule
allows for the sudo group. The reboot starts a few seconds after the request,
so the caller gets its answer first.
"""

import asyncio
import logging
from src.utils.logging import log_auth_event

logger = logging.getLogger(__name__)

# logind's own answer to "may this user reboot without a password?" ("yes",
# "challenge", "no", "na"). The polkit rules folder isn't readable by the API user,
# so asking logind is the only reliable check.
CAN_REBOOT_CMD = (
    "busctl", "call", "org.freedesktop.login1", "/org/freedesktop/login1",
    "org.freedesktop.login1.Manager", "CanReboot",
)
REBOOT_DELAY_SECONDS = 3

# Keeps the scheduled reboot task referenced so it isn't garbage-collected
_pending: set[asyncio.Task] = set()

NOT_SET_UP_MESSAGE = (
    "Reboot isn't set up on this frame yet. "
    "Run: sudo bash scripts/setup/install_setup.sh"
)


async def reboot_available() -> bool:
    """True if logind lets this user reboot without a password (install_setup.sh's polkit rule)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *CAN_REBOOT_CMD,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)
    except (OSError, asyncio.TimeoutError) as e:
        logger.warning(f"Couldn't ask logind whether reboot is allowed: {e}")
        return False
    answer = stdout.decode().strip()
    if proc.returncode != 0 or answer != 's "yes"':
        logger.info(f"Reboot not available: CanReboot answered {answer or stderr.decode().strip()!r}")
        return False
    return True


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

"""
PicFrame 4.0 - Sleep Mode Scheduler.

Background asyncio task that stops/starts the picframe display service
and controls HDMI power according to a configured sleep/wake schedule.
"""

import asyncio
import logging
from datetime import datetime, timedelta, time as dtime

from src.config.settings import get_settings
from src.services.systemd_service import systemd_service

logger = logging.getLogger(__name__)

# Runtime sleep state — set on scheduler startup and toggled at each event
_is_sleeping: bool = False


def is_sleeping() -> bool:
    """Return True if the scheduler has put the frame to sleep."""
    return _is_sleeping


def _parse_hhmm(value: str) -> dtime:
    """Parse 'HH:MM' into a datetime.time object."""
    h, m = value.split(":")
    return dtime(int(h), int(m))


def _in_sleep_window(sleep_time: str, wake_time: str) -> bool:
    """
    Return True if the current wall-clock time is inside the sleep window.

    Handles overnight wrapping (e.g. sleep 22:00, wake 07:00).
    """
    now = datetime.now().time().replace(second=0, microsecond=0)
    sleep = _parse_hhmm(sleep_time)
    wake = _parse_hhmm(wake_time)
    if sleep == wake:
        return False
    if sleep > wake:
        # Overnight window: sleeping from 22:00 to 07:00 next day
        return now >= sleep or now < wake
    # Same-day window: sleeping from 13:00 to 15:00
    return sleep <= now < wake


def _seconds_until(target: dtime) -> float:
    """Return seconds from now until the next occurrence of target time (today or tomorrow)."""
    now = datetime.now()
    candidate = now.replace(hour=target.hour, minute=target.minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return (candidate - now).total_seconds()


def _next_event(sleep_time: str, wake_time: str) -> tuple[float, str]:
    """
    Return (seconds_to_wait, event_name) for the next scheduled sleep or wake event.
    event_name is 'sleep' or 'wake'.
    """
    sleep = _parse_hhmm(sleep_time)
    wake = _parse_hhmm(wake_time)
    secs_to_sleep = _seconds_until(sleep)
    secs_to_wake = _seconds_until(wake)
    if secs_to_sleep <= secs_to_wake:
        return secs_to_sleep, "sleep"
    return secs_to_wake, "wake"


async def _hdmi_power(on: bool) -> None:
    """Toggle HDMI output via vcgencmd display_power."""
    value = "1" if on else "0"
    try:
        proc = await asyncio.create_subprocess_exec(
            "vcgencmd", "display_power", value,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
    except Exception as e:
        logger.warning(f"vcgencmd display_power {value} failed: {e}")


async def _do_sleep() -> None:
    """Stop picframe and cut HDMI power."""
    global _is_sleeping
    logger.info("Sleep mode: stopping picframe and cutting HDMI power")
    await systemd_service.stop("picframe")
    await _hdmi_power(False)
    _is_sleeping = True


async def _do_wake() -> None:
    """Restore HDMI power and start picframe."""
    global _is_sleeping
    logger.info("Sleep mode: restoring HDMI power and starting picframe")
    await _hdmi_power(True)
    await systemd_service.start("picframe")
    _is_sleeping = False


async def start_sleep_scheduler() -> None:
    """
    Background task: enforce sleep/wake schedule.

    Reads settings on every loop iteration so changes take effect without
    restarting the API. When sleep is disabled mid-sleep the frame wakes
    immediately.
    """
    global _is_sleeping
    try:
        while True:
            settings = get_settings()
            cfg = settings.sleep

            if not cfg.enabled:
                # Sleep mode is off — wake the frame if we put it to sleep
                if _is_sleeping:
                    logger.info("Sleep mode disabled while sleeping — waking frame")
                    await _do_wake()
                await asyncio.sleep(60)
                continue

            in_window = _in_sleep_window(cfg.sleep_time, cfg.wake_time)

            # Enforce current state on startup or after config change
            if in_window and not _is_sleeping:
                await _do_sleep()
            elif not in_window and _is_sleeping:
                await _do_wake()

            # Sleep until the next boundary crossing
            wait_secs, next_event = _next_event(cfg.sleep_time, cfg.wake_time)
            logger.debug(f"Sleep scheduler: next event '{next_event}' in {wait_secs:.0f}s")

            # Re-check settings at least every 60 s so config changes are picked up promptly
            await asyncio.sleep(min(wait_secs, 60))

    except asyncio.CancelledError:
        logger.info("Sleep scheduler cancelled")
    except Exception as e:
        logger.error(f"Sleep scheduler error: {e}", exc_info=True)
        await asyncio.sleep(60)

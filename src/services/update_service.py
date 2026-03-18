"""
PicFrame 4.0 - Update Service.

Checks for available updates from GitHub by comparing local git commit vs remote.
Provides a background scheduler for automatic periodic checks.
"""

import asyncio
import calendar
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.config.settings import get_settings, reload_settings
from src.config.manager import config_manager

logger = logging.getLogger(__name__)

# Path to the git repo on the Pi
REPO_PATH = Path.home() / "picframe_4.0"

# Background scheduler task reference
_scheduler_task: Optional[asyncio.Task] = None


def get_repo_path() -> Path:
    """Get the path to the git repository."""
    return REPO_PATH


async def check_for_updates(repo_path: Optional[Path] = None) -> dict:
    """
    Check for available updates by comparing local HEAD vs remote.

    Runs git fetch then compares HEAD vs @{u}.

    Args:
        repo_path: Path to the git repo. Defaults to ~/picframe_4.0.

    Returns:
        dict with keys: up_to_date, local_commit, remote_commit, checked_at, error
    """
    if repo_path is None:
        repo_path = get_repo_path()

    checked_at = datetime.now().isoformat()

    try:
        # Run git fetch
        fetch_proc = await asyncio.create_subprocess_exec(
            "git", "-C", str(repo_path), "fetch", "--quiet",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, fetch_stderr = await asyncio.wait_for(fetch_proc.communicate(), timeout=30)

        if fetch_proc.returncode != 0:
            error = fetch_stderr.decode().strip() or "git fetch failed"
            logger.warning(f"git fetch failed: {error}")
            return {
                "up_to_date": None,
                "local_commit": None,
                "remote_commit": None,
                "checked_at": checked_at,
                "error": f"git fetch failed: {error}",
            }

        # Get local HEAD short hash
        local_proc = await asyncio.create_subprocess_exec(
            "git", "-C", str(repo_path), "rev-parse", "--short", "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        local_stdout, _ = await local_proc.communicate()
        local_commit = local_stdout.decode().strip()

        # Get remote tracking branch short hash
        remote_proc = await asyncio.create_subprocess_exec(
            "git", "-C", str(repo_path), "rev-parse", "--short", "@{u}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        remote_stdout, remote_stderr = await remote_proc.communicate()

        if remote_proc.returncode != 0:
            error = remote_stderr.decode().strip() or "No upstream configured"
            logger.warning(f"Could not get remote commit: {error}")
            return {
                "up_to_date": None,
                "local_commit": local_commit,
                "remote_commit": None,
                "checked_at": checked_at,
                "error": f"Could not get remote: {error}",
            }

        remote_commit = remote_stdout.decode().strip()
        up_to_date = local_commit == remote_commit

        return {
            "up_to_date": up_to_date,
            "local_commit": local_commit,
            "remote_commit": remote_commit,
            "checked_at": checked_at,
            "error": None,
        }

    except asyncio.TimeoutError:
        logger.error("git fetch timed out")
        return {
            "up_to_date": None,
            "local_commit": None,
            "remote_commit": None,
            "checked_at": checked_at,
            "error": "git fetch timed out",
        }
    except Exception as e:
        logger.error(f"Update check failed: {e}")
        return {
            "up_to_date": None,
            "local_commit": None,
            "remote_commit": None,
            "checked_at": checked_at,
            "error": str(e),
        }


def save_check_result(result: dict) -> None:
    """
    Save the update check result to config.

    Args:
        result: Result dict from check_for_updates()
    """
    config_manager.set("updates.last_checked", result["checked_at"])

    if result.get("error"):
        config_manager.set("updates.last_result", "error")
        config_manager.set("updates.available_commit", None)
    elif result.get("up_to_date") is True:
        config_manager.set("updates.last_result", "up_to_date")
        config_manager.set("updates.available_commit", None)
    elif result.get("up_to_date") is False:
        config_manager.set("updates.last_result", "update_available")
        config_manager.set("updates.available_commit", result.get("remote_commit"))

    reload_settings()


def calculate_next_check(frequency: str, day: int, check_time: str) -> datetime:
    """
    Calculate the next scheduled check datetime.

    Args:
        frequency: "monthly" or "weekly"
        day: 1-28 for monthly; 0-6 (Mon=0) for weekly
        check_time: "HH:MM" string

    Returns:
        Next datetime to run the check
    """
    now = datetime.now()

    # Parse check_time
    try:
        hour, minute = [int(x) for x in check_time.split(":")]
    except (ValueError, AttributeError):
        hour, minute = 2, 0

    if frequency == "monthly":
        # Find next occurrence of day-of-month at check_time
        try:
            candidate = now.replace(day=day, hour=hour, minute=minute, second=0, microsecond=0)
        except ValueError:
            candidate = None

        if candidate is None or candidate <= now:
            # Advance to next month
            if now.month == 12:
                next_month_dt = now.replace(year=now.year + 1, month=1)
            else:
                next_month_dt = now.replace(month=now.month + 1)

            try:
                candidate = next_month_dt.replace(day=day, hour=hour, minute=minute, second=0, microsecond=0)
            except ValueError:
                # Day doesn't exist in that month — use last day
                last_day = calendar.monthrange(next_month_dt.year, next_month_dt.month)[1]
                candidate = next_month_dt.replace(day=last_day, hour=hour, minute=minute, second=0, microsecond=0)

        return candidate

    else:  # weekly
        # day is 0-6 (Mon=0)
        days_ahead = day - now.weekday()
        if days_ahead < 0:
            days_ahead += 7

        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=days_ahead)

        if candidate <= now:
            candidate += timedelta(weeks=1)

        return candidate


async def start_update_scheduler() -> None:
    """
    Background task that runs scheduled update checks.

    Reads schedule config on each iteration, calculates next run time,
    sleeps until then, then runs the check.
    """
    logger.info("Update scheduler started")

    while True:
        try:
            settings = get_settings()
            updates = settings.updates

            if not updates.auto_check:
                # Re-check schedule in 1 hour
                await asyncio.sleep(3600)
                continue

            next_check = calculate_next_check(
                frequency=updates.frequency,
                day=updates.day,
                check_time=updates.check_time,
            )

            wait_seconds = (next_check - datetime.now()).total_seconds()
            if wait_seconds > 0:
                logger.info(f"Next update check scheduled for {next_check.isoformat()}")
                await asyncio.sleep(wait_seconds)

            # Run the check
            logger.info("Running scheduled update check")
            result = await check_for_updates()
            save_check_result(result)

            if result.get("error"):
                logger.warning(f"Scheduled update check failed: {result['error']}")
            elif result.get("up_to_date") is False:
                logger.info(f"Update available: remote commit {result.get('remote_commit')}")
            else:
                logger.info("System is up to date")

        except asyncio.CancelledError:
            logger.info("Update scheduler cancelled")
            return
        except Exception as e:
            logger.error(f"Update scheduler error: {e}")
            await asyncio.sleep(3600)  # Wait 1 hour before retry


async def get_local_commit(repo_path: Optional[Path] = None) -> Optional[str]:
    """
    Get the current local HEAD short hash without fetching.

    Args:
        repo_path: Path to the git repo. Defaults to ~/picframe_4.0.

    Returns:
        Short commit hash string or None on error
    """
    if repo_path is None:
        repo_path = get_repo_path()

    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", str(repo_path), "rev-parse", "--short", "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            return stdout.decode().strip()
    except Exception as e:
        logger.warning(f"Failed to get local commit: {e}")

    return None

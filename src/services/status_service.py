"""
PicFrame 4.0 - Status Service.

Shared status logic used by both API and dashboard routes.
Consolidates source resolution, photo counting, sync status,
and disk capacity calculations.
"""

import asyncio
import logging
import shutil
import time
from pathlib import Path
from typing import Optional

from src.config.settings import get_settings
from src.services.source_manager import source_manager, PhotoSource
from src.services.sync_service import sync_service
from src.utils.rclone import count_local_files, rclone_count

logger = logging.getLogger(__name__)

# Cache remote counts to avoid hammering the cloud provider on every status poll
_remote_count_cache: dict[str, tuple[int, float]] = {}  # remote -> (count, timestamp)
REMOTE_COUNT_CACHE_TTL = 300  # 5 minutes

# Default path for capacity checks
PICTURES_PATH = Path.home() / "Pictures"


def get_current_source() -> tuple[str, Optional[PhotoSource]]:
    """
    Get the current active source ID and object.

    Returns:
        Tuple of (source_id, PhotoSource or None)
    """
    settings = get_settings()
    current_source_id = settings.display.current_source
    sources = source_manager.list_sources()
    current_source = next((s for s in sources if s.id == current_source_id), None)
    return current_source_id, current_source


async def get_photo_counts(source: Optional[PhotoSource]) -> tuple[int, int]:
    """
    Get local and remote photo counts for a source.

    Args:
        source: The photo source to count, or None

    Returns:
        Tuple of (local_count, remote_count)
    """
    if not source:
        return 0, 0

    local_count = count_local_files(source.local_path)

    remote_count = 0
    if source.rclone_remote:
        cached = _remote_count_cache.get(source.rclone_remote)
        if cached and (time.monotonic() - cached[1]) < REMOTE_COUNT_CACHE_TTL:
            remote_count = cached[0]
        else:
            try:
                remote_count = await asyncio.wait_for(
                    rclone_count(source.rclone_remote),
                    timeout=15,
                )
                _remote_count_cache[source.rclone_remote] = (remote_count, time.monotonic())
            except (asyncio.TimeoutError, Exception):
                # Use stale cache if available rather than showing 0
                if cached:
                    remote_count = cached[0]

    return local_count, remote_count


def determine_sync_status(local_count: int, remote_count: int) -> str:
    """
    Determine sync status from counts and sync service state.

    Returns:
        Status string: "syncing", "error", "match", "mismatch", or "idle"
    """
    if sync_service._is_syncing:
        return "syncing"
    if sync_service._last_sync and not sync_service._last_sync.success:
        return "error"
    if local_count == remote_count and remote_count > 0:
        return "match"
    if remote_count > 0 and local_count != remote_count:
        return "mismatch"
    return "idle"


def get_last_sync_time() -> Optional[str]:
    """
    Get the ISO timestamp of the last sync, if any.

    Returns:
        ISO format string or None
    """
    if sync_service._last_sync and hasattr(sync_service._last_sync, 'completed_at'):
        return sync_service._last_sync.completed_at.isoformat()
    return None


def get_disk_capacity(path: Path = PICTURES_PATH) -> dict:
    """
    Get disk capacity for a path.

    Args:
        path: Path to check capacity for

    Returns:
        Dict with total_gb, used_gb, available_gb, percent_used, and byte values
    """
    try:
        usage = shutil.disk_usage(path)
        total_gb = usage.total / (1024**3)
        used_gb = usage.used / (1024**3)
        available_gb = usage.free / (1024**3)
        percent_used = (usage.used / usage.total) * 100 if usage.total > 0 else 0
        return {
            "total_gb": round(total_gb, 2),
            "used_gb": round(used_gb, 2),
            "available_gb": round(available_gb, 2),
            "percent_used": round(percent_used, 1),
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
        }
    except Exception:
        return {
            "total_gb": 0, "used_gb": 0, "available_gb": 0, "percent_used": 0,
            "total_bytes": 0, "used_bytes": 0, "free_bytes": 0,
        }

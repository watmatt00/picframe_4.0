"""
PicFrame 4.0 API - Status Routes.

Provides frame status information:
- GET /status: Full status including capacity, sync state, service health
"""

import asyncio
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.dependencies import require_admin
from src.config.settings import get_settings
from src.services.source_manager import source_manager
from src.services.sync_service import sync_service
from src.utils.rclone import count_local_files

router = APIRouter(tags=["status"])


class ServiceStatus(BaseModel):
    """Status of a systemd service."""
    name: str
    display_name: str
    active: bool
    status: str  # "running", "stopped", "unknown"
    can_restart: bool


class SyncStatusInfo(BaseModel):
    """Status of photo sync."""
    last_sync: Optional[str]
    status: str  # "match", "mismatch", "syncing", "error", "idle"
    local_count: int
    remote_count: int
    is_syncing: bool
    current_source: Optional[str]


class CapacityInfo(BaseModel):
    """Storage capacity information."""
    total_gb: float
    used_gb: float
    available_gb: float
    percent_used: float
    total_bytes: int
    used_bytes: int
    free_bytes: int


class FrameStatus(BaseModel):
    """Complete frame status response."""
    frame_id: str
    frame_name: str
    current_source: str
    photo_count: int
    services: list[ServiceStatus]
    sync: SyncStatusInfo
    capacity: CapacityInfo


SERVICE_DISPLAY_NAMES = {
    "picframe.service": "PicFrame Display",
    "picframe-api.service": "PicFrame API",
    "picframe-sync.service": "PicFrame Sync",
}


def _map_service_status(systemctl_status: str) -> str:
    """Map systemctl status strings to mobile-friendly values."""
    if systemctl_status == "active":
        return "running"
    elif systemctl_status == "inactive":
        return "stopped"
    return "unknown"


async def _get_service_status(service_name: str) -> ServiceStatus:
    """Get status of a systemd user service."""
    display_name = SERVICE_DISPLAY_NAMES.get(service_name, service_name)
    try:
        proc = await asyncio.create_subprocess_exec(
            "systemctl", "--user", "is-active", service_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        raw_status = stdout.decode().strip()
        active = raw_status == "active"
        return ServiceStatus(
            name=service_name,
            display_name=display_name,
            active=active,
            status=_map_service_status(raw_status),
            can_restart=True,
        )
    except Exception:
        return ServiceStatus(
            name=service_name,
            display_name=display_name,
            active=False,
            status="unknown",
            can_restart=True,
        )


def _get_capacity(path: Path) -> CapacityInfo:
    """Get disk capacity for the given path."""
    try:
        usage = shutil.disk_usage(path)
        total_gb = usage.total / (1024**3)
        used_gb = usage.used / (1024**3)
        available_gb = usage.free / (1024**3)
        percent_used = (usage.used / usage.total) * 100 if usage.total > 0 else 0
        return CapacityInfo(
            total_gb=round(total_gb, 2),
            used_gb=round(used_gb, 2),
            available_gb=round(available_gb, 2),
            percent_used=round(percent_used, 1),
            total_bytes=usage.total,
            used_bytes=usage.used,
            free_bytes=usage.free,
        )
    except Exception:
        return CapacityInfo(
            total_gb=0, used_gb=0, available_gb=0, percent_used=0,
            total_bytes=0, used_bytes=0, free_bytes=0,
        )


@router.get("/status", response_model=FrameStatus)
async def get_status(admin=Depends(require_admin)):
    """
    Get comprehensive frame status.

    Returns service health, sync status, capacity, and current configuration.
    """
    settings = get_settings()

    # Get service statuses
    services = await asyncio.gather(
        _get_service_status("picframe.service"),
        _get_service_status("picframe-api.service"),
    )

    # Get current source info
    current_source_id = settings.display.current_source
    sources = source_manager.list_sources()
    current_source = next((s for s in sources if s.id == current_source_id), None)

    # Count photos
    photo_count = 0
    if current_source:
        photo_count = count_local_files(current_source.local_path)

    # Get total photo count across all sources
    total_local_count = sum(count_local_files(s.local_path) for s in sources)

    # Determine sync status
    sync_status = "idle"
    if sync_service._is_syncing:
        sync_status = "syncing"
    elif sync_service._last_sync:
        sync_status = "match" if sync_service._last_sync.success else "error"

    last_sync_str = None
    if sync_service._last_sync:
        last_sync_str = sync_service._last_sync.completed_at.isoformat()

    # Get capacity for Pictures directory
    pictures_path = Path.home() / "Pictures"
    capacity = _get_capacity(pictures_path)

    return FrameStatus(
        frame_id=settings.frame.id,
        frame_name=settings.frame.name,
        current_source=current_source_id,
        photo_count=photo_count,
        services=list(services),
        sync=SyncStatusInfo(
            last_sync=last_sync_str,
            status=sync_status,
            local_count=total_local_count,
            remote_count=0,  # Would need to query all remotes
            is_syncing=sync_service._is_syncing,
            current_source=sync_service._current_source,
        ),
        capacity=capacity,
    )

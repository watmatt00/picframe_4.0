"""
PicFrame 4.0 API - Status Routes.

Provides frame status information:
- GET /status: Full status including capacity, sync state, service health
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from src.api.dependencies import require_admin

router = APIRouter(tags=["status"])


class ServiceStatus(BaseModel):
    """Status of a systemd service."""
    name: str
    active: bool
    status: str


class SyncStatus(BaseModel):
    """Status of photo sync."""
    last_sync: Optional[str]
    status: str  # "match", "mismatch", "syncing", "error"
    local_count: int
    remote_count: int


class CapacityInfo(BaseModel):
    """Storage capacity information."""
    total_gb: float
    used_gb: float
    available_gb: float
    percent_used: float


class FrameStatus(BaseModel):
    """Complete frame status response."""
    frame_id: str
    frame_name: str
    current_source: str
    services: list[ServiceStatus]
    sync: SyncStatus
    capacity: CapacityInfo


@router.get("/status", response_model=FrameStatus)
async def get_status(admin=Depends(require_admin)):
    """
    Get comprehensive frame status.

    Returns service health, sync status, capacity, and current configuration.
    """
    # TODO: Implement status gathering
    return FrameStatus(
        frame_id="placeholder",
        frame_name="Placeholder Frame",
        current_source="koofr_main",
        services=[],
        sync=SyncStatus(
            last_sync=None,
            status="unknown",
            local_count=0,
            remote_count=0,
        ),
        capacity=CapacityInfo(
            total_gb=0,
            used_gb=0,
            available_gb=0,
            percent_used=0,
        ),
    )

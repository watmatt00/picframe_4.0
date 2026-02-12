"""
PicFrame 4.0 API - Settings Routes.

Manage frame settings remotely:
- GET /settings: Get current settings
- PUT /settings/sync-interval: Update sync interval
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.api.dependencies import require_admin
from src.config.settings import get_settings, reload_settings
from src.config.manager import config_manager

router = APIRouter(prefix="/settings", tags=["settings"])


class FrameSettings(BaseModel):
    """Current frame settings exposed to mobile app."""
    sync_interval: int = Field(description="Sync interval in seconds")
    rotation_interval: int = Field(description="Seconds between photo rotations")
    frame_name: str = Field(description="Frame display name")


class UpdateSyncIntervalRequest(BaseModel):
    """Request to update sync interval."""
    interval: int = Field(ge=60, le=86400, description="Sync interval in seconds (1 min to 24 hours)")


class UpdateSettingsResponse(BaseModel):
    """Response after updating settings."""
    success: bool
    message: str


@router.get("", response_model=FrameSettings)
async def get_frame_settings(admin=Depends(require_admin)):
    """
    Get current frame settings.
    """
    settings = get_settings()
    return FrameSettings(
        sync_interval=settings.sync.interval,
        rotation_interval=settings.display.rotation_interval,
        frame_name=settings.frame.name,
    )


@router.put("/sync-interval", response_model=UpdateSettingsResponse)
async def update_sync_interval(
    request: UpdateSyncIntervalRequest,
    admin=Depends(require_admin),
):
    """
    Update the sync interval.

    Changes how often the frame syncs photos from cloud sources.
    """
    config_manager.set("sync.interval", request.interval)
    reload_settings()

    return UpdateSettingsResponse(
        success=True,
        message=f"Sync interval updated to {request.interval} seconds",
    )

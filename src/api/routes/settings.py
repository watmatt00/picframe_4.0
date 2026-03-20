"""
PicFrame 4.0 API - Settings Routes.

Manage frame settings remotely:
- GET /settings: Get current settings
- PUT /settings/sync-interval: Update sync interval
- PUT /settings/frame-name: Update frame display name
- PUT /settings/rotation-interval: Update photo rotation interval
"""

from pathlib import Path

import yaml
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from src.api.dependencies import require_admin
from src.config.settings import get_settings, reload_settings
from src.config.manager import config_manager
from src.services.systemd_service import systemd_service, update_sync_timer, VALID_SYNC_INTERVALS
from src.utils.logging import log_auth_event

PICFRAME_CONFIG_PATH = Path.home() / "picframe_data" / "config" / "configuration.yaml"

router = APIRouter(prefix="/settings", tags=["settings"])


class FrameSettings(BaseModel):
    """Current frame settings exposed to mobile app."""
    sync_interval: int = Field(description="Sync interval in seconds (0 = disabled)")
    rotation_interval: int = Field(description="Seconds between photo rotations")
    frame_name: str = Field(description="Frame display name")


class UpdateSyncIntervalRequest(BaseModel):
    """Request to update sync interval."""
    interval: int = Field(description="Sync interval in seconds (0=off, or 300/600/900/1800/2700/3600/7200/21600/43200/86400)")

    @field_validator("interval")
    @classmethod
    def must_be_valid_interval(cls, v: int) -> int:
        if v not in VALID_SYNC_INTERVALS:
            raise ValueError(f"interval must be one of {sorted(VALID_SYNC_INTERVALS)}")
        return v


class UpdateFrameNameRequest(BaseModel):
    """Request to update frame display name."""
    name: str = Field(
        min_length=1,
        max_length=50,
        pattern=r'^[a-zA-Z0-9 _\-]+$',
        description="Frame display name (alphanumeric, spaces, hyphens, underscores)",
    )


class UpdateRotationIntervalRequest(BaseModel):
    """Request to update photo rotation interval."""
    interval: int = Field(ge=5, le=3600, description="Rotation interval in seconds (5s to 60min)")


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
    await update_sync_timer(request.interval)

    label = "disabled" if request.interval == 0 else f"{request.interval} seconds"
    return UpdateSettingsResponse(
        success=True,
        message=f"Sync interval updated to {label}",
    )


@router.put("/frame-name", response_model=UpdateSettingsResponse)
async def update_frame_name(
    request: UpdateFrameNameRequest,
    admin=Depends(require_admin),
):
    """
    Update the frame display name.

    The name appears in the mobile app and pairing QR codes.
    """
    name = request.name.strip()
    config_manager.set("frame.name", name)
    reload_settings()

    log_auth_event(
        "SETTINGS_UPDATE",
        success=True,
        details={"field": "frame_name", "admin": admin.device_name},
    )

    return UpdateSettingsResponse(
        success=True,
        message=f"Frame name updated to '{name}'",
    )


@router.put("/rotation-interval", response_model=UpdateSettingsResponse)
async def update_rotation_interval(
    request: UpdateRotationIntervalRequest,
    admin=Depends(require_admin),
):
    """
    Update the photo rotation interval.

    Changes how many seconds each photo is displayed.
    Automatically restarts the Frame service to apply the change.
    """
    config_manager.set("display.rotation_interval", request.interval)
    reload_settings()

    # Also write to pi3d configuration.yaml so dashboard reads the same value
    if PICFRAME_CONFIG_PATH.exists():
        try:
            with open(PICFRAME_CONFIG_PATH) as f:
                picframe_config = yaml.safe_load(f) or {}
            picframe_config.setdefault("model", {})["time_delay"] = float(request.interval)
            with open(PICFRAME_CONFIG_PATH, "w") as f:
                yaml.safe_dump(picframe_config, f, default_flow_style=False)
        except Exception as e:
            log_auth_event("SETTINGS_UPDATE", success=False,
                           details={"field": "rotation_interval", "error": str(e)})

    restarted = await systemd_service.restart("picframe")

    log_auth_event(
        "SETTINGS_UPDATE",
        success=True,
        details={
            "field": "rotation_interval",
            "value": request.interval,
            "admin": admin.device_name,
            "service_restarted": restarted,
        },
    )

    message = f"Rotation interval updated to {request.interval} seconds"
    if restarted:
        message += ". Frame service restarted."
    else:
        message += ". Warning: Frame service restart failed — change will apply on next restart."

    return UpdateSettingsResponse(success=True, message=message)

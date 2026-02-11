"""
PicFrame 4.0 API - Display Control Routes.

Controls the Pi3D PictureFrame display:
- GET /display/folder: Get current display folder
- POST /display/folder: Switch display folder
"""

import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel

from src.api.dependencies import require_admin
from src.config.settings import get_settings, reload_settings
from src.config.manager import config_manager
from src.services.display_service import display_service
from src.services.source_manager import source_manager
from src.services.sync_service import sync_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/display", tags=["display"])


class DisplayFolder(BaseModel):
    """Current display folder info."""
    source_id: str
    source_name: str
    path: str
    photo_count: int


class SwitchFolderRequest(BaseModel):
    """Request to switch display folder."""
    source_id: str


class SwitchFolderResponse(BaseModel):
    """Response after switching display folder."""
    success: bool
    source_id: str
    source_name: str
    path: str
    message: str


@router.get("/folder", response_model=DisplayFolder)
async def get_current_folder(admin=Depends(require_admin)):
    """
    Get the currently active display folder.
    """
    settings = get_settings()
    current_source_id = settings.display.current_source

    # Get source info
    source = source_manager.get_source(current_source_id)
    if not source:
        # Return info about the raw folder from Pi3D
        current_path = await display_service.get_current_folder()
        return DisplayFolder(
            source_id="unknown",
            source_name="Unknown Source",
            path=current_path,
            photo_count=0,
        )

    # Count photos in the source
    from src.utils.rclone import count_local_files
    photo_count = count_local_files(source.local_path)

    return DisplayFolder(
        source_id=source.id,
        source_name=source.name,
        path=source.local_path,
        photo_count=photo_count,
    )


@router.post("/folder", response_model=SwitchFolderResponse)
async def switch_folder(
    request: SwitchFolderRequest,
    background_tasks: BackgroundTasks,
    admin=Depends(require_admin),
):
    """
    Switch the display to a different photo source.

    This updates the Pi3D configuration, restarts the display service,
    and triggers a background sync for the new source if it has a remote.
    """
    # Validate source exists
    source = source_manager.get_source(request.source_id)
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source '{request.source_id}' not found",
        )

    if not source.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Source '{request.source_id}' is disabled",
        )

    # Check path exists
    source_path = Path(source.local_path)
    if not source_path.exists():
        # Create it if it doesn't exist
        source_path.mkdir(parents=True, exist_ok=True)

    # Switch the display folder
    success = await display_service.switch_folder(source_path)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to switch display to '{request.source_id}'",
        )

    # Update our config to track current source
    config_manager.set("display.current_source", request.source_id)
    reload_settings()  # Clear cached settings

    # Auto-sync the new source in the background if it has a remote
    if source.rclone_remote and not sync_service._is_syncing:
        async def _run_sync():
            """Background sync for the newly activated source."""
            try:
                await sync_service.sync_source(
                    source_id=source.id,
                    local_path=Path(source.local_path),
                    rclone_remote=source.rclone_remote,
                )
                logger.info(f"Auto-sync completed for '{source.id}'")
            except Exception as e:
                logger.error(f"Auto-sync failed for '{source.id}': {e}")

        background_tasks.add_task(_run_sync)
        logger.info(f"Auto-sync triggered for '{source.id}' after activation")

    return SwitchFolderResponse(
        success=True,
        source_id=source.id,
        source_name=source.name,
        path=source.local_path,
        message=f"Display switched to '{source.name}'",
    )

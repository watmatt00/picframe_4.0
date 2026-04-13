"""
PicFrame 4.0 API - Display Control Routes.

Controls the Pi3D PictureFrame display:
- GET /display/folder: Get current display folder
- POST /display/folder: Switch display folder
- POST /display/spotlight: Show a single photo for N seconds, then restore
"""

import asyncio
import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel

from src.api.dependencies import require_admin
from src.config.settings import get_settings, reload_settings
from src.config.manager import config_manager
from src.services.display_service import display_service
from src.services.source_manager import source_manager
from src.services.sync_service import sync_service
from src.utils.rclone import _validate_filename, _validate_relative_path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/display", tags=["display"])

# Non-hidden, persistent — Pi3D indexes this dir at startup and tracks it via mtime.
# Never removed, only its contents are cleared after a spotlight ends.
SPOTLIGHT_DIR = Path.home() / "Pictures" / "spotlight"
SPOTLIGHT_DIR.mkdir(parents=True, exist_ok=True)


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


class SpotlightRequest(BaseModel):
    """Request to spotlight a single photo."""
    source_id: str
    filename: str
    duration_seconds: int = 60


class SpotlightResponse(BaseModel):
    """Response after starting a spotlight."""
    success: bool
    filename: str
    duration_seconds: int
    message: str


@router.post("/spotlight", response_model=SpotlightResponse)
async def spotlight_photo(
    request: SpotlightRequest,
    background_tasks: BackgroundTasks,
    admin=Depends(require_admin),
):
    """
    Display a single photo on the frame for a limited time, then restore
    the previous source automatically.
    """
    if not _validate_relative_path(request.filename):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")

    if not (1 <= request.duration_seconds <= 3600):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="duration_seconds must be 1–3600")

    source = source_manager.get_source(request.source_id)
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Source '{request.source_id}' not found")

    photo_path = Path(source.local_path) / request.filename
    if not photo_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")

    # Guard against path traversal
    try:
        photo_path.resolve().relative_to(Path(source.local_path).resolve())
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")

    # Capture current source for restoration
    settings = get_settings()
    restore_source_id = settings.display.current_source
    restore_source = source_manager.get_source(restore_source_id)
    restore_path = (
        Path(restore_source.local_path) if restore_source
        else Path(await display_service.get_current_folder())
    )

    # Clear any previous spotlight content, copy the target photo.
    # Copy (not symlink) to avoid follow_links issues; keep the dir itself
    # so Pi3D continues to track it in its DB via mtime changes.
    SPOTLIGHT_DIR.mkdir(parents=True, exist_ok=True)
    for old in SPOTLIGHT_DIR.glob("*"):
        old.unlink(missing_ok=True)
    spotlight_file = SPOTLIGHT_DIR / Path(request.filename).name
    shutil.copy2(str(photo_path.resolve()), str(spotlight_file))

    # Give Pi3D's update_interval scan (2s) time to detect the new file
    # before switching — avoids "no pictures selected" flash.
    await asyncio.sleep(2.5)

    # Switch display to spotlight dir via HTTP API (no service restart)
    success = await display_service.switch_folder(SPOTLIGHT_DIR)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to switch display for spotlight",
        )

    # Pause immediately after switch — Pi3D will complete the fade-in of the
    # spotlight photo then freeze on it, preventing it from looping.
    await display_service.pause()

    logger.info(f"Spotlight started: '{request.filename}' for {request.duration_seconds}s (restore → '{restore_source_id}')")

    async def _restore() -> None:
        await asyncio.sleep(request.duration_seconds)
        logger.info(f"Spotlight ending — restoring to '{restore_source_id}'")
        await display_service.resume()  # unpause before switching back
        await display_service.switch_folder(restore_path)
        config_manager.set("display.current_source", restore_source_id)
        reload_settings()
        # Remove spotlight files (keep the dir so Pi3D keeps it indexed)
        for f in SPOTLIGHT_DIR.glob("*"):
            f.unlink(missing_ok=True)

    background_tasks.add_task(_restore)

    restore_name = restore_source.name if restore_source else restore_source_id
    return SpotlightResponse(
        success=True,
        filename=request.filename,
        duration_seconds=request.duration_seconds,
        message=f"Displaying '{request.filename}' for {request.duration_seconds}s, then restoring '{restore_name}'",
    )

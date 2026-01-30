"""
PicFrame 4.0 API - Display Control Routes.

Controls the Pi3D PictureFrame display:
- GET /display/folder: Get current display folder
- POST /display/folder: Switch display folder
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.api.dependencies import require_admin

router = APIRouter(prefix="/display", tags=["display"])


class DisplayFolder(BaseModel):
    """Current display folder info."""
    source_id: str
    source_name: str
    path: str


class SwitchFolderRequest(BaseModel):
    """Request to switch display folder."""
    source_id: str


@router.get("/folder", response_model=DisplayFolder)
async def get_current_folder(admin=Depends(require_admin)):
    """
    Get the currently active display folder.
    """
    # TODO: Implement via display_service
    return DisplayFolder(
        source_id="koofr_main",
        source_name="Main Photos",
        path="/home/pi/Pictures/koofr_main",
    )


@router.post("/folder", response_model=DisplayFolder)
async def switch_folder(request: SwitchFolderRequest, admin=Depends(require_admin)):
    """
    Switch the display to a different photo source.

    This updates the Pi3D configuration and restarts the display service.
    """
    # TODO: Implement folder switching
    # - Validate source_id exists
    # - Update symlink or config
    # - Restart picframe service
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Folder switching not yet implemented",
    )

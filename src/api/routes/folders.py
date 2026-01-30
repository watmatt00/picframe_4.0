"""
PicFrame 4.0 API - Folder Management Routes.

Manages photo sources/folders:
- GET /folders: List all photo sources
- POST /folders: Create a new photo source
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional

from src.api.dependencies import require_admin

router = APIRouter(prefix="/folders", tags=["folders"])


class PhotoSource(BaseModel):
    """A photo source configuration."""
    id: str
    name: str
    local_path: str
    rclone_remote: Optional[str]
    enabled: bool
    photo_count: int


class CreateFolderRequest(BaseModel):
    """Request to create a new photo source."""
    name: str
    rclone_remote: Optional[str] = None


@router.get("", response_model=list[PhotoSource])
async def list_folders(admin=Depends(require_admin)):
    """
    List all configured photo sources.
    """
    # TODO: Implement via source_manager
    return []


@router.post("", response_model=PhotoSource)
async def create_folder(request: CreateFolderRequest, admin=Depends(require_admin)):
    """
    Create a new photo source.

    If rclone_remote is provided, sets up sync from that remote.
    """
    # TODO: Implement folder creation
    # - Validate name is unique
    # - Create local directory
    # - Add to sources.yaml
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Folder creation not yet implemented",
    )

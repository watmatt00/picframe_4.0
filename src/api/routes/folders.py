"""
PicFrame 4.0 API - Folder Management Routes.

Manages photo sources/folders:
- GET /folders: List all photo sources
- POST /folders: Create a new photo source
- GET /folders/{id}: Get folder details
- DELETE /folders/{id}: Delete a folder
- POST /folders/{id}/sync: Trigger sync for a folder
- GET /folders/{id}/sync/status: Get sync status for a folder
- POST /folders/sync/all: Sync all enabled sources
- GET /folders/remotes: List available rclone remotes
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
from typing import Optional

from src.api.dependencies import require_admin
from src.services.source_manager import source_manager
from src.services.sync_service import sync_service
from src.utils.rclone import count_local_files, get_sync_status, rclone_list_remotes


router = APIRouter(prefix="/folders", tags=["folders"])


class PhotoSourceResponse(BaseModel):
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


class SyncStatusResponse(BaseModel):
    """Sync status response."""
    is_syncing: bool
    current_source: Optional[str]
    local_count: int
    remote_count: int
    sync_status: str
    message: str


class SyncTriggerResponse(BaseModel):
    """Response after triggering sync."""
    message: str
    source_id: str


@router.get("", response_model=list[PhotoSourceResponse])
async def list_folders(admin=Depends(require_admin)):
    """
    List all configured photo sources.
    """
    sources = source_manager.list_sources()
    result = []
    for source in sources:
        photo_count = count_local_files(source.local_path)
        result.append(PhotoSourceResponse(
            id=source.id,
            name=source.name,
            local_path=source.local_path,
            rclone_remote=source.rclone_remote,
            enabled=source.enabled,
            photo_count=photo_count,
        ))
    return result


@router.post("", response_model=PhotoSourceResponse, status_code=status.HTTP_201_CREATED)
async def create_folder(request: CreateFolderRequest, admin=Depends(require_admin)):
    """
    Create a new photo source.

    If rclone_remote is provided, sets up sync from that remote.
    """
    source = source_manager.create_source(
        name=request.name,
        rclone_remote=request.rclone_remote,
    )

    photo_count = count_local_files(source.local_path)

    return PhotoSourceResponse(
        id=source.id,
        name=source.name,
        local_path=source.local_path,
        rclone_remote=source.rclone_remote,
        enabled=source.enabled,
        photo_count=photo_count,
    )


@router.get("/{source_id}", response_model=PhotoSourceResponse)
async def get_folder(source_id: str, admin=Depends(require_admin)):
    """
    Get a specific photo source by ID.
    """
    source = source_manager.get_source(source_id)
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source '{source_id}' not found",
        )

    photo_count = count_local_files(source.local_path)

    return PhotoSourceResponse(
        id=source.id,
        name=source.name,
        local_path=source.local_path,
        rclone_remote=source.rclone_remote,
        enabled=source.enabled,
        photo_count=photo_count,
    )


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(source_id: str, admin=Depends(require_admin)):
    """
    Delete a photo source configuration.

    Note: Does not delete the local files.
    """
    if not source_manager.delete_source(source_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source '{source_id}' not found",
        )


@router.get("/{source_id}/sync/status", response_model=SyncStatusResponse)
async def get_folder_sync_status(source_id: str, admin=Depends(require_admin)):
    """
    Get sync status for a specific folder.

    Returns local vs remote file counts and sync state.
    """
    source = source_manager.get_source(source_id)
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source '{source_id}' not found",
        )

    local_count = count_local_files(source.local_path)
    remote_count = 0
    sync_status_str = "unknown"
    message = "No remote configured"

    if source.rclone_remote:
        status_result = await get_sync_status(source.rclone_remote, source.local_path)
        remote_count = status_result.remote_count
        local_count = status_result.local_count
        sync_status_str = status_result.status.value
        message = status_result.message

    return SyncStatusResponse(
        is_syncing=sync_service._is_syncing,
        current_source=sync_service._current_source,
        local_count=local_count,
        remote_count=remote_count,
        sync_status=sync_status_str,
        message=message,
    )


async def _run_sync(source_id: str, local_path: str, rclone_remote: str):
    """Background task to run sync."""
    await sync_service.sync_source(
        source_id=source_id,
        local_path=Path(local_path),
        rclone_remote=rclone_remote,
    )


@router.post("/{source_id}/sync", response_model=SyncTriggerResponse)
async def trigger_folder_sync(
    source_id: str,
    background_tasks: BackgroundTasks,
    admin=Depends(require_admin),
):
    """
    Trigger sync for a specific folder.

    Sync runs in the background. Use GET /folders/{id}/sync/status to check progress.
    """
    source = source_manager.get_source(source_id)
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source '{source_id}' not found",
        )

    if not source.rclone_remote:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Source '{source_id}' has no remote configured",
        )

    if sync_service._is_syncing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Sync already in progress for '{sync_service._current_source}'",
        )

    background_tasks.add_task(
        _run_sync,
        source_id,
        source.local_path,
        source.rclone_remote,
    )

    return SyncTriggerResponse(
        message=f"Sync started for '{source_id}'",
        source_id=source_id,
    )


class SyncAllResponse(BaseModel):
    """Response after triggering sync for all sources."""
    message: str
    sources_queued: list[str]


@router.post("/sync/all", response_model=SyncAllResponse)
async def trigger_sync_all(
    background_tasks: BackgroundTasks,
    admin=Depends(require_admin),
):
    """
    Trigger sync for all enabled sources with remotes configured.

    Sources are synced sequentially in the background.
    """
    if sync_service._is_syncing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Sync already in progress for '{sync_service._current_source}'",
        )

    sources = source_manager.list_sources()
    syncable = [s for s in sources if s.enabled and s.rclone_remote]

    if not syncable:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No sources with remotes configured",
        )

    async def sync_all_sources():
        for source in syncable:
            try:
                await sync_service.sync_source(
                    source_id=source.id,
                    local_path=Path(source.local_path),
                    rclone_remote=source.rclone_remote,
                )
            except RuntimeError:
                pass

    background_tasks.add_task(sync_all_sources)

    return SyncAllResponse(
        message=f"Sync started for {len(syncable)} sources",
        sources_queued=[s.id for s in syncable],
    )


class RemoteInfo(BaseModel):
    """An rclone remote."""
    name: str


@router.get("/remotes", response_model=list[RemoteInfo])
async def list_remotes(admin=Depends(require_admin)):
    """
    List available rclone remotes.

    Returns remotes configured in the system's rclone config.
    """
    remotes = await rclone_list_remotes()
    return [RemoteInfo(name=name) for name in remotes]

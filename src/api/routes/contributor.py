"""
PicFrame 4.0 API - Contributor Routes.

Endpoints accessible to both admin and contributor tokens:
- GET  /contributor/folders              — list uploadable photo sources
- POST /contributor/upload/{source_id}   — upload a photo directly to a source
"""

import logging
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from src.api.dependencies import require_contributor
from src.services.source_manager import source_manager
from src.utils.rclone import IMAGE_EXTENSIONS, _validate_filename, count_local_files

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/contributor", tags=["contributor"])

_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


class ContributorFolder(BaseModel):
    id: str
    name: str
    photo_count: int


class ContributorFoldersResponse(BaseModel):
    folders: list[ContributorFolder]


class ContributorUploadResponse(BaseModel):
    success: bool
    file_name: str
    source_id: str
    message: str


@router.get("/folders", response_model=ContributorFoldersResponse)
async def list_contributor_folders(device=Depends(require_contributor)):
    """
    List enabled photo sources available for contributor upload.

    Returns only id, name, and photo_count — never exposes local_path or
    rclone_remote to contributor tokens.
    """
    sources = source_manager.list_sources()
    folders = [
        ContributorFolder(
            id=source.id,
            name=source.name,
            photo_count=count_local_files(source.local_path),
        )
        for source in sources
        if source.enabled
    ]
    return ContributorFoldersResponse(folders=folders)


@router.post("/upload/{source_id}", response_model=ContributorUploadResponse)
async def contributor_upload(
    source_id: str,
    file: UploadFile = File(...),
    device=Depends(require_contributor),
):
    """
    Upload a photo directly to a source's local directory.

    The file is written atomically (write to .tmp, rename). The Pi's
    scheduled rclone sync will push it to cloud storage on the next cycle.

    Security:
    - File extension validated against IMAGE_EXTENSIONS whitelist
    - Filename sanitised and path-traversal checked
    - Max 50 MB per file
    - Writes only to the source's configured local_path
    """
    source = source_manager.get_source(source_id)
    if not source or not source.enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Source '{source_id}' not found")

    filename = (file.filename or "upload.jpg").strip()
    if not _validate_filename(filename):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid filename")

    suffix = Path(filename).suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"File type '{suffix}' not allowed. Accepted: {', '.join(sorted(IMAGE_EXTENSIONS))}",
        )

    local_dir = Path(source.local_path)
    local_dir.mkdir(parents=True, exist_ok=True)
    dest = local_dir / filename

    # Guard against path traversal
    try:
        dest.resolve().relative_to(local_dir.resolve())
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid filename")

    # On filename conflict, append a timestamp suffix before the extension
    if dest.exists():
        stem = dest.stem
        dest = local_dir / f"{stem}_{int(time.time())}{suffix}"
        filename = dest.name

    contents = await file.read()
    if len(contents) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "File too large (max 50 MB)",
        )

    tmp = dest.with_suffix(dest.suffix + ".tmp")
    try:
        tmp.write_bytes(contents)
        tmp.rename(dest)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        logger.error(f"Contributor upload failed for '{filename}': {exc}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to save file")

    logger.info(
        f"Contributor upload: '{filename}' → source '{source_id}' "
        f"by '{device.device_name}' (role={device.role})"
    )

    return ContributorUploadResponse(
        success=True,
        file_name=filename,
        source_id=source_id,
        message=f"Uploaded '{filename}' to '{source.name}'. Will sync to cloud on next scheduled sync.",
    )

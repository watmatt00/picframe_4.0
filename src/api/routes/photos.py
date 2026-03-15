"""
PicFrame 4.0 API - Photo Management Routes.

Provides per-source photo listing, thumbnail generation, and deletion:
- GET  /sources/{source_id}/photos               — list photos from local filesystem
- GET  /sources/{source_id}/photos/thumbnail     — JPEG thumbnail via Pillow (cached)
- DELETE /sources/{source_id}/photos/{filename}  — delete from cloud first, then local
"""

import io
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from src.api.dependencies import require_admin
from src.services.source_manager import source_manager
from src.utils.rclone import rclone_deletefile, _validate_filename, IMAGE_EXTENSIONS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sources", tags=["photos"])

THUMB_CACHE_DIR = Path("/tmp/pfthumb")
THUMB_SIZE = (256, 256)


class PhotoInfo(BaseModel):
    filename: str
    size_bytes: int
    modified_epoch: int


class PhotoListResponse(BaseModel):
    source_id: str
    photos: list[PhotoInfo]
    total: int


class DeletePhotoResponse(BaseModel):
    deleted: str
    message: str


@router.get("/{source_id}/photos", response_model=PhotoListResponse)
async def list_photos(source_id: str, admin=Depends(require_admin)):
    """List all image files in a source's local directory."""
    source = source_manager.get_source(source_id)
    if not source:
        raise HTTPException(404, f"Source '{source_id}' not found")
    local_path = Path(source.local_path)
    if not local_path.exists():
        return PhotoListResponse(source_id=source_id, photos=[], total=0)
    photos = []
    for f in sorted(local_path.rglob("*")):
        if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS:
            st = f.stat()
            photos.append(PhotoInfo(
                filename=f.name,
                size_bytes=st.st_size,
                modified_epoch=int(st.st_mtime),
            ))
    return PhotoListResponse(source_id=source_id, photos=photos, total=len(photos))


@router.get("/{source_id}/photos/thumbnail")
async def get_thumbnail(
    source_id: str,
    filename: str = Query(...),
    admin=Depends(require_admin),
):
    """Return a JPEG thumbnail for a photo. Cached in /tmp/pfthumb/."""
    if not _validate_filename(filename):
        raise HTTPException(400, "Invalid filename")
    source = source_manager.get_source(source_id)
    if not source:
        raise HTTPException(404, f"Source '{source_id}' not found")
    local_file = Path(source.local_path) / filename
    if not local_file.is_file():
        raise HTTPException(404, "Photo not found")
    # Block path traversal
    try:
        local_file.resolve().relative_to(Path(source.local_path).resolve())
    except ValueError:
        raise HTTPException(400, "Invalid filename")

    mtime = int(local_file.stat().st_mtime)
    cache_path = THUMB_CACHE_DIR / f"{source_id}_{filename}_{mtime}.jpg"
    if cache_path.exists():
        return Response(content=cache_path.read_bytes(), media_type="image/jpeg")

    from PIL import Image  # noqa: PLC0415 — lazy import, Pillow is optional at startup

    THUMB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with Image.open(local_file) as img:
            img = img.convert("RGB")
            img.thumbnail(THUMB_SIZE, Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=75, optimize=True)
            jpeg_bytes = buf.getvalue()
    except Exception as exc:
        logger.warning(f"Thumbnail generation failed for {filename}: {exc}")
        raise HTTPException(500, f"Failed to generate thumbnail: {exc}")

    tmp = cache_path.with_suffix(".tmp")
    tmp.write_bytes(jpeg_bytes)
    tmp.rename(cache_path)  # atomic
    return Response(content=jpeg_bytes, media_type="image/jpeg")


@router.delete("/{source_id}/photos/{filename}", response_model=DeletePhotoResponse)
async def delete_photo(source_id: str, filename: str, admin=Depends(require_admin)):
    """
    Delete a photo from cloud storage first, then from the local filesystem.

    Cloud deletion MUST succeed before local deletion to prevent sync restoring
    the file on the next sync cycle.
    """
    if not _validate_filename(filename):
        raise HTTPException(400, "Invalid filename")
    source = source_manager.get_source(source_id)
    if not source:
        raise HTTPException(404, f"Source '{source_id}' not found")
    local_file = Path(source.local_path) / filename
    if not local_file.is_file():
        raise HTTPException(404, "Photo not found locally")
    try:
        local_file.resolve().relative_to(Path(source.local_path).resolve())
    except ValueError:
        raise HTTPException(400, "Invalid filename")

    # STEP 1: delete from cloud (must succeed first)
    if source.rclone_remote:
        result = await rclone_deletefile(source.rclone_remote, filename)
        if not result.success:
            raise HTTPException(
                502,
                f"Cloud delete failed: {result.error}. Local NOT deleted.",
            )

    # STEP 2: delete local
    local_file.unlink()
    logger.info(f"Deleted photo '{filename}' from source '{source_id}'")

    # Evict thumbnail cache entries for this file
    for stale in THUMB_CACHE_DIR.glob(f"{source_id}_{filename}_*.jpg"):
        stale.unlink(missing_ok=True)

    return DeletePhotoResponse(
        deleted=filename,
        message=f"Deleted '{filename}' from cloud and local storage",
    )

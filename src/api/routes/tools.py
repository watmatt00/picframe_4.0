"""
PicFrame 4.0 API - Photo Tools Routes.

JWT-authenticated endpoints for photo library maintenance tools.
All operations follow a scan → apply pattern:

  GET  /sources/{source_id}/tools/scan/filenames   — preview filename fixes
  POST /sources/{source_id}/tools/apply/filenames  — execute renames (cloud-first)
  GET  /sources/{source_id}/tools/scan/duplicates  — find exact duplicate groups
  POST /sources/{source_id}/tools/apply/duplicates — delete chosen duplicates (cloud-first)
  GET  /sources/{source_id}/tools/scan/videos      — list video files Pi3D can't show
  POST /sources/{source_id}/tools/apply/videos     — delete chosen videos (cloud-first)

These endpoints share the same service layer as the LAN dashboard endpoints so
adding them to the iOS app requires only model bindings — no backend changes.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.dependencies import require_admin
from src.services import photo_tools_service as svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sources", tags=["tools"])


# ---------------------------------------------------------------------------
# Filename cleaning
# ---------------------------------------------------------------------------

@router.get("/{source_id}/tools/scan/filenames", response_model=svc.FilenameScanResult)
async def scan_filenames(source_id: str, admin=Depends(require_admin)):
    """Preview filename issues and proposed clean names. Read-only — no changes made."""
    try:
        return svc.scan_filenames(source_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except Exception as exc:
        logger.error(f"Filename scan failed for '{source_id}': {exc}")
        raise HTTPException(500, str(exc))


class ApplyFilenamesRequest(BaseModel):
    fixes: list[svc.FilenameFix]


@router.post("/{source_id}/tools/apply/filenames", response_model=svc.BatchResult)
async def apply_filenames(
    source_id: str,
    body: ApplyFilenamesRequest,
    admin=Depends(require_admin),
):
    """Apply a list of filename fixes (cloud-first).  Use scan first to generate the list."""
    try:
        return await svc.apply_filenames(source_id, body.fixes)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except Exception as exc:
        logger.error(f"Filename apply failed for '{source_id}': {exc}")
        raise HTTPException(500, str(exc))


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

@router.get("/{source_id}/tools/scan/duplicates", response_model=svc.DupScanResult)
async def scan_duplicates(source_id: str, admin=Depends(require_admin)):
    """Find exact duplicate files (hash-based). Read-only — no changes made.

    For large libraries this may take a few seconds. The response groups
    duplicate sets and suggests which copy to keep.
    """
    try:
        return svc.scan_duplicates(source_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except Exception as exc:
        logger.error(f"Duplicate scan failed for '{source_id}': {exc}")
        raise HTTPException(500, str(exc))


class ApplyDuplicatesRequest(BaseModel):
    to_delete: list[str]  # filenames to remove; user should omit the keeper


@router.post("/{source_id}/tools/apply/duplicates", response_model=svc.BatchResult)
async def apply_duplicates(
    source_id: str,
    body: ApplyDuplicatesRequest,
    admin=Depends(require_admin),
):
    """Delete the specified duplicate files (cloud-first).  Use scan to identify them."""
    if not body.to_delete:
        raise HTTPException(400, "to_delete list is empty")
    try:
        return await svc.apply_duplicates(source_id, body.to_delete)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except Exception as exc:
        logger.error(f"Duplicate apply failed for '{source_id}': {exc}")
        raise HTTPException(500, str(exc))


# ---------------------------------------------------------------------------
# Video management
# ---------------------------------------------------------------------------

@router.get("/{source_id}/tools/scan/videos", response_model=svc.VideoScanResult)
async def scan_videos(source_id: str, admin=Depends(require_admin)):
    """List video files in the source directory. Pi3D cannot display videos."""
    try:
        return svc.scan_videos(source_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except Exception as exc:
        logger.error(f"Video scan failed for '{source_id}': {exc}")
        raise HTTPException(500, str(exc))


class ApplyVideosRequest(BaseModel):
    to_delete: list[str]


@router.post("/{source_id}/tools/apply/videos", response_model=svc.BatchResult)
async def apply_videos(
    source_id: str,
    body: ApplyVideosRequest,
    admin=Depends(require_admin),
):
    """Delete the specified video files (cloud-first)."""
    if not body.to_delete:
        raise HTTPException(400, "to_delete list is empty")
    try:
        return await svc.apply_videos(source_id, body.to_delete)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except Exception as exc:
        logger.error(f"Video apply failed for '{source_id}': {exc}")
        raise HTTPException(500, str(exc))


# ---------------------------------------------------------------------------
# Manual rename
# ---------------------------------------------------------------------------

class RenameFileRequest(BaseModel):
    original: str
    proposed: str


@router.post("/{source_id}/tools/rename", response_model=svc.BatchResult)
async def rename_file(
    source_id: str,
    body: RenameFileRequest,
    admin=Depends(require_admin),
):
    """Rename a single file (cloud-first). Useful for one-off corrections."""
    if not body.original.strip() or not body.proposed.strip():
        raise HTTPException(400, "original and proposed are required")
    if body.original == body.proposed:
        raise HTTPException(400, "original and proposed are the same")
    try:
        return await svc.rename_file(source_id, body.original.strip(), body.proposed.strip())
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except Exception as exc:
        logger.error(f"Rename failed for '{source_id}': {exc}")
        raise HTTPException(500, str(exc))

"""
PicFrame 4.0 - Album Deletion (PL-147).

Deleting an album removes it from sources.yaml and deletes its photos on the
frame. The cloud folder is left alone (it's the master copy), and so are the
album's backups in ~/Pictures/backups.
"""

import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml
from filelock import FileLock

from src.config.settings import get_settings
from src.services import source_manager as sources
from src.services.source_manager import PhotoSource
from src.services.sync_service import sync_service
from src.utils import thumbnails
from src.utils.rclone import count_local_files

logger = logging.getLogger(__name__)

PICTURES_DIR = Path.home() / "Pictures"
# Albums deleted on this frame, so Recover Albums only offers this frame's own
# cloud folders: the Koofr account is shared, and other frames' KFR_* folders
# must never be offered (PL-147)
DELETED_ALBUMS_PATH = Path.home() / ".picframe" / "deleted_albums.yaml"

# Folders under ~/Pictures that belong to the frame, never to an album
PROTECTED_DIRS = frozenset({"spotlight", "backups"})


class AlbumDeleteError(Exception):
    """An album can't be deleted; `status_code` is the HTTP status to answer with."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _deleted_lock() -> FileLock:
    """Lock for the deleted-albums file (path looked up at call time, for tests)."""
    return FileLock(str(DELETED_ALBUMS_PATH) + ".lock", timeout=10)


def _load_deleted() -> list[dict[str, Any]]:
    """Read the deleted-albums file; an unreadable file counts as empty."""
    if not DELETED_ALBUMS_PATH.exists():
        return []
    try:
        data = yaml.safe_load(DELETED_ALBUMS_PATH.read_text()) or {}
        return [a for a in data.get("albums", []) if isinstance(a, dict) and a.get("rclone_remote")]
    except (OSError, yaml.YAMLError) as e:
        logger.error(f"Failed to read {DELETED_ALBUMS_PATH}: {e}")
        return []


def _save_deleted(albums: list[dict[str, Any]]) -> None:
    """Write the deleted-albums file atomically, owner-only."""
    DELETED_ALBUMS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = DELETED_ALBUMS_PATH.with_suffix(".tmp")
    tmp.write_text(yaml.safe_dump({"albums": albums}, default_flow_style=False))
    os.chmod(tmp, 0o600)
    tmp.replace(DELETED_ALBUMS_PATH)


def list_deleted_albums() -> list[dict[str, Any]]:
    """Albums deleted on this frame that had a cloud folder, newest first."""
    with _deleted_lock():
        return sorted(_load_deleted(), key=lambda a: a.get("deleted_at", ""), reverse=True)


def record_deleted_album(source: PhotoSource) -> None:
    """Remember a deleted album's cloud folder (one entry per folder, latest wins)."""
    if not source.rclone_remote:
        return
    with _deleted_lock():
        albums = [a for a in _load_deleted() if a["rclone_remote"] != source.rclone_remote]
        albums.append({
            "id": source.id,
            "name": source.name,
            "rclone_remote": source.rclone_remote,
            "deleted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        _save_deleted(albums)


def forget_deleted_album(rclone_remote: str) -> None:
    """Drop a deleted-album entry once it has been recovered."""
    with _deleted_lock():
        albums = _load_deleted()
        kept = [a for a in albums if a["rclone_remote"] != rclone_remote]
        if len(kept) != len(albums):
            _save_deleted(kept)


def deletable_folder(source: PhotoSource, others: list[PhotoSource]) -> Optional[Path]:
    """
    The album's local folder if it is safe to delete, else None.

    Safe means: it exists, is a direct child of ~/Pictures (after resolving
    symlinks), isn't a protected frame folder, and no other album uses it.
    """
    try:
        folder = Path(source.local_path).expanduser().resolve()
        pictures = PICTURES_DIR.resolve()
    except (OSError, RuntimeError):
        return None
    if not folder.is_dir() or folder.parent != pictures or folder.name in PROTECTED_DIRS:
        return None
    for other in others:
        try:
            if Path(other.local_path).expanduser().resolve() == folder:
                return None
        except (OSError, RuntimeError):
            continue
    return folder


def delete_album(source_id: str) -> dict[str, Any]:
    """
    Delete an album and its photos on the frame.

    Args:
        source_id: Album to delete

    Returns:
        deleted (id), name, photos_removed, local_folder_removed, cloud_folder
        and error (set when the album was removed but its folder couldn't be)

    Raises:
        AlbumDeleteError: 404 unknown album, 409 showing or syncing
    """
    source = sources.source_manager.get_source(source_id)
    if source is None:
        raise AlbumDeleteError(404, f"Album '{source_id}' not found")
    if get_settings().display.current_source == source_id:
        raise AlbumDeleteError(
            409, "This album is showing on the frame. Show another album first, then delete it."
        )
    if sync_service._is_syncing and sync_service._current_source == source_id:
        raise AlbumDeleteError(409, "This album is syncing. Try again when the sync has finished.")

    others = [s for s in sources.source_manager.list_sources() if s.id != source_id]
    folder = deletable_folder(source, others)
    photos = count_local_files(folder) if folder else 0

    if not sources.source_manager.delete_source(source_id):
        raise AlbumDeleteError(404, f"Album '{source_id}' not found")
    try:
        record_deleted_album(source)
    except Exception as e:  # recovery list only; the delete itself has happened
        logger.error(f"Album '{source_id}' deleted, but recording it for Recover Albums failed: {e}")

    result: dict[str, Any] = {
        "deleted": source_id,
        "name": source.name,
        "photos_removed": 0,
        "local_folder_removed": False,
        "cloud_folder": source.rclone_remote,
        "error": None,
    }
    if folder:
        try:
            shutil.rmtree(folder)
            result["photos_removed"] = photos
            result["local_folder_removed"] = True
        except OSError as e:
            logger.error(f"Album '{source_id}' removed, but deleting {folder} failed: {e}")
            result["error"] = f"The album was removed, but its photos couldn't be deleted from the frame: {e}"
    else:
        logger.warning(f"Album '{source_id}': local folder {source.local_path} kept (missing or not safe to delete)")

    thumbnails.evict_source(source_id)
    logger.info(
        f"Deleted album '{source_id}' ({result['photos_removed']} photos removed, "
        f"cloud folder {source.rclone_remote or 'none'} kept)"
    )
    return result

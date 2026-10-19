"""
PicFrame 4.0 - Album Recovery (PL-147 follow-up).

Gets albums back after Delete Album, from the dashboard:
- from its cloud folder (re-adds the album pointed at it): this frame's own
  deleted albums, per the frame registry; folders another frame sharing the
  cloud account claims are never offered
- from a .tar.gz backup in ~/Pictures/backups, including a deleted album's
- from a .zip / .tar.gz of photos uploaded from the computer

Sync mirrors the cloud onto the frame (rclone sync), so a photo that is only
on the frame is deleted by the next sync. Restores therefore unpack into a
staging folder, copy it to the album's cloud folder first, and only then move
the files into the album.
"""

import asyncio
import logging
import re
import shutil
import tarfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Callable, Optional

from src.services import backup_service, frame_registry
from src.services import source_manager as sources
from src.services.source_manager import PhotoSource
from src.services.sync_service import sync_service
from src.utils.rclone import (
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    rclone_copy_dir,
    rclone_count,
)

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
MAX_FILES = 10_000
MAX_TOTAL_BYTES = 8 * 1024 ** 3
FREE_SPACE_MARGIN = 1024 ** 3
MAX_UPLOAD_BYTES = 2 * 1024 ** 3
CLOUD_FOLDER_RE = frame_registry.FOLDER_RE
BACKUP_NAME_RE = re.compile(r"^(?P<id>[a-z0-9_-]+)_(?P<ts>\d{4}-\d{2}-\d{2}_\d{6})\.tar\.gz$")
COUNT_TIMEOUT_SECONDS = 15

# One restore at a time: they share disk space and the cloud connection
_restore_lock = asyncio.Lock()
# Keeps background syncs referenced so they aren't garbage-collected
_pending: set[asyncio.Task] = set()


class RecoveryError(Exception):
    """A recovery can't go ahead; `status_code` is the HTTP status to answer with."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


# --- Archives ----------------------------------------------------------------

def _keep(name: str) -> Optional[str]:
    """Flattened file name to restore for an archive entry, or None to skip it."""
    path = PurePosixPath(name.replace("\\", "/"))
    if any(part == "__MACOSX" for part in path.parts):
        return None
    flat = path.name
    if not flat or flat.startswith(".") or flat.lower() == "thumbs.db":
        return None
    if Path(flat).suffix.lower() not in ALLOWED_EXTENSIONS:
        return None
    return flat


def _archive_entries(archive: Path) -> tuple[list[tuple[str, int, Callable[[], BinaryIO]]], int, Any]:
    """
    Photo and video entries of a zip or tar(.gz), without extracting anything.

    Only regular files are kept (no links or devices), with paths flattened to
    their file name so nothing can be written outside the target folder.

    Returns:
        ([(flat_name, size, opener)], skipped_count, open_archive) — close the archive when done
    """
    entries: list[tuple[str, int, Callable[[], BinaryIO]]] = []
    skipped = 0
    if zipfile.is_zipfile(archive):
        zf = zipfile.ZipFile(archive)
        for info in zf.infolist():
            if info.is_dir():
                continue
            is_link = (info.external_attr >> 16) & 0o170000 == 0o120000
            flat = None if is_link else _keep(info.filename)
            if flat is None:
                skipped += 1
                continue
            entries.append((flat, info.file_size, lambda info=info: zf.open(info)))
        return entries, skipped, zf
    try:
        tf = tarfile.open(archive, "r:*")
    except tarfile.TarError as e:
        raise RecoveryError(400, f"Not a .zip or .tar.gz archive ({e})")
    for member in tf.getmembers():
        if member.isdir():
            continue
        flat = _keep(member.name) if member.isreg() else None
        if flat is None:
            skipped += 1
            continue
        entries.append((flat, member.size, lambda member=member: tf.extractfile(member)))
    return entries, skipped, tf


def _unique_name(name: str, taken: set[str]) -> str:
    """`name`, or `name_1.ext`, `name_2.ext`… if it's already taken (case-insensitive)."""
    stem, suffix = Path(name).stem, Path(name).suffix
    candidate, n = name, 0
    while candidate.lower() in taken:
        n += 1
        candidate = f"{stem}_{n}{suffix}"
    taken.add(candidate.lower())
    return candidate


def _extract_to_staging(archive: Path, staging: Path, album_dir: Path) -> dict[str, int]:
    """
    Unpack an archive's photos into `staging`, renaming any that clash with the album.

    Checks the file count and total size before writing anything (zip bomb guard),
    and stops any entry that turns out bigger than its header said.
    """
    entries, skipped, handle = _archive_entries(archive)
    try:
        if not entries:
            raise RecoveryError(400, "No photos or videos found in this archive.")
        if len(entries) > MAX_FILES:
            raise RecoveryError(413, f"Too many files ({len(entries)}); the limit is {MAX_FILES}.")
        total = sum(size for _, size, _ in entries)
        free = shutil.disk_usage(staging.parent).free - FREE_SPACE_MARGIN
        if total > min(MAX_TOTAL_BYTES, free):
            raise RecoveryError(
                507, f"Not enough space: the photos need {total / 1024 ** 3:.1f} GB "
                     f"and the frame can spare {max(free, 0) / 1024 ** 3:.1f} GB."
            )

        staging.mkdir(parents=True)
        taken = {p.name.lower() for p in album_dir.iterdir()} if album_dir.is_dir() else set()
        renamed = 0
        for flat, size, opener in entries:
            name = _unique_name(flat, taken)
            renamed += name != flat
            with opener() as src, open(staging / name, "wb") as dst:
                written = 0
                while chunk := src.read(1024 * 1024):
                    written += len(chunk)
                    if written > size:
                        raise RecoveryError(400, f"{flat} is bigger than the archive says; archive rejected.")
                    dst.write(chunk)
        return {"restored": len(entries), "renamed": renamed, "skipped": skipped}
    finally:
        handle.close()


async def restore_into_album(source: PhotoSource, archive: Path) -> dict[str, Any]:
    """
    Add an archive's photos to an album: staging → cloud folder → album folder.

    Returns:
        album, restored, renamed, skipped, uploaded_to_cloud

    Raises:
        RecoveryError: bad archive, too big, album syncing, or cloud upload failed
    """
    async with _restore_lock:
        if sync_service._is_syncing and sync_service._current_source == source.id:
            raise RecoveryError(409, "This album is syncing. Try again when the sync has finished.")

        album_dir = Path(source.local_path).expanduser()
        staging = backup_service.BACKUPS_DIR / f".staging-{uuid.uuid4().hex}"
        backup_service.BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            counts = await asyncio.to_thread(_extract_to_staging, archive, staging, album_dir)

            if source.rclone_remote:
                result = await rclone_copy_dir(staging, source.rclone_remote)
                if not result.success:
                    raise RecoveryError(
                        502, f"Couldn't upload the photos to the album's cloud folder ({result.error}). "
                             "Nothing was added to the album."
                    )

            album_dir.mkdir(parents=True, exist_ok=True)
            for staged in staging.iterdir():
                shutil.move(str(staged), str(album_dir / staged.name))
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    logger.info(
        f"Restored {counts['restored']} file(s) into album '{source.id}' from {archive.name} "
        f"({counts['renamed']} renamed, {counts['skipped']} skipped, cloud: {source.rclone_remote or 'none'})"
    )
    return {"album": source.id, **counts, "uploaded_to_cloud": bool(source.rclone_remote)}


# --- Target album -----------------------------------------------------------

async def resolve_target(target_id: Optional[str], new_name: Optional[str]) -> PhotoSource:
    """The album to restore into: an existing one, or a new one (with its own cloud folder)."""
    if target_id:
        source = sources.source_manager.get_source(target_id)
        if source is None:
            raise RecoveryError(404, f"Album '{target_id}' not found")
        return source
    name = (new_name or "").strip()
    if not 1 <= len(name) <= 50:
        raise RecoveryError(400, "Album name must be 1–50 characters")
    return await asyncio.to_thread(sources.source_manager.create_source, name)


# --- Backups ----------------------------------------------------------------

def list_all_backups() -> list[dict[str, Any]]:
    """Every backup in ~/Pictures/backups, newest first, marked when its album is gone."""
    names = {s.id: s.name for s in sources.source_manager.list_sources()}
    result = []
    if not backup_service.BACKUPS_DIR.is_dir():
        return result
    for f in backup_service.BACKUPS_DIR.glob("*.tar.gz"):
        m = BACKUP_NAME_RE.match(f.name)
        if not m:
            continue
        stat = f.stat()
        result.append({
            "filename": f.name,
            "album_id": m.group("id"),
            "album_name": names.get(m.group("id")),
            "album_exists": m.group("id") in names,
            "size_bytes": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })
    return sorted(result, key=lambda b: b["created_at"], reverse=True)


async def restore_backup(filename: str, target_id: Optional[str], new_name: Optional[str]) -> dict[str, Any]:
    """Restore a backup archive into an existing or new album."""
    if not BACKUP_NAME_RE.match(filename):
        raise RecoveryError(400, f"Invalid backup filename: {filename}")
    archive = backup_service.BACKUPS_DIR / filename
    if not archive.is_file():
        raise RecoveryError(404, f"Backup not found: {filename}")
    source = await resolve_target(target_id, new_name)
    return await restore_into_album(source, archive)


# --- Cloud folders ----------------------------------------------------------

async def _cloud_view() -> dict[str, Any]:
    """The frame registry's view of unused cloud folders, as a RecoveryError on failure."""
    try:
        return await frame_registry.cloud_view()
    except frame_registry.RegistryError as e:
        raise RecoveryError(e.status_code, e.message)


async def list_recoverable_cloud_folders() -> dict[str, Any]:
    """
    Cloud folders that can come back as albums, with photo counts (-1 on timeout).

    Returns:
        cloud: this frame's deleted albums; unclaimed: folders no frame claims
        (offered only after a warning unless the account is this frame's alone);
        unclaimed_needs_confirm; frames: other frames that can be taken over
    """
    view = await _cloud_view()

    async def count(folder: str) -> int:
        try:
            return await asyncio.wait_for(rclone_count(f"{view['remote']}:{folder}"), timeout=COUNT_TIMEOUT_SECONDS)
        except Exception:
            return -1

    entries = view["mine"] + view["unclaimed"]
    counts = dict(zip(
        (e["folder"] for e in entries),
        await asyncio.gather(*(count(e["folder"]) for e in entries)),
    ))

    def row(e: dict[str, Any]) -> dict[str, Any]:
        return {
            "folder": e["folder"],
            "photo_count": counts[e["folder"]],
            "suggested_name": e.get("name") or e["folder"][4:].replace("_", " "),
            "deleted_at": e.get("deleted_at"),
        }

    return {
        "cloud": [row(e) for e in view["mine"]],
        "unclaimed": [row(e) for e in view["unclaimed"]],
        "unclaimed_needs_confirm": not view["dedicated"],
        "frames": view["frames"],
    }


async def recover_from_cloud(folder: str, name: str, allow_unclaimed: bool = False) -> dict[str, Any]:
    """
    Re-add a deleted album pointed at its cloud folder, then start syncing it.

    Offered: this frame's own deleted albums; folders no frame claims when the
    account is this frame's alone, or with `allow_unclaimed` (the user accepted
    the shared-account warning). Never a folder another frame claims.

    Returns:
        album, name, cloud_folder, sync_started, message
    """
    if not CLOUD_FOLDER_RE.match(folder):
        raise RecoveryError(400, f"Invalid cloud folder: {folder}")
    name = name.strip()
    if not 1 <= len(name) <= 50:
        raise RecoveryError(400, "Album name must be 1–50 characters")
    view = await _cloud_view()
    mine = any(e["folder"] == folder for e in view["mine"])
    unclaimed = any(e["folder"] == folder for e in view["unclaimed"])
    if not (mine or (unclaimed and (view["dedicated"] or allow_unclaimed))):
        raise RecoveryError(
            409, f"{folder} can't be recovered here: it isn't one of this frame's albums, "
                 "or it's in use or no longer in the cloud."
        )

    rclone_remote = f"{view['remote']}:{folder}"
    source = await asyncio.to_thread(sources.source_manager.create_source, name, rclone_remote)
    logger.info(f"Recovered album '{source.id}' from cloud folder {rclone_remote}")
    if sync_service._is_syncing:
        return {
            "album": source.id, "name": source.name, "cloud_folder": rclone_remote, "sync_started": False,
            "message": "Album added. Another sync is running: sync it from the Albums table when that finishes.",
        }

    async def run_sync() -> None:
        try:
            await sync_service.sync_source(source.id, Path(source.local_path), rclone_remote)
        except RuntimeError as e:  # another sync started first
            logger.warning(f"Sync after recovering '{source.id}' didn't start: {e}")

    task = asyncio.create_task(run_sync())
    _pending.add(task)
    task.add_done_callback(_pending.discard)
    return {
        "album": source.id, "name": source.name, "cloud_folder": rclone_remote, "sync_started": True,
        "message": "Album added. Its photos are syncing to the frame now.",
    }

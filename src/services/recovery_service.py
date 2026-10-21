"""
WanderWall - Album Recovery (PL-147 follow-up).

Gets albums back after Delete Album, from the dashboard:
- from its cloud folder (re-adds the album pointed at it): this frame's own
  deleted albums, per the frame registry; folders another frame sharing the
  cloud account claims are never offered
- from a .tar.gz backup in ~/Pictures/backups, including a deleted album's,
  or a whole-frame backup, which restores every album in one go (PL-164)
- from a .zip / .tar.gz of photos uploaded from the computer

Sync mirrors the cloud onto the frame (rclone sync), so a photo that is only
on the frame is deleted by the next sync. Restores therefore unpack into a
staging folder, copy it to the album's cloud folder first, and only then move
the files into the album.
"""

import asyncio
import filecmp
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
FREE_SPACE_MARGIN = backup_service.FREE_SPACE_MARGIN
# An upload can be a whole-frame backup (PL-164), so the limit is high; free space caps it too
MAX_UPLOAD_BYTES = 16 * 1024 ** 3
FRAME_MAX_FILES = 200_000
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


Entry = tuple[str, str, int, Callable[[], BinaryIO]]


def _top_folder(name: str) -> str:
    """The first folder of an archive path ('' for a file at the root)."""
    parts = [p for p in PurePosixPath(name.replace("\\", "/")).parts if p not in ("/", ".", "")]
    return parts[0] if len(parts) > 1 else ""


def _archive_entries(archive: Path) -> tuple[list[Entry], int, Any]:
    """
    Photo and video entries of a zip or tar(.gz), without extracting anything.

    Only regular files are kept (no links or devices), with paths flattened to
    their file name so nothing can be written outside the target folder. Each
    entry also carries its top folder, which a whole-frame backup uses to tell
    albums apart.

    Returns:
        ([(top_folder, flat_name, size, opener)], skipped_count, open_archive) — close the archive when done
    """
    entries: list[Entry] = []
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
            entries.append((_top_folder(info.filename), flat, info.file_size, lambda info=info: zf.open(info)))
        return entries, skipped, zf
    try:
        tf = tarfile.open(archive, "r:*")
    except tarfile.TarError as e:
        raise RecoveryError(400, f"Not a .zip or .tar.gz archive ({e})")
    for member in tf.getmembers():
        if member.isdir() or member.name == backup_service.MANIFEST_NAME:
            continue
        flat = _keep(member.name) if member.isreg() else None
        if flat is None:
            skipped += 1
            continue
        entries.append((_top_folder(member.name), flat, member.size, lambda member=member: tf.extractfile(member)))
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


def _check_limits(entries: list[Entry], staging_parent: Path, max_files: int, max_bytes: int) -> None:
    """Refuse an archive with too many files or more bytes than the limit or the free space (zip bomb guard)."""
    if not entries:
        raise RecoveryError(400, "No photos or videos found in this archive.")
    if len(entries) > max_files:
        raise RecoveryError(413, f"Too many files ({len(entries)}); the limit is {max_files}.")
    total = sum(size for _, _, size, _ in entries)
    free = shutil.disk_usage(staging_parent).free - FREE_SPACE_MARGIN
    if total > min(max_bytes, free):
        raise RecoveryError(
            507, f"Not enough space: the photos need {total / 1024 ** 3:.1f} GB "
                 f"and the frame can spare {max(free, 0) / 1024 ** 3:.1f} GB."
        )


def _already_have(tmp: Path, size: int, flat: str, existing: dict[str, Path]) -> bool:
    """True if the album has this photo as `flat` or as an earlier restore's `stem_N.ext`, byte for byte."""
    stem, suffix = Path(flat).stem, Path(flat).suffix
    candidate, n = flat, 0
    while (same := existing.get(candidate.lower())) is not None:
        if same.stat().st_size == size and filecmp.cmp(tmp, same, shallow=False):
            return True
        n += 1
        candidate = f"{stem}_{n}{suffix}"
    return False


def _stage(entries: list[Entry], staging: Path, album_dir: Path) -> dict[str, int]:
    """
    Unpack entries into `staging`, skipping photos the album already has.

    A photo already there (same name, same size, same bytes) is skipped, so a
    restore onto an album that still has its photos adds only what's missing and
    running it twice changes nothing. Same name but different content is saved
    as name_1.ext. Stops any entry that turns out bigger than its header said.

    Returns:
        restored (added), already_there, renamed
    """
    staging.mkdir(parents=True, exist_ok=True)
    existing = {p.name.lower(): p for p in album_dir.iterdir() if p.is_file()} if album_dir.is_dir() else {}
    taken = set(existing)
    restored = already_there = renamed = 0
    for _, flat, size, opener in entries:
        tmp = staging / f".part-{uuid.uuid4().hex}"
        with opener() as src, open(tmp, "wb") as dst:
            written = 0
            while chunk := src.read(1024 * 1024):
                written += len(chunk)
                if written > size:
                    raise RecoveryError(400, f"{flat} is bigger than the archive says; archive rejected.")
                dst.write(chunk)
        if _already_have(tmp, written, flat, existing):
            tmp.unlink()
            already_there += 1
            continue
        name = _unique_name(flat, taken)
        renamed += name != flat
        tmp.rename(staging / name)
        # A later entry with the same name and bytes (flattened subfolders) is a duplicate too
        existing.setdefault(name.lower(), staging / name)
        restored += 1
    return {"restored": restored, "already_there": already_there, "renamed": renamed}


def _extract_to_staging(archive: Path, staging: Path, album_dir: Path) -> dict[str, int]:
    """Unpack an archive's photos into `staging` for one album (see _stage)."""
    entries, skipped, handle = _archive_entries(archive)
    try:
        _check_limits(entries, staging.parent, MAX_FILES, MAX_TOTAL_BYTES)
        return {**_stage(entries, staging, album_dir), "skipped": skipped}
    finally:
        handle.close()


def _check_not_syncing(source: PhotoSource) -> None:
    """Refuse to restore into an album while it syncs (the sync would remove the new photos)."""
    if sync_service._is_syncing and sync_service._current_source == source.id:
        raise RecoveryError(409, f"Album '{source.name}' is syncing. Try again when the sync has finished.")


async def _commit_staging(source: PhotoSource, staging: Path) -> None:
    """Copy staged photos to the album's cloud folder first, then move them into the album."""
    staged = [p for p in staging.iterdir() if not p.name.startswith(".part-")] if staging.is_dir() else []
    if not staged:
        return
    if source.rclone_remote:
        result = await rclone_copy_dir(staging, source.rclone_remote)
        if not result.success:
            raise RecoveryError(
                502, f"Couldn't upload the photos to the album's cloud folder ({result.error}). "
                     "Nothing was added to the album."
            )
    album_dir = Path(source.local_path).expanduser()
    album_dir.mkdir(parents=True, exist_ok=True)
    for f in staged:
        shutil.move(str(f), str(album_dir / f.name))


def _new_staging() -> Path:
    """A fresh staging folder in ~/Pictures/backups (not /tmp, which can be RAM)."""
    backup_service.BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    return backup_service.BACKUPS_DIR / f".staging-{uuid.uuid4().hex}"


async def restore_into_album(source: PhotoSource, archive: Path) -> dict[str, Any]:
    """
    Add an archive's photos to an album: staging → cloud folder → album folder.

    Returns:
        album, restored, already_there, renamed, skipped, uploaded_to_cloud

    Raises:
        RecoveryError: bad archive, too big, album syncing, or cloud upload failed
    """
    async with _restore_lock:
        _check_not_syncing(source)
        staging = _new_staging()
        try:
            counts = await asyncio.to_thread(
                _extract_to_staging, archive, staging, Path(source.local_path).expanduser())
            await _commit_staging(source, staging)
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    logger.info(
        f"Restored {counts['restored']} file(s) into album '{source.id}' from {archive.name} "
        f"({counts['already_there']} already there, {counts['renamed']} renamed, {counts['skipped']} skipped, "
        f"cloud: {source.rclone_remote or 'none'})"
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

def _frame_manifest(f: Path) -> Optional[dict[str, Any]]:
    """The manifest if f is a whole-frame backup (frame_… with a readable manifest), else None."""
    if not f.name.startswith(backup_service.FRAME_PREFIX):
        return None
    try:
        return backup_service.read_frame_manifest(f)
    except ValueError:
        return None


def list_all_backups() -> list[dict[str, Any]]:
    """
    Every backup in ~/Pictures/backups, newest first.

    Album backups are marked when their album is gone; whole-frame backups have
    kind "frame" with their album count.
    """
    names = {s.id: s.name for s in sources.source_manager.list_sources()}
    result = []
    if not backup_service.BACKUPS_DIR.is_dir():
        return result
    for f in backup_service.BACKUPS_DIR.glob("*.tar.gz"):
        m = BACKUP_NAME_RE.match(f.name)
        if not m:
            continue
        stat = f.stat()
        row = {
            "filename": f.name,
            "path": str(f),
            "size_bytes": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        }
        manifest = _frame_manifest(f)
        if manifest:
            row.update(kind="frame", frame_name=manifest["frame_name"], album_count=len(manifest["albums"]),
                       album_id=None, album_name=None, album_exists=False)
        else:
            row.update(kind="album", album_id=m.group("id"), album_name=names.get(m.group("id")),
                       album_exists=m.group("id") in names)
        result.append(row)
    return sorted(result, key=lambda b: b["created_at"], reverse=True)


async def restore_backup(filename: str, target_id: Optional[str], new_name: Optional[str]) -> dict[str, Any]:
    """Restore a backup archive into an existing or new album, or every album for a whole-frame backup."""
    if not BACKUP_NAME_RE.match(filename):
        raise RecoveryError(400, f"Invalid backup filename: {filename}")
    archive = backup_service.BACKUPS_DIR / filename
    if not archive.is_file():
        raise RecoveryError(404, f"Backup not found: {filename}")
    if filename.startswith(backup_service.FRAME_PREFIX) and await asyncio.to_thread(frame_manifest_or_error, archive):
        return await restore_frame_backup(archive)
    source = await resolve_target(target_id, new_name)
    return await restore_into_album(source, archive)


# --- Whole-frame backups (PL-164) -------------------------------------------

def frame_manifest_or_error(archive: Path) -> Optional[dict[str, Any]]:
    """The archive's whole-frame manifest, None if it isn't one; RecoveryError if it's malformed."""
    try:
        return backup_service.read_frame_manifest(archive)
    except ValueError as e:
        raise RecoveryError(400, str(e))


def _free_cloud_folder(base: str, taken: set[str]) -> str:
    """KFR_<base>, or KFR_<base>_2, _3… so a restored album never shares another frame's folder."""
    base = re.sub(r"[^A-Za-z0-9_]", "_", base)[:60] or "album"
    folder, n = f"KFR_{base}", 1
    while folder in taken:
        n += 1
        folder = f"KFR_{base}_{n}"
    taken.add(folder)
    return folder


async def _frame_targets(albums: list[dict[str, Any]]) -> list[tuple[dict[str, Any], PhotoSource, str]]:
    """
    The album on this frame each manifest album restores into, created if needed.

    - an album on this frame with the same id, cloud folder or name → merge into it
    - this frame's deleted album on the same cloud folder → re-add it on that folder
    - otherwise a new album on a cloud folder nobody uses (never another frame's)

    Returns:
        [(manifest album, target album, "merged" | "recovered" | "created")]
    """
    current = sources.source_manager.list_sources()

    def existing(album: dict[str, Any]) -> Optional[PhotoSource]:
        for match in (
            lambda s: s.id == album["id"],
            lambda s: album["cloud_folder"] and frame_registry._folder_of(s.rclone_remote) == album["cloud_folder"],
            lambda s: s.name.strip().lower() == album["name"].lower(),
        ):
            found = next((s for s in current if match(s)), None)
            if found:
                return found
        return None

    missing = [a for a in albums if existing(a) is None]
    remote, mine, taken = None, set(), set()
    if missing:
        remote = await frame_registry._koofr_remote()
        if remote:
            view = await _cloud_view()
            dirs = await frame_registry.rclone_list_dirs(f"{remote}:")
            if dirs is None:
                raise RecoveryError(502, "Couldn't list the cloud storage folders.")
            mine = {e["folder"] for e in view["mine"]}
            taken = set(dirs)

    targets = []
    for album in albums:
        found = existing(album)
        if found:
            targets.append((album, found, "merged"))
            continue
        if remote and album["cloud_folder"] in mine:
            mine.discard(album["cloud_folder"])
            source = await asyncio.to_thread(
                sources.source_manager.create_source, album["name"], f"{remote}:{album['cloud_folder']}")
            targets.append((album, source, "recovered"))
            continue
        if remote:
            folder = _free_cloud_folder(album["id"], taken)
            source = await asyncio.to_thread(sources.source_manager.create_source, album["name"], f"{remote}:{folder}")
        else:
            source = await asyncio.to_thread(sources.source_manager.create_source, album["name"])
        targets.append((album, source, "created"))
    return targets


async def restore_frame_backup(archive: Path) -> dict[str, Any]:
    """
    Restore every album in a whole-frame backup, in one go.

    Albums still on the frame get only the photos they're missing (identical ones
    are skipped), so restoring onto a running frame duplicates nothing and running
    it twice is safe. Deleted or missing albums are created again. Each album goes
    staging → cloud folder → album folder, like a single-album restore.

    Returns:
        frame_name, albums [{album, name, action, restored, already_there, renamed}], skipped

    Raises:
        RecoveryError: bad archive or manifest, too big, an album syncing, or a cloud upload
        failed (the message says which albums were already done)
    """
    manifest = await asyncio.to_thread(frame_manifest_or_error, archive)
    if not manifest:
        raise RecoveryError(400, "This isn't a whole-frame backup.")
    async with _restore_lock:
        entries, skipped, handle = await asyncio.to_thread(_archive_entries, archive)
        try:
            folders = {a["folder"] for a in manifest["albums"]}
            stray = sum(1 for e in entries if e[0] not in folders)
            entries = [e for e in entries if e[0] in folders]
            _check_limits(entries, backup_service.BACKUPS_DIR, FRAME_MAX_FILES, MAX_UPLOAD_BYTES)
            targets = await _frame_targets(manifest["albums"])
            for _, source, _ in targets:
                _check_not_syncing(source)

            done: list[dict[str, Any]] = []
            for album, source, action in targets:
                staging = _new_staging()
                try:
                    album_entries = [e for e in entries if e[0] == album["folder"]]
                    counts = await asyncio.to_thread(
                        _stage, album_entries, staging, Path(source.local_path).expanduser())
                    await _commit_staging(source, staging)
                except RecoveryError as e:
                    finished = ", ".join(d["name"] for d in done) or "none"
                    raise RecoveryError(e.status_code, f'{album["name"]}: {e.message} Albums already restored: {finished}. '
                                                       "Restoring again is safe: photos already there are skipped.")
                finally:
                    shutil.rmtree(staging, ignore_errors=True)
                done.append({"album": source.id, "name": source.name, "action": action, **counts})
        finally:
            handle.close()

    logger.info(f"Restored whole-frame backup {archive.name}: " + "; ".join(
        f"{d['album']} {d['action']} +{d['restored']} ({d['already_there']} already there)" for d in done))
    return {"kind": "frame", "frame_name": manifest["frame_name"], "albums": done, "skipped": skipped + stray}


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

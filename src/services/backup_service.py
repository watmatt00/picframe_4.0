"""
WanderWall - Backup Service.

Creates and manages tar.gz backups of photo source local directories.
Backups are stored in ~/Pictures/backups/:
- one album: <album_id>_<YYYY-MM-DD_HHMMSS>.tar.gz, the album's folder
- whole frame (PL-164): frame_<frame>_<YYYY-MM-DD_HHMMSS>.tar.gz, manifest.yaml
  first (frame and album names, cloud folders), then one folder per album
"""

import asyncio
import logging
import re
import shutil
import tarfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml

logger = logging.getLogger(__name__)

BACKUPS_DIR = Path.home() / "Pictures" / "backups"
BACKUP_FILENAME_RE = re.compile(r'^[a-z0-9_-]+_\d{4}-\d{2}-\d{2}_\d{6}\.tar\.gz$')
# Space left free on the disk after a backup or restore (recovery_service uses it too)
FREE_SPACE_MARGIN = 1024 ** 3
MANIFEST_NAME = "manifest.yaml"
MANIFEST_KIND = "wanderwall-frame-backup"
MANIFEST_MAX_BYTES = 1024 * 1024
FRAME_PREFIX = "frame_"
# Album ids and archive folder names in a manifest: no slashes, no leading dot
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}$")


def _belongs_to(filename: str, source_id: str) -> bool:
    """True if filename is exactly <source_id>_<timestamp>.tar.gz."""
    return re.fullmatch(rf"{re.escape(source_id)}_\d{{4}}-\d{{2}}-\d{{2}}_\d{{6}}\.tar\.gz", filename) is not None


def _folder_size(path: Path) -> int:
    """Total size in bytes of the regular files under path (symlinks not followed)."""
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file() and not f.is_symlink())


def _check_free_space(needed: int) -> None:
    """Raise ValueError if needed bytes won't fit in BACKUPS_DIR with the margin left free."""
    free = shutil.disk_usage(BACKUPS_DIR).free - FREE_SPACE_MARGIN
    if needed > free:
        raise ValueError(
            f"Not enough free space: the backup needs about {needed // 1024 ** 2} MB, "
            f"{max(free, 0) // 1024 ** 2} MB is free (1 GB is kept free)"
        )


def list_backups(source_id: str) -> list[dict]:
    """List existing tar.gz backups for the given source, newest first.

    Args:
        source_id: The photo source identifier.

    Returns:
        List of dicts with filename, size_bytes, and created_at (ISO 8601).
    """
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    result = []
    for f in sorted(BACKUPS_DIR.glob(f"{source_id}_*.tar.gz"), reverse=True):
        if not _belongs_to(f.name, source_id):  # "trip_*" also matches album trip_2's backups
            continue
        stat = f.stat()
        result.append({
            "filename": f.name,
            "path": str(f),
            "size_bytes": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })
    return result


async def _run_tar(tar_path: Path, args: list[str]) -> None:
    """Run tar czf tar_path <args>; remove a partial archive and raise RuntimeError if it fails."""
    proc = await asyncio.create_subprocess_exec(
        "tar", "czf", str(tar_path), *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        tar_path.unlink(missing_ok=True)
        raise RuntimeError(f"tar failed: {stderr.decode().strip()}")


async def create_backup(source_id: str, local_path: str) -> dict:
    """Create a tar.gz backup of the source's local photo directory.

    Args:
        source_id: The photo source identifier (used for archive name).
        local_path: Absolute path to the source's local photo directory.

    Returns:
        Dict with filename and size_bytes of the created archive.

    Raises:
        ValueError: If local_path does not exist or there isn't enough free space.
        RuntimeError: If tar fails.
    """
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    src = Path(local_path).expanduser()
    if not src.exists():
        raise ValueError(f"Source path does not exist: {local_path}")
    _check_free_space(await asyncio.to_thread(_folder_size, src))
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    tar_name = f"{source_id}_{timestamp}.tar.gz"
    tar_path = BACKUPS_DIR / tar_name
    logger.info("Creating backup: %s", tar_path)
    await _run_tar(tar_path, ["-C", str(src.parent), src.name])
    stat = tar_path.stat()
    logger.info("Backup created: %s (%d bytes)", tar_name, stat.st_size)
    return {"filename": tar_name, "size_bytes": stat.st_size}


def _count_files(path: Path) -> int:
    """Number of regular files under path (symlinks not followed)."""
    return sum(1 for f in path.rglob("*") if f.is_file() and not f.is_symlink())


async def create_frame_backup(sources: Iterable[Any], frame_name: str, serial: Optional[str]) -> dict:
    """Back up every album into one archive, with a manifest so it can be restored in one go.

    Free space is checked for the whole set first. Albums with no folder on the
    frame yet are left out and listed in `skipped`.

    Args:
        sources: Albums with id, name, local_path and rclone_remote (source_manager.list_sources()).
        frame_name: This frame's name (archive name and manifest).
        serial: This Pi's board serial (manifest), or None.

    Returns:
        Dict with filename, path, size_bytes, albums (count) and skipped (album ids).

    Raises:
        ValueError: No albums to back up, two album folders with the same name, or not enough free space.
        RuntimeError: If tar fails (no archive is left behind).
    """
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    todo, skipped = [], []
    for source in sources:
        path = Path(source.local_path).expanduser()
        (todo if path.is_dir() else skipped).append((source, path))
    if not todo:
        raise ValueError("This frame has no albums with photos to back up.")
    folders = [path.name for _, path in todo]
    if len(set(folders)) != len(folders) or not all(SAFE_NAME_RE.match(f) for f in folders):
        raise ValueError("Two albums use folders with the same name; back them up one at a time.")
    _check_free_space(sum(await asyncio.gather(*(asyncio.to_thread(_folder_size, p) for _, p in todo))))

    counts = await asyncio.gather(*(asyncio.to_thread(_count_files, p) for _, p in todo))
    manifest = {
        "kind": MANIFEST_KIND,
        "version": 1,
        "frame_name": frame_name,
        "serial": serial,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "albums": [
            {
                "id": source.id,
                "name": source.name,
                "folder": path.name,
                "cloud_folder": source.rclone_remote.split(":", 1)[1] if source.rclone_remote and ":" in source.rclone_remote else None,
                "photo_count": count,
            }
            for (source, path), count in zip(todo, counts)
        ],
    }
    slug = re.sub(r"[^a-z0-9-]+", "-", frame_name.lower()).strip("-")[:30] or "frame"
    tar_name = f"{FRAME_PREFIX}{slug}_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.tar.gz"
    tar_path = BACKUPS_DIR / tar_name
    meta = BACKUPS_DIR / f".frame-{uuid.uuid4().hex}"
    meta.mkdir()
    try:
        (meta / MANIFEST_NAME).write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True))
        # The manifest goes first, so listing and restoring can read it without unpacking the rest
        args = ["-C", str(meta), MANIFEST_NAME]
        for _, path in todo:
            args += ["-C", str(path.parent), path.name]
        logger.info("Creating whole-frame backup: %s (%d albums)", tar_path, len(todo))
        await _run_tar(tar_path, args)
    finally:
        shutil.rmtree(meta, ignore_errors=True)
    size = tar_path.stat().st_size
    logger.info("Whole-frame backup created: %s (%d bytes)", tar_name, size)
    return {
        "filename": tar_name,
        "path": str(tar_path),
        "size_bytes": size,
        "albums": len(todo),
        "skipped": [s.id for s, _ in skipped],
    }


def read_frame_manifest(archive: Path) -> Optional[dict]:
    """The manifest of a whole-frame backup, or None if the archive isn't one.

    Only the first member is read (create_frame_backup writes the manifest first).

    Raises:
        ValueError: It says it's a whole-frame backup but the manifest is malformed.
    """
    try:
        with tarfile.open(archive, "r:*") as tf:
            first = tf.next()
            if first is None or first.name != MANIFEST_NAME or not first.isreg() or first.size > MANIFEST_MAX_BYTES:
                return None
            data = yaml.safe_load(tf.extractfile(first).read())
    except (tarfile.TarError, OSError, EOFError, yaml.YAMLError):
        return None
    if not isinstance(data, dict) or data.get("kind") != MANIFEST_KIND:
        return None
    if data.get("version") != 1 or not isinstance(data.get("albums"), list) or not data["albums"]:
        raise ValueError("This whole-frame backup's manifest isn't one this frame can read.")
    albums = []
    for a in data["albums"]:
        if not isinstance(a, dict):
            raise ValueError("Malformed album in the whole-frame backup's manifest.")
        aid, folder, name = str(a.get("id") or ""), str(a.get("folder") or ""), str(a.get("name") or "").strip()
        cloud = a.get("cloud_folder")
        if not (SAFE_NAME_RE.match(aid) and SAFE_NAME_RE.match(folder) and 1 <= len(name) <= 50):
            raise ValueError(f"Malformed album in the whole-frame backup's manifest: {aid or '?'}")
        albums.append({
            "id": aid, "name": name, "folder": folder,
            "cloud_folder": str(cloud) if cloud and SAFE_NAME_RE.match(str(cloud)) else None,
            "photo_count": int(a.get("photo_count") or 0),
        })
    if len({a["folder"] for a in albums}) != len(albums):
        raise ValueError("The whole-frame backup's manifest lists the same folder twice.")
    return {
        "frame_name": str(data.get("frame_name") or "")[:50],
        "serial": data.get("serial"),
        "created_at": data.get("created_at"),
        "albums": albums,
    }


def backup_path(filename: str) -> Path:
    """The path of an existing backup archive, with name and path traversal checks.

    Raises:
        ValueError: If filename is invalid.
        FileNotFoundError: If the archive does not exist.
    """
    if not BACKUP_FILENAME_RE.match(filename):
        raise ValueError(f"Invalid backup filename: {filename}")
    path = BACKUPS_DIR / filename
    path.relative_to(BACKUPS_DIR)  # path traversal guard
    if not path.is_file():
        raise FileNotFoundError(f"Backup not found: {filename}")
    return path


def delete_backup(source_id: str, filename: str) -> None:
    """Delete one of an album's backup archives.

    Args:
        source_id: The photo source identifier (ensures the file belongs to it).
        filename: The archive filename (must match expected pattern).

    Raises:
        ValueError: If filename is invalid or belongs to a different source.
        FileNotFoundError: If the archive does not exist.
    """
    if not _belongs_to(filename, source_id):
        raise ValueError("Backup does not belong to this source")
    delete_backup_file(filename)


def delete_backup_file(filename: str) -> None:
    """Delete a backup archive by name (any album's, deleted ones too) with path traversal protection.

    Args:
        filename: The archive filename (must match expected pattern).

    Raises:
        ValueError: If filename is invalid.
        FileNotFoundError: If the archive does not exist.
    """
    backup_path(filename).unlink()
    logger.info("Backup deleted: %s", filename)

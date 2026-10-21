"""
WanderWall - Backup Service.

Creates and manages tar.gz backups of photo source local directories.
Backups are stored in ~/Pictures/backups/.
"""

import asyncio
import logging
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

BACKUPS_DIR = Path.home() / "Pictures" / "backups"
BACKUP_FILENAME_RE = re.compile(r'^[a-z0-9_-]+_\d{4}-\d{2}-\d{2}_\d{6}\.tar\.gz$')
# Space left free on the disk after a backup or restore (recovery_service uses it too)
FREE_SPACE_MARGIN = 1024 ** 3


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
            "size_bytes": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })
    return result


async def create_backup(
    source_id: str, local_path: str, timestamp: Optional[str] = None, check_space: bool = True,
) -> dict:
    """Create a tar.gz backup of the source's local photo directory.

    Args:
        source_id: The photo source identifier (used for archive name).
        local_path: Absolute path to the source's local photo directory.
        timestamp: Archive timestamp (YYYY-mm-dd_HHMMSS); a whole-frame backup
            passes one so all its archives share it. Defaults to now.
        check_space: Check free space first (create_all_backups checks the whole set).

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
    if check_space:
        _check_free_space(await asyncio.to_thread(_folder_size, src))
    timestamp = timestamp or datetime.now().strftime("%Y-%m-%d_%H%M%S")
    tar_name = f"{source_id}_{timestamp}.tar.gz"
    tar_path = BACKUPS_DIR / tar_name
    logger.info("Creating backup: %s", tar_path)
    proc = await asyncio.create_subprocess_exec(
        "tar", "czf", str(tar_path), "-C", str(src.parent), src.name,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        if tar_path.exists():
            tar_path.unlink()
        raise RuntimeError(f"tar failed: {stderr.decode().strip()}")
    stat = tar_path.stat()
    logger.info("Backup created: %s (%d bytes)", tar_name, stat.st_size)
    return {"filename": tar_name, "size_bytes": stat.st_size}


async def create_all_backups(sources: Iterable[Any]) -> dict:
    """Back up every album, one archive per album, all with the same timestamp.

    Free space is checked for the whole set first, so it doesn't fail halfway.

    Args:
        sources: Albums with id and local_path (source_manager.list_sources()).

    Returns:
        Dict with created (filename, size_bytes per archive), skipped (album ids
        with no folder on the frame) and total_bytes.

    Raises:
        ValueError: If there isn't enough free space for the set.
        RuntimeError: If tar fails (archives already made are kept).
    """
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    todo, skipped = [], []
    for source in sources:
        path = Path(source.local_path).expanduser()
        (todo if path.is_dir() else skipped).append(source)
    _check_free_space(sum(await asyncio.gather(
        *(asyncio.to_thread(_folder_size, Path(s.local_path).expanduser()) for s in todo)
    )))
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    created = []
    for source in todo:
        created.append(await create_backup(source.id, source.local_path, timestamp, check_space=False))
    return {
        "created": created,
        "skipped": [s.id for s in skipped],
        "total_bytes": sum(c["size_bytes"] for c in created),
    }


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
    if not BACKUP_FILENAME_RE.match(filename):
        raise ValueError(f"Invalid backup filename: {filename}")
    backup_path = BACKUPS_DIR / filename
    backup_path.relative_to(BACKUPS_DIR)  # path traversal guard
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup not found: {filename}")
    backup_path.unlink()
    logger.info("Backup deleted: %s", filename)

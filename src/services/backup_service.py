"""
PicFrame 4.0 - Backup Service.

Creates and manages tar.gz backups of photo source local directories.
Backups are stored in ~/Pictures/backups/.
"""

import asyncio
import logging
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

BACKUPS_DIR = Path.home() / "Pictures" / "backups"
BACKUP_FILENAME_RE = re.compile(r'^[a-z0-9_-]+_\d{4}-\d{2}-\d{2}_\d{6}\.tar\.gz$')


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
        stat = f.stat()
        result.append({
            "filename": f.name,
            "size_bytes": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })
    return result


async def create_backup(source_id: str, local_path: str) -> dict:
    """Create a tar.gz backup of the source's local photo directory.

    Args:
        source_id: The photo source identifier (used for archive name).
        local_path: Absolute path to the source's local photo directory.

    Returns:
        Dict with filename and size_bytes of the created archive.

    Raises:
        ValueError: If local_path does not exist.
        RuntimeError: If tar fails.
    """
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    src = Path(local_path).expanduser()
    if not src.exists():
        raise ValueError(f"Source path does not exist: {local_path}")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
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


def delete_backup(source_id: str, filename: str) -> None:
    """Delete a backup archive with path traversal protection.

    Args:
        source_id: The photo source identifier (ensures the file belongs to it).
        filename: The archive filename (must match expected pattern).

    Raises:
        ValueError: If filename is invalid or belongs to a different source.
        FileNotFoundError: If the archive does not exist.
    """
    if not BACKUP_FILENAME_RE.match(filename):
        raise ValueError(f"Invalid backup filename: {filename}")
    if not filename.startswith(f"{source_id}_"):
        raise ValueError("Backup does not belong to this source")
    backup_path = BACKUPS_DIR / filename
    backup_path.relative_to(BACKUPS_DIR)  # path traversal guard
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup not found: {filename}")
    backup_path.unlink()
    logger.info("Backup deleted: %s", filename)

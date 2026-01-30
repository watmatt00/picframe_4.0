"""
PicFrame 4.0 - rclone Wrapper.

Python wrapper for rclone operations (no shell scripts).
"""

import asyncio
import logging
import re
from typing import Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class RcloneResult(BaseModel):
    """Result of an rclone operation."""
    success: bool
    files_transferred: int = 0
    files_deleted: int = 0
    bytes_transferred: int = 0
    error: Optional[str] = None
    output: str = ""


async def rclone_sync(
    source: str,
    dest: str,
    extra_flags: list[str] | None = None,
) -> RcloneResult:
    """
    Sync files from source to destination using rclone.

    Args:
        source: Source path (can be remote like "koofr:folder")
        dest: Destination path (usually local)
        extra_flags: Additional rclone flags

    Returns:
        RcloneResult with operation details
    """
    # Validate inputs to prevent command injection
    if not _validate_remote(source):
        return RcloneResult(success=False, error=f"Invalid source: {source}")
    if not _validate_path(dest):
        return RcloneResult(success=False, error=f"Invalid destination: {dest}")

    cmd = ["rclone", "sync", source, dest, "--stats-one-line", "-v"]

    if extra_flags:
        # Filter potentially dangerous flags
        safe_flags = [f for f in extra_flags if _is_safe_flag(f)]
        cmd.extend(safe_flags)

    logger.info(f"Running: {' '.join(cmd)}")

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode()

        if proc.returncode == 0:
            # Parse output for stats
            transferred = _parse_transferred(output)
            return RcloneResult(
                success=True,
                files_transferred=transferred,
                output=output,
            )
        else:
            return RcloneResult(
                success=False,
                error=f"rclone exited with code {proc.returncode}",
                output=output,
            )

    except FileNotFoundError:
        return RcloneResult(
            success=False,
            error="rclone not found. Please install rclone.",
        )
    except Exception as e:
        return RcloneResult(success=False, error=str(e))


async def rclone_count(remote: str) -> int:
    """
    Count files in a remote.

    Args:
        remote: Remote path to count

    Returns:
        Number of files
    """
    if not _validate_remote(remote):
        raise ValueError(f"Invalid remote: {remote}")

    cmd = ["rclone", "size", remote, "--json"]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()

        if proc.returncode == 0:
            import json
            data = json.loads(stdout.decode())
            return data.get("count", 0)
        return 0

    except Exception as e:
        logger.error(f"Failed to count remote files: {e}")
        return 0


async def rclone_check(remote: str) -> bool:
    """
    Check if an rclone remote is accessible.

    Args:
        remote: Remote to check (e.g., "koofr:")

    Returns:
        True if remote is accessible
    """
    if not _validate_remote(remote):
        return False

    cmd = ["rclone", "lsd", remote, "--max-depth", "0"]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return proc.returncode == 0

    except Exception:
        return False


def _validate_remote(remote: str) -> bool:
    """Validate an rclone remote specification."""
    # Allow: name:path or /local/path
    if remote.startswith("/"):
        return _validate_path(remote)
    # Remote format: name:path
    if ":" not in remote:
        return False
    name, path = remote.split(":", 1)
    # Name should be alphanumeric + underscore
    if not re.match(r"^[a-zA-Z0-9_-]+$", name):
        return False
    return True


def _validate_path(path: str) -> bool:
    """Validate a local path (no traversal)."""
    if ".." in path:
        return False
    if not path.startswith("/"):
        return False
    return True


def _is_safe_flag(flag: str) -> bool:
    """Check if an rclone flag is safe to use."""
    # Blacklist dangerous flags
    dangerous = {
        "--config",
        "--delete-before",
        "--delete-during",
        "--delete-after",
        "--delete-excluded",
    }
    return flag.split("=")[0] not in dangerous


def _parse_transferred(output: str) -> int:
    """Parse the number of transferred files from rclone output."""
    # Look for patterns like "Transferred: 5 / 5"
    match = re.search(r"Transferred:\s*(\d+)", output)
    if match:
        return int(match.group(1))
    return 0

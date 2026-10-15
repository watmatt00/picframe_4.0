"""
PicFrame 4.0 - Main entry point.

Usage:
    uvicorn src.api.app:app --host 0.0.0.0 --port 8000

Or via CLI:
    picframe-api
"""

import logging
import tempfile
from pathlib import Path

import uvicorn

from src.config.settings import get_settings
from src.utils.logging import setup_logging

logger = logging.getLogger(__name__)

# /tmp is RAM-backed (tmpfs) on Raspberry Pi OS trixie. Upload spool files and
# temp copies go here instead so a large upload doesn't use RAM (PL-060).
DISK_TEMP_DIR = Path.home() / "picframe_data" / "tmp"


def use_disk_tempdir(path: Path = DISK_TEMP_DIR) -> None:
    """
    Point tempfile (and so Starlette's upload spool files) at a directory on disk.

    Leftover picframe_upload_* files from a crash are removed. Falls back to the
    system default if the directory can't be created.

    Args:
        path: Directory to use for temporary files.
    """
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.chmod(0o700)
        for stale in path.glob("picframe_upload_*"):
            stale.unlink(missing_ok=True)
    except OSError as e:
        logger.warning(f"Temp dir {path} unavailable, using system default: {e}")
        return
    tempfile.tempdir = str(path)
    logger.info(f"Temporary files in {path}")


def main():
    """Run the PicFrame API server."""
    # Initialize settings and logging
    settings = get_settings()
    setup_logging(
        level=settings.logging.level,
        ops_retention_days=settings.logging.retention_days,
        security_retention_days=settings.logging.security_retention_days,
    )
    use_disk_tempdir()

    uvicorn.run(
        "src.api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        # Tailscale Funnel/Serve proxies from 127.0.0.1. Trust X-Forwarded-For only
        # from there so request.client is the real caller; LANOnlyMiddleware relies on it.
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
    )


if __name__ == "__main__":
    main()

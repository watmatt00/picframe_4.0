"""
PicFrame 4.0 - Main entry point.

Usage:
    uvicorn src.api.app:app --host 0.0.0.0 --port 8000

Or via CLI:
    picframe-api
"""

import uvicorn

from src.config.settings import get_settings
from src.utils.logging import setup_logging


def main():
    """Run the PicFrame API server."""
    # Initialize settings and logging
    settings = get_settings()
    setup_logging(
        level=settings.logging.level,
        ops_retention_days=settings.logging.retention_days,
        security_retention_days=settings.logging.security_retention_days,
    )

    uvicorn.run(
        "src.api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()

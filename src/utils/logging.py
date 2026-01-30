"""
PicFrame 4.0 - Logging Setup.

Dual logging strategy:
- picframe.log: Operations (sync, display, errors) - 7 day retention
- security.log: Auth events, API access - 90 day retention
"""

import logging
import os
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

# Log directory
LOG_DIR = Path.home() / ".picframe" / "logs"

# Log format
LOG_FORMAT = "%(asctime)s %(levelname)-5s [%(name)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    level: str = "INFO",
    ops_retention_days: int = 7,
    security_retention_days: int = 90,
):
    """
    Set up dual logging with separate files and retention.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        ops_retention_days: Days to keep operations logs
        security_retention_days: Days to keep security logs
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Set up root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    root_logger.addHandler(console)

    # Operations log (picframe.log)
    ops_handler = TimedRotatingFileHandler(
        LOG_DIR / "picframe.log",
        when="midnight",
        backupCount=ops_retention_days,
        encoding="utf-8",
    )
    ops_handler.setLevel(logging.DEBUG)
    ops_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    root_logger.addHandler(ops_handler)

    # Security log (security.log)
    security_logger = logging.getLogger("security")
    security_handler = TimedRotatingFileHandler(
        LOG_DIR / "security.log",
        when="midnight",
        backupCount=security_retention_days,
        encoding="utf-8",
    )
    security_handler.setLevel(logging.INFO)
    security_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    security_logger.addHandler(security_handler)
    security_logger.propagate = False  # Don't duplicate to ops log

    # Set restrictive permissions on log directory
    os.chmod(LOG_DIR, 0o700)

    logging.info("Logging initialized")


def get_security_logger() -> logging.Logger:
    """Get the security logger for auth events."""
    return logging.getLogger("security")


def log_auth_event(
    event_type: str,
    success: bool,
    details: dict | None = None,
    ip: str | None = None,
):
    """
    Log an authentication/security event.

    Args:
        event_type: Type of event (PAIR_ATTEMPT, PAIR_SUCCESS, API_REQUEST, etc.)
        success: Whether the event was successful
        details: Additional event details
        ip: Client IP address
    """
    logger = get_security_logger()
    status = "SUCCESS" if success else "FAILURE"

    parts = [f"{event_type}_{status}"]
    if ip:
        parts.append(f"ip={ip}")
    if details:
        for key, value in details.items():
            parts.append(f"{key}={value}")

    logger.info(" ".join(parts))


def cleanup_old_logs():
    """
    Clean up log files older than their retention period.

    This is called periodically to remove old rotated logs.
    """
    now = datetime.now()

    for log_file in LOG_DIR.glob("*.log.*"):
        try:
            # Get file modification time
            mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
            age = now - mtime

            # Determine retention based on file name
            if "security" in log_file.name:
                max_age = timedelta(days=90)
            else:
                max_age = timedelta(days=7)

            if age > max_age:
                log_file.unlink()
                logging.debug(f"Deleted old log: {log_file}")

        except Exception as e:
            logging.warning(f"Failed to clean up log {log_file}: {e}")

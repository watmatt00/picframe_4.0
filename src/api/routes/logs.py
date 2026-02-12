"""
PicFrame 4.0 API - Log Routes.

View frame logs remotely:
- GET /logs: Get recent log entries
"""

from pathlib import Path

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.api.dependencies import require_admin

router = APIRouter(prefix="/logs", tags=["logs"])

LOGS_DIR = Path.home() / ".picframe" / "logs"


class LogsResponse(BaseModel):
    """Response containing log entries."""
    entries: list[str]
    log_type: str
    count: int


@router.get("", response_model=LogsResponse)
async def get_logs(
    lines: int = Query(default=100, ge=1, le=500),
    log_type: str = Query(default="ops", pattern="^(ops|security)$"),
    admin=Depends(require_admin),
):
    """
    Get recent log entries from the frame.

    Args:
        lines: Number of lines to return (1-500)
        log_type: "ops" for operation logs, "security" for security logs
    """
    if log_type == "security":
        log_file = LOGS_DIR / "security.log"
    else:
        log_file = LOGS_DIR / "picframe.log"

    entries: list[str] = []
    if log_file.exists():
        try:
            with open(log_file, "r") as f:
                all_lines = f.readlines()
            # Return last N lines, newest first
            entries = [line.strip() for line in all_lines[-lines:] if line.strip()][::-1]
        except Exception:
            pass

    return LogsResponse(
        entries=entries,
        log_type=log_type,
        count=len(entries),
    )

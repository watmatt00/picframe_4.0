"""
PicFrame 4.0 API - Software Update Routes.

Check for, schedule, and apply frame software updates from the mobile app.
The LAN dashboard has equivalent unauthenticated routes under /api/updates/*.
"""

from fastapi import APIRouter, Depends

from src.api.dependencies import require_admin
from src.auth.jwt_handler import TokenClaims
from src.services.update_service import (
    SaveUpdateScheduleRequest,
    apply_update_and_restart,
    get_update_status,
    run_update_check,
    save_update_schedule,
)

router = APIRouter(prefix="/updates", tags=["updates"])


@router.get("/settings")
async def get_update_settings(
    admin: TokenClaims = Depends(require_admin),
) -> dict:
    """Get update schedule settings, last check result, and installed version."""
    return await get_update_status()


@router.post("/check")
async def check_for_updates(
    admin: TokenClaims = Depends(require_admin),
) -> dict:
    """Trigger an immediate update check."""
    return await run_update_check()


@router.post("/schedule")
async def save_schedule(
    request: SaveUpdateScheduleRequest,
    admin: TokenClaims = Depends(require_admin),
) -> dict:
    """Save update schedule settings."""
    return save_update_schedule(request)


@router.post("/apply")
async def apply_update(
    admin: TokenClaims = Depends(require_admin),
) -> dict:
    """Apply available updates (git pull) and restart the API."""
    return await apply_update_and_restart("app")

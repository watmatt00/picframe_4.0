"""
WanderWall API - System Routes.

- POST /system/reboot: Reboot the frame (admin only, PL-142)
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from src.api.dependencies import require_admin
from src.services import power_service

router = APIRouter(prefix="/system", tags=["system"])


class RebootResponse(BaseModel):
    """Answer sent before the frame reboots."""
    rebooting: bool
    message: str
    delay_seconds: int


@router.post("/reboot", response_model=RebootResponse, status_code=status.HTTP_202_ACCEPTED)
async def reboot_frame(http_request: Request, admin=Depends(require_admin)):
    """
    Reboot the frame a few seconds from now. It's back in about 1-2 minutes.

    503 if this frame hasn't had install_setup.sh re-run since reboot was added.
    """
    if not await power_service.reboot_available():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=power_service.NOT_SET_UP_MESSAGE)
    client_ip = http_request.client.host if http_request.client else None
    power_service.schedule_reboot(admin.device_name, ip=client_ip)
    return RebootResponse(
        rebooting=True,
        message="Rebooting. The frame will be back in about 1-2 minutes.",
        delay_seconds=power_service.REBOOT_DELAY_SECONDS,
    )

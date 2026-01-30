"""
PicFrame 4.0 API - Device Management Routes.

Manages paired devices:
- GET /devices: List all paired devices
- DELETE /devices/{id}: Revoke a device
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional

from src.api.dependencies import require_admin

router = APIRouter(prefix="/devices", tags=["devices"])


class PairedDevice(BaseModel):
    """A paired mobile device."""
    id: str
    name: str
    role: str  # "admin"
    paired_at: str
    last_seen: Optional[str]


@router.get("", response_model=list[PairedDevice])
async def list_devices(admin=Depends(require_admin)):
    """
    List all paired devices.

    Returns device info including role, pairing date, and last activity.
    """
    # TODO: Implement device listing from storage
    return []


@router.delete("/{device_id}")
async def revoke_device(device_id: str, admin=Depends(require_admin)):
    """
    Revoke a paired device.

    The device's JWT will be invalidated and they will need to re-pair.
    Cannot revoke the last admin device.
    """
    # TODO: Implement device revocation
    # - Check if this is the last admin
    # - Remove from storage
    # - Add to revocation list
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Device revocation not yet implemented",
    )

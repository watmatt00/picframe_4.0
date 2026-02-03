"""
PicFrame 4.0 API - Device Management Routes.

Manages paired devices:
- GET /devices: List all paired devices
- GET /devices/{id}: Get a specific device
- DELETE /devices/{id}: Revoke a device
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional

from src.api.dependencies import require_admin
from src.storage.devices import device_storage

router = APIRouter(prefix="/devices", tags=["devices"])


class PairedDeviceResponse(BaseModel):
    """A paired mobile device."""
    id: str
    name: str
    role: str  # "admin"
    paired_at: str
    last_seen: Optional[str]


class DeviceCountResponse(BaseModel):
    """Device count information."""
    total: int
    admins: int


@router.get("", response_model=list[PairedDeviceResponse])
async def list_devices(admin=Depends(require_admin)):
    """
    List all paired devices.

    Returns device info including role, pairing date, and last activity.
    """
    devices = device_storage.list_devices()
    return [
        PairedDeviceResponse(
            id=d.id,
            name=d.name,
            role=d.role,
            paired_at=d.paired_at.isoformat() if d.paired_at else "",
            last_seen=d.last_seen.isoformat() if d.last_seen else None,
        )
        for d in devices
    ]


@router.get("/count", response_model=DeviceCountResponse)
async def get_device_count(admin=Depends(require_admin)):
    """
    Get count of paired devices.
    """
    devices = device_storage.list_devices()
    admin_count = device_storage.count_admins()
    return DeviceCountResponse(total=len(devices), admins=admin_count)


@router.get("/{device_id}", response_model=PairedDeviceResponse)
async def get_device(device_id: str, admin=Depends(require_admin)):
    """
    Get a specific paired device.
    """
    device = device_storage.get_device(device_id)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device '{device_id}' not found",
        )

    return PairedDeviceResponse(
        id=device.id,
        name=device.name,
        role=device.role,
        paired_at=device.paired_at.isoformat() if device.paired_at else "",
        last_seen=device.last_seen.isoformat() if device.last_seen else None,
    )


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_device(device_id: str, admin=Depends(require_admin)):
    """
    Revoke a paired device.

    The device's JWT will be invalidated and they will need to re-pair.
    Cannot revoke the last admin device.
    """
    # Check if device exists
    device = device_storage.get_device(device_id)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device '{device_id}' not found",
        )

    # Check if this is the last admin
    if device.role == "admin" and device_storage.count_admins() <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot revoke the last admin device. Add another admin first.",
        )

    # Remove the device
    success = device_storage.remove_device(device_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to revoke device '{device_id}'",
        )

"""
PicFrame 4.0 API - Service Control Routes.

Controls systemd services:
- GET /services: List services and their status
- POST /services/{name}/restart: Restart a service
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.api.dependencies import require_admin

router = APIRouter(prefix="/services", tags=["services"])

# Whitelist of services that can be controlled
ALLOWED_SERVICES = {"picframe", "picframe-api"}


class ServiceInfo(BaseModel):
    """Service information."""
    name: str
    active: bool
    status: str
    can_restart: bool


@router.get("", response_model=list[ServiceInfo])
async def list_services(admin=Depends(require_admin)):
    """
    List controllable services and their current status.
    """
    # TODO: Query systemd for service status
    return [
        ServiceInfo(name="picframe", active=True, status="running", can_restart=True),
        ServiceInfo(name="picframe-api", active=True, status="running", can_restart=True),
    ]


@router.post("/{service_name}/restart")
async def restart_service(service_name: str, admin=Depends(require_admin)):
    """
    Restart a system service.

    Only whitelisted services can be restarted for security.
    """
    if service_name not in ALLOWED_SERVICES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Service '{service_name}' is not in the allowed list",
        )

    # TODO: Implement service restart via systemd_service
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Service restart not yet implemented",
    )

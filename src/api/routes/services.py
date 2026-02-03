"""
PicFrame 4.0 API - Service Control Routes.

Controls systemd services:
- GET /services: List services and their status
- POST /services/{name}/restart: Restart a service
- POST /services/{name}/start: Start a service
- POST /services/{name}/stop: Stop a service
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.api.dependencies import require_admin
from src.services.systemd_service import systemd_service, ALLOWED_SERVICES

router = APIRouter(prefix="/services", tags=["services"])


class ServiceInfo(BaseModel):
    """Service information."""
    name: str
    active: bool
    status: str
    enabled: bool
    can_restart: bool


class ServiceActionResponse(BaseModel):
    """Response after a service action."""
    service: str
    action: str
    success: bool
    message: str


@router.get("", response_model=list[ServiceInfo])
async def list_services(admin=Depends(require_admin)):
    """
    List controllable services and their current status.
    """
    statuses = await systemd_service.list_services()
    return [
        ServiceInfo(
            name=s.name,
            active=s.active,
            status=s.status,
            enabled=s.enabled,
            can_restart=True,
        )
        for s in statuses
    ]


@router.post("/{service_name}/restart", response_model=ServiceActionResponse)
async def restart_service(service_name: str, admin=Depends(require_admin)):
    """
    Restart a system service.

    Only whitelisted services can be restarted for security.
    """
    if service_name not in ALLOWED_SERVICES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Service '{service_name}' is not in the allowed list. Allowed: {', '.join(ALLOWED_SERVICES)}",
        )

    success = await systemd_service.restart(service_name)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to restart service '{service_name}'",
        )

    return ServiceActionResponse(
        service=service_name,
        action="restart",
        success=True,
        message=f"Service '{service_name}' restarted successfully",
    )


@router.post("/{service_name}/start", response_model=ServiceActionResponse)
async def start_service(service_name: str, admin=Depends(require_admin)):
    """
    Start a system service.
    """
    if service_name not in ALLOWED_SERVICES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Service '{service_name}' is not in the allowed list",
        )

    success = await systemd_service.start(service_name)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start service '{service_name}'",
        )

    return ServiceActionResponse(
        service=service_name,
        action="start",
        success=True,
        message=f"Service '{service_name}' started successfully",
    )


@router.post("/{service_name}/stop", response_model=ServiceActionResponse)
async def stop_service(service_name: str, admin=Depends(require_admin)):
    """
    Stop a system service.
    """
    if service_name not in ALLOWED_SERVICES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Service '{service_name}' is not in the allowed list",
        )

    success = await systemd_service.stop(service_name)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop service '{service_name}'",
        )

    return ServiceActionResponse(
        service=service_name,
        action="stop",
        success=True,
        message=f"Service '{service_name}' stopped successfully",
    )

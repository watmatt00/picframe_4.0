"""
PicFrame 4.0 API - Token Refresh Routes.

Lets a paired device swap its JWT for a fresh one before it expires.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from src.api.dependencies import get_current_device
from src.auth.jwt_handler import TokenClaims, create_token, verify_token
from src.config.settings import get_settings
from src.storage.devices import device_storage
from src.utils.logging import log_auth_event

router = APIRouter(prefix="/auth", tags=["auth"])


class RefreshResponse(BaseModel):
    """Response from POST /auth/refresh."""
    token: str
    expires_at: datetime


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_token(
    http_request: Request,
    claims: TokenClaims = Depends(get_current_device),
) -> RefreshResponse:
    """
    Issue a new token for the calling device.

    The previous token keeps working for a short grace period, then is rejected.
    Role comes from device storage, not the old token.
    """
    client_ip = http_request.client.host if http_request.client else None
    device = device_storage.get_device(claims.device_id)
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Device has been revoked",
        )

    # JWT iat has 1-second resolution; record the floor before minting so the
    # new token's iat is never earlier than it.
    issued_at = datetime.now(timezone.utc).replace(microsecond=0)
    token = create_token(
        device_id=device.id,
        device_name=device.name,
        role=device.role,
        frame_id=get_settings().frame.id,
    )
    device_storage.set_token_not_before(device.id, issued_at)

    new_claims = verify_token(token)
    log_auth_event(
        "TOKEN_REFRESH",
        success=True,
        details={"device_id": device.id, "device_name": device.name},
        ip=client_ip,
    )
    return RefreshResponse(token=token, expires_at=new_claims.exp)

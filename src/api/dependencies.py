"""
PicFrame 4.0 API - FastAPI Dependencies.

Authentication and authorization dependencies for route protection.
"""

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from src.auth.jwt_handler import TokenClaims, verify_token
from src.storage.devices import device_storage

security = HTTPBearer(auto_error=False)

# How long a replaced token keeps working after a refresh, so requests already
# in flight (and a retry after a lost refresh response) don't fail.
TOKEN_REFRESH_GRACE = timedelta(minutes=2)


def is_superseded(claims: TokenClaims, token_not_before: datetime | None) -> bool:
    """Check if a token was replaced by a newer one and its grace period is over."""
    if token_not_before is None or claims.iat >= token_not_before:
        return False
    return datetime.now(timezone.utc) > token_not_before + TOKEN_REFRESH_GRACE


async def get_current_device(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> TokenClaims:
    """
    Validate JWT token and return current device info.

    Raises:
        HTTPException: If token is missing, invalid, or expired.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    claims = verify_token(credentials.credentials)
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    device = device_storage.get_device(claims.device_id)
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Device has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if is_superseded(claims, device.token_not_before):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been replaced",
            headers={"WWW-Authenticate": "Bearer"},
        )

    device_storage.update_last_seen(claims.device_id)
    return claims


async def require_admin(
    device: TokenClaims = Depends(get_current_device),
) -> TokenClaims:
    """
    Require admin role for protected endpoints.

    Raises:
        HTTPException: If device is not an admin.
    """
    if device.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return device


async def require_contributor(
    device: TokenClaims = Depends(get_current_device),
) -> TokenClaims:
    """
    Require admin or contributor role for contributor endpoints.

    Raises:
        HTTPException: If device has an unrecognized role.
    """
    if device.role not in ("admin", "contributor"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Contributor or admin access required",
        )
    return device

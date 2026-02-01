"""
PicFrame 4.0 API - FastAPI Dependencies.

Authentication and authorization dependencies for route protection.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from src.auth.jwt_handler import TokenClaims, verify_token

security = HTTPBearer(auto_error=False)


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

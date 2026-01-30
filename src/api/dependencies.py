"""
PicFrame 4.0 API - FastAPI Dependencies.

Authentication and authorization dependencies for route protection.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()


async def get_current_device(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Validate JWT token and return current device info.

    Raises:
        HTTPException: If token is invalid or expired.
    """
    # TODO: Implement JWT validation
    # from src.auth.jwt_handler import verify_token
    # return verify_token(credentials.credentials)
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Authentication not yet implemented",
    )


async def require_admin(device=Depends(get_current_device)):
    """
    Require admin role for protected endpoints.

    Raises:
        HTTPException: If device is not an admin.
    """
    # TODO: Check device role
    # if device.role != "admin":
    #     raise HTTPException(status_code=403, detail="Admin access required")
    # return device
    pass

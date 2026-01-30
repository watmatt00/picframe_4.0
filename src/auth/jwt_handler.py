"""
PicFrame 4.0 - JWT Token Handler.

Handles JWT token creation and validation using HS256.
Secret is stored per-Pi at ~/.picframe/jwt_secret with 600 permissions.
"""

import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import jwt
from pydantic import BaseModel

# Default token expiry: 1 year
DEFAULT_EXPIRY_DAYS = 365

# Secret file location
SECRET_PATH = Path.home() / ".picframe" / "jwt_secret"


class TokenClaims(BaseModel):
    """JWT token claims."""
    device_id: str
    device_name: str
    role: str  # "admin"
    frame_id: str
    iat: datetime
    exp: datetime


def get_or_create_secret() -> str:
    """
    Get the JWT secret, creating it if it doesn't exist.

    The secret is a 256-bit (32 byte) random value, stored with 600 permissions.
    """
    if SECRET_PATH.exists():
        return SECRET_PATH.read_text().strip()

    # Create parent directory if needed
    SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Generate 256-bit secret
    secret = secrets.token_hex(32)

    # Write with restrictive permissions
    SECRET_PATH.write_text(secret)
    os.chmod(SECRET_PATH, 0o600)

    return secret


def create_token(
    device_id: str,
    device_name: str,
    role: str,
    frame_id: str,
    expiry_days: int = DEFAULT_EXPIRY_DAYS,
) -> str:
    """
    Create a new JWT token for a device.

    Args:
        device_id: Unique device identifier
        device_name: Human-readable device name
        role: Device role ("admin")
        frame_id: Frame this token is for
        expiry_days: Token validity in days

    Returns:
        Encoded JWT token string
    """
    secret = get_or_create_secret()
    now = datetime.now(timezone.utc)

    payload = {
        "device_id": device_id,
        "device_name": device_name,
        "role": role,
        "frame_id": frame_id,
        "iat": now,
        "exp": now + timedelta(days=expiry_days),
    }

    return jwt.encode(payload, secret, algorithm="HS256")


def verify_token(token: str) -> Optional[TokenClaims]:
    """
    Verify and decode a JWT token.

    Args:
        token: The JWT token string

    Returns:
        TokenClaims if valid, None if invalid or expired

    Raises:
        jwt.InvalidTokenError: If token is malformed
        jwt.ExpiredSignatureError: If token has expired
    """
    secret = get_or_create_secret()

    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return TokenClaims(**payload)
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def revoke_token(device_id: str) -> bool:
    """
    Revoke all tokens for a device.

    Note: With HS256, we can't truly revoke tokens. Instead, we maintain
    a revocation list that is checked during verification.

    Args:
        device_id: Device to revoke

    Returns:
        True if device was found and revoked
    """
    # TODO: Implement revocation list
    # Store revoked device_ids in ~/.picframe/revoked_devices.json
    # Check this list in verify_token()
    return False

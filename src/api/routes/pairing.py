"""
PicFrame 4.0 API - Pairing Routes.

Handles device pairing flow:
- POST /pair: Exchange pairing code for JWT
- POST /pairing/generate: Generate new pairing QR code (admin only)
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from src.api.dependencies import require_admin
from src.auth.jwt_handler import create_token
from src.auth.models import Device
from src.auth.pairing import generate_pairing_code as gen_code, verify_pairing_code
from src.config.settings import get_settings
from src.storage.devices import device_storage
from src.utils.logging import log_auth_event
from src.utils.qr_generator import generate_pairing_qr

router = APIRouter(tags=["pairing"])


class PairRequest(BaseModel):
    """Request body for pairing exchange."""
    code: str
    device_name: str


class PairResponse(BaseModel):
    """Response from successful pairing."""
    token: str
    frame_id: str
    frame_name: str
    role: str = "admin"
    api_port: int = 8000


class PairingGenerateResponse(BaseModel):
    """Response with QR code data."""
    qr_code_base64: str
    code: str
    expires_at: str


@router.post("/pair", response_model=PairResponse)
async def pair_device(request: PairRequest, http_request: Request):
    """
    Exchange a pairing code for a JWT token.

    The pairing code is displayed on the Pi (via dashboard or CLI).
    Mobile app scans QR code containing URL + code, then calls this endpoint.
    """
    client_ip = http_request.client.host if http_request.client else None

    # Log pairing attempt
    log_auth_event(
        "PAIR_ATTEMPT",
        success=True,
        details={"code": request.code[:3] + "***", "device_name": request.device_name},
        ip=client_ip,
    )

    # Validate the pairing code
    if not verify_pairing_code(request.code):
        log_auth_event(
            "PAIR",
            success=False,
            details={"reason": "invalid_or_expired_code"},
            ip=client_ip,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired pairing code",
        )

    # Get frame config
    settings = get_settings()

    # Generate device ID and create JWT
    device_id = str(uuid.uuid4())
    token = create_token(
        device_id=device_id,
        device_name=request.device_name,
        role="admin",
        frame_id=settings.frame.id,
    )

    # Store the new device
    device = Device(
        id=device_id,
        name=request.device_name,
        role="admin",
        paired_at=datetime.now(timezone.utc),
    )
    device_storage.add_device(device)

    # Log successful pairing
    log_auth_event(
        "PAIR",
        success=True,
        details={"device_id": device_id, "device_name": request.device_name},
        ip=client_ip,
    )

    return PairResponse(
        token=token,
        frame_id=settings.frame.id,
        frame_name=settings.frame.name,
    )


@router.post("/pairing/generate", response_model=PairingGenerateResponse)
async def generate_pairing_code(http_request: Request, admin=Depends(require_admin)):
    """
    Generate a new pairing code and QR code.

    Admin-only endpoint. The QR code contains the Funnel URL and pairing code.
    Code expires after 5 minutes or 3 failed attempts.
    Rate limit: 3 codes per hour.
    """
    client_ip = http_request.client.host if http_request.client else None

    # Get frame config
    settings = get_settings()

    if not settings.frame.funnel_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Funnel URL not configured. Set frame.funnel_url in config.",
        )

    # Generate pairing code
    pairing_code = gen_code()

    if pairing_code is None:
        log_auth_event(
            "PAIR_CODE_GENERATE",
            success=False,
            details={"reason": "rate_limit_exceeded", "admin": admin.device_name},
            ip=client_ip,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Maximum 3 codes per hour.",
        )

    # Generate QR code
    qr_base64 = generate_pairing_qr(
        url=settings.frame.funnel_url,
        code=pairing_code.code,
        frame_name=settings.frame.name,
    )

    # Log code generation
    log_auth_event(
        "PAIR_CODE_GENERATE",
        success=True,
        details={"admin": admin.device_name, "expires": pairing_code.expires_at.isoformat()},
        ip=client_ip,
    )

    return PairingGenerateResponse(
        qr_code_base64=qr_base64,
        code=pairing_code.code,
        expires_at=pairing_code.expires_at.isoformat(),
    )

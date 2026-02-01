"""
PicFrame 4.0 API - Pairing Routes.

Handles device pairing flow:
- POST /pair: Exchange pairing code for JWT
- POST /pairing/generate: Generate new pairing QR code (admin only)
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.api.dependencies import require_admin
from src.auth.jwt_handler import create_token
from src.auth.models import Device
from src.auth.pairing import generate_pairing_code as gen_code, verify_pairing_code
from src.storage.devices import device_storage
from src.utils.qr_generator import generate_pairing_qr

router = APIRouter(tags=["pairing"])

# Frame configuration - TODO: Move to config file
FRAME_ID = "tkframe"
FRAME_NAME = "Test Frame"
FUNNEL_URL = "https://tkframe.tail7de60a.ts.net"


class PairRequest(BaseModel):
    """Request body for pairing exchange."""
    code: str
    device_name: str


class PairResponse(BaseModel):
    """Response from successful pairing."""
    token: str
    frame_id: str
    frame_name: str


class PairingGenerateResponse(BaseModel):
    """Response with QR code data."""
    qr_code_base64: str
    code: str
    expires_at: str


@router.post("/pair", response_model=PairResponse)
async def pair_device(request: PairRequest):
    """
    Exchange a pairing code for a JWT token.

    The pairing code is displayed on the Pi (via dashboard or CLI).
    Mobile app scans QR code containing URL + code, then calls this endpoint.
    """
    # Validate the pairing code
    if not verify_pairing_code(request.code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired pairing code",
        )

    # Generate device ID and create JWT
    device_id = str(uuid.uuid4())
    token = create_token(
        device_id=device_id,
        device_name=request.device_name,
        role="admin",
        frame_id=FRAME_ID,
    )

    # Store the new device
    device = Device(
        id=device_id,
        name=request.device_name,
        role="admin",
        paired_at=datetime.now(timezone.utc),
    )
    device_storage.add_device(device)

    return PairResponse(
        token=token,
        frame_id=FRAME_ID,
        frame_name=FRAME_NAME,
    )


@router.post("/pairing/generate", response_model=PairingGenerateResponse)
async def generate_pairing_code(admin=Depends(require_admin)):
    """
    Generate a new pairing code and QR code.

    Admin-only endpoint. The QR code contains the Funnel URL and pairing code.
    Code expires after 5 minutes or 3 failed attempts.
    Rate limit: 3 codes per hour.
    """
    # Generate pairing code
    pairing_code = gen_code()

    if pairing_code is None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Maximum 3 codes per hour.",
        )

    # Generate QR code
    qr_base64 = generate_pairing_qr(
        url=FUNNEL_URL,
        code=pairing_code.code,
        frame_name=FRAME_NAME,
    )

    return PairingGenerateResponse(
        qr_code_base64=qr_base64,
        code=pairing_code.code,
        expires_at=pairing_code.expires_at.isoformat(),
    )

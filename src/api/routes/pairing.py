"""
PicFrame 4.0 API - Pairing Routes.

Handles device pairing flow:
- POST /pair: Exchange pairing code for JWT
- POST /pairing/generate: Generate new pairing QR code (admin only)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.api.dependencies import require_admin

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
    # TODO: Implement pairing code validation and JWT issuance
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Pairing not yet implemented",
    )


@router.post("/pairing/generate", response_model=PairingGenerateResponse)
async def generate_pairing_code(admin=Depends(require_admin)):
    """
    Generate a new pairing code and QR code.

    Admin-only endpoint. The QR code contains the Funnel URL and pairing code.
    Code expires after 5 minutes or 3 failed attempts.
    """
    # TODO: Implement pairing code generation
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Pairing generation not yet implemented",
    )

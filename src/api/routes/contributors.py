"""
PicFrame 4.0 API - Contributor Management Routes.

Manages contributor access via invite codes:
- GET /contributors: List all invite records
- POST /contributors/invite: Generate a new contributor invite (code + QR)
- DELETE /contributors/{invite_id}: Revoke an unclaimed invite
"""

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.api.dependencies import require_admin
from src.config.settings import get_settings
from src.storage.invites import invite_storage
from src.utils.logging import log_auth_event
from src.utils.qr_generator import generate_pairing_qr

router = APIRouter(prefix="/contributors", tags=["contributors"])

# Validate invite_id is a UUID to prevent injection
_UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE,
)


class InviteListItem(BaseModel):
    """Invite summary for list view (no QR)."""
    id: str
    code: str
    expires_at: str
    claimed: bool
    claimed_at: Optional[str] = None
    claimed_by: Optional[str] = None


class InviteResponse(BaseModel):
    """Full invite response with QR code."""
    id: str
    code: str
    qr_code_base64: str
    expires_at: str
    funnel_url: str
    claimed: bool


@router.get("", response_model=list[InviteListItem])
async def list_contributors(admin=Depends(require_admin)):
    """
    List all contributor invites (claimed and unclaimed).
    """
    invites = invite_storage.list_invites()
    return [
        InviteListItem(
            id=i.id,
            code=i.code,
            expires_at=i.expires_at.isoformat(),
            claimed=i.claimed,
            claimed_at=i.claimed_at.isoformat() if i.claimed_at else None,
            claimed_by=i.claimed_by,
        )
        for i in invites
    ]


@router.post("/invite", response_model=InviteResponse)
async def create_invite(admin=Depends(require_admin)):
    """
    Generate a contributor invite code and QR.

    The invite code is single-use and expires after 48 hours.
    The QR encodes the same JSON payload as admin pairing QR
    so the contributor uses the standard pairing flow to claim it.

    Rate limit: 3 pending invites per hour.
    """
    settings = get_settings()

    if not settings.frame.funnel_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Funnel URL not configured. Set frame.funnel_url in config.",
        )

    invite = invite_storage.create_invite()
    if invite is None:
        log_auth_event(
            "INVITE_CREATE",
            success=False,
            details={"reason": "rate_limit", "admin": admin.device_name},
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Maximum 3 pending invites per hour.",
        )

    qr_base64 = generate_pairing_qr(
        url=settings.frame.funnel_url,
        code=invite.code,
        frame_name=settings.frame.name,
    )

    log_auth_event(
        "INVITE_CREATE",
        success=True,
        details={"admin": admin.device_name, "invite_id": invite.id},
    )

    return InviteResponse(
        id=invite.id,
        code=invite.code,
        qr_code_base64=qr_base64,
        expires_at=invite.expires_at.isoformat(),
        funnel_url=settings.frame.funnel_url,
        claimed=False,
    )


@router.delete("/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invite(invite_id: str, admin=Depends(require_admin)):
    """
    Revoke an unclaimed contributor invite.

    Cannot revoke an invite that has already been claimed.
    """
    if not _UUID_RE.match(invite_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid invite ID format",
        )

    if not invite_storage.revoke_invite(invite_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invite not found or already claimed",
        )

    log_auth_event(
        "INVITE_REVOKE",
        success=True,
        details={"admin": admin.device_name, "invite_id": invite_id},
    )

"""
PicFrame 4.0 API - Contributor Management Routes.

Manages contributor access (Koofr upload only):
- GET /contributors: List contributor invites
- POST /contributors/invite: Generate a new contributor invite
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional

from src.api.dependencies import require_admin

router = APIRouter(prefix="/contributors", tags=["contributors"])


class ContributorInvite(BaseModel):
    """A contributor invite."""
    id: str
    name: str
    koofr_folder: str
    created_at: str
    accepted: bool


class CreateInviteRequest(BaseModel):
    """Request to create a contributor invite."""
    name: str
    koofr_folder: Optional[str] = None  # Auto-generated if not provided


class CreateInviteResponse(BaseModel):
    """Response with invite details."""
    invite_id: str
    koofr_share_link: str
    instructions: str


@router.get("", response_model=list[ContributorInvite])
async def list_contributors(admin=Depends(require_admin)):
    """
    List all contributor invites.
    """
    # TODO: Implement contributor listing
    return []


@router.post("/invite", response_model=CreateInviteResponse)
async def create_invite(request: CreateInviteRequest, admin=Depends(require_admin)):
    """
    Generate a contributor invite.

    Creates a Koofr shared folder and returns the share link.
    Contributors can only upload photos - no Pi access.
    """
    # TODO: Implement invite generation
    # - Create Koofr folder via API
    # - Generate share link
    # - Store invite record
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Contributor invites not yet implemented",
    )

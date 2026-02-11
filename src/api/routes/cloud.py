"""
PicFrame 4.0 API - Cloud Credentials Routes.

Provides cloud storage credentials to mobile clients:
- GET /cloud/credentials: Returns Koofr credentials from rclone config
"""

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.dependencies import require_admin

router = APIRouter(tags=["cloud"])


class CloudCredentials(BaseModel):
    """Cloud storage credentials for mobile upload."""
    provider: str
    email: str
    password: str


class CloudCredentialsResponse(BaseModel):
    """Response from GET /cloud/credentials."""
    credentials: Optional[CloudCredentials] = None
    message: str


async def _get_rclone_koofr_credentials() -> Optional[CloudCredentials]:
    """Extract Koofr credentials from rclone config.

    Reads rclone config dump to find the first Koofr remote,
    then reveals the obscured password.
    """
    try:
        # Get rclone config as JSON
        proc = await asyncio.create_subprocess_exec(
            "rclone", "config", "dump",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)

        import json
        config = json.loads(stdout.decode())

        # Find first Koofr remote
        for remote_name, remote_config in config.items():
            if remote_config.get("type") == "koofr":
                email = remote_config.get("user", "")
                obscured_password = remote_config.get("password", "")

                if not email or not obscured_password:
                    continue

                # Reveal the obscured password
                reveal_proc = await asyncio.create_subprocess_exec(
                    "rclone", "reveal", obscured_password,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                reveal_stdout, _ = await asyncio.wait_for(
                    reveal_proc.communicate(), timeout=10
                )
                password = reveal_stdout.decode().strip()

                if password:
                    return CloudCredentials(
                        provider="koofr",
                        email=email,
                        password=password,
                    )

        return None
    except (asyncio.TimeoutError, Exception):
        return None


@router.get("/cloud/credentials", response_model=CloudCredentialsResponse)
async def get_cloud_credentials(admin=Depends(require_admin)):
    """Get cloud storage credentials for mobile upload.

    Returns Koofr credentials extracted from the frame's rclone config.
    Admin only — credentials are sensitive.
    """
    credentials = await _get_rclone_koofr_credentials()

    if credentials:
        return CloudCredentialsResponse(
            credentials=credentials,
            message="Credentials retrieved successfully",
        )

    return CloudCredentialsResponse(
        credentials=None,
        message="No Koofr remote configured on this frame",
    )

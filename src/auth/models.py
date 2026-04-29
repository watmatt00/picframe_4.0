"""
PicFrame 4.0 - Authentication Models.

Pydantic models for devices, tokens, and pairing.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class Device(BaseModel):
    """A paired mobile device."""
    model_config = ConfigDict()

    id: str = Field(..., description="Unique device identifier (UUID)")
    name: str = Field(..., description="User-provided device name")
    role: str = Field(default="admin", description="Device role")
    paired_at: datetime = Field(..., description="When device was paired")
    last_seen: Optional[datetime] = Field(None, description="Last API activity")

    @field_serializer("paired_at", "last_seen")
    def serialize_dt(self, v: Optional[datetime]) -> Optional[str]:
        return v.isoformat() if v is not None else None


class PairingRequest(BaseModel):
    """Request to pair a new device."""
    code: str = Field(..., description="6-char pairing code from QR")
    device_name: str = Field(..., description="Name for this device")


class PairingResponse(BaseModel):
    """Response after successful pairing."""
    token: str = Field(..., description="JWT token for API access")
    frame_id: str = Field(..., description="Unique frame identifier")
    frame_name: str = Field(..., description="Human-readable frame name")


class QRCodeData(BaseModel):
    """Data encoded in pairing QR code."""
    url: str = Field(..., description="Tailscale Funnel URL")
    code: str = Field(..., description="Pairing code")
    name: str = Field(..., description="Frame name")

    def to_json_string(self) -> str:
        """Serialize for QR code encoding."""
        return self.model_dump_json()

    @classmethod
    def from_json_string(cls, data: str) -> "QRCodeData":
        """Deserialize from QR code scan."""
        return cls.model_validate_json(data)

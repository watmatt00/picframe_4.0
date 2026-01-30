"""
PicFrame 4.0 - Configuration Schemas.

Pydantic models for validating configuration data.
"""

from typing import Optional

from pydantic import BaseModel, Field, field_validator


class FrameConfigSchema(BaseModel):
    """Schema for frame configuration."""
    id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(..., min_length=1, max_length=128)


class SourceConfigSchema(BaseModel):
    """Schema for a photo source configuration."""
    id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(..., min_length=1, max_length=128)
    local_path: str = Field(..., min_length=1)
    rclone_remote: Optional[str] = Field(None, min_length=1)
    enabled: bool = Field(default=True)

    @field_validator("local_path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        """Ensure path doesn't contain traversal attempts."""
        if ".." in v:
            raise ValueError("Path cannot contain '..'")
        return v


class SyncConfigSchema(BaseModel):
    """Schema for sync configuration."""
    interval: int = Field(..., ge=60, le=86400)  # 1 min to 24 hours
    rclone_flags: list[str] = Field(default_factory=list)

    @field_validator("rclone_flags")
    @classmethod
    def validate_flags(cls, v: list[str]) -> list[str]:
        """Ensure no dangerous flags are passed."""
        dangerous = {"--delete-excluded", "-P", "--progress"}
        for flag in v:
            if flag.startswith("--config"):
                raise ValueError("Cannot override rclone config")
        return v


class DisplayConfigSchema(BaseModel):
    """Schema for display configuration."""
    current_source: str = Field(..., min_length=1, max_length=64)
    rotation_interval: int = Field(..., ge=5, le=3600)  # 5 sec to 1 hour


class FullConfigSchema(BaseModel):
    """Schema for complete configuration file."""
    frame: FrameConfigSchema
    display: DisplayConfigSchema
    sync: SyncConfigSchema

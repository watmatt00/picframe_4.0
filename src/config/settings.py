"""
PicFrame 4.0 - Application Settings.

Pydantic settings with environment variable and YAML file support.
"""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml

# Default config locations
CONFIG_DIR = Path.home() / ".picframe"
CONFIG_FILE = CONFIG_DIR / "config.yaml"


class FrameConfig(BaseModel):
    """Frame identification settings."""
    id: str = Field(default="picframe", description="Unique frame identifier")
    name: str = Field(default="PicFrame", description="Human-readable frame name")


class DisplayConfig(BaseModel):
    """Display settings."""
    current_source: str = Field(default="default", description="Active photo source ID")
    rotation_interval: int = Field(default=30, description="Seconds between images")


class SyncConfig(BaseModel):
    """Sync settings."""
    interval: int = Field(default=900, description="Sync interval in seconds")
    rclone_flags: list[str] = Field(default_factory=list, description="Extra rclone flags")


class TailscaleConfig(BaseModel):
    """Tailscale settings."""
    funnel_port: int = Field(default=443, description="Funnel HTTPS port")


class LoggingConfig(BaseModel):
    """Logging settings."""
    level: str = Field(default="INFO", description="Log level")
    retention_days: int = Field(default=7, description="Days to keep operation logs")
    security_retention_days: int = Field(default=90, description="Days to keep security logs")


class Settings(BaseSettings):
    """
    Application settings.

    Loaded from:
    1. Environment variables (PICFRAME_*)
    2. ~/.picframe/config.yaml
    3. Defaults
    """

    model_config = SettingsConfigDict(
        env_prefix="PICFRAME_",
        env_nested_delimiter="__",
    )

    frame: FrameConfig = Field(default_factory=FrameConfig)
    display: DisplayConfig = Field(default_factory=DisplayConfig)
    sync: SyncConfig = Field(default_factory=SyncConfig)
    tailscale: TailscaleConfig = Field(default_factory=TailscaleConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @classmethod
    def from_yaml(cls, path: Path = CONFIG_FILE) -> "Settings":
        """
        Load settings from YAML file.

        Args:
            path: Path to YAML config file

        Returns:
            Settings instance
        """
        if not path.exists():
            return cls()

        with open(path) as f:
            data = yaml.safe_load(f) or {}

        return cls(**data)

    def to_yaml(self, path: Path = CONFIG_FILE):
        """
        Save settings to YAML file.

        Args:
            path: Path to save config
        """
        path.parent.mkdir(parents=True, exist_ok=True)

        data = self.model_dump()

        with open(path, "w") as f:
            yaml.safe_dump(data, f, default_flow_style=False)


@lru_cache
def get_settings() -> Settings:
    """
    Get application settings (cached).

    Returns:
        Settings instance
    """
    return Settings.from_yaml()

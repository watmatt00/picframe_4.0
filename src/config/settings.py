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
    funnel_url: str = Field(default="", description="Tailscale Funnel URL")


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


class Source(BaseModel):
    """Photo source configuration."""
    id: str = Field(description="Unique source identifier")
    name: str = Field(description="Human-readable source name")
    local_path: str = Field(description="Local directory path for synced photos")
    rclone_remote: str = Field(default="", description="rclone remote spec (e.g., 'koofr:KFR_kframe')")
    enabled: bool = Field(default=True, description="Whether this source is active")

    def get_local_path(self) -> Path:
        """Get the local path as a Path object."""
        return Path(self.local_path).expanduser()


class SourcesConfig(BaseModel):
    """Photo sources configuration."""
    sources: list[Source] = Field(
        default_factory=lambda: [
            Source(
                id="local",
                name="Local Photos",
                local_path="~/Pictures",
                rclone_remote="",
                enabled=True,
            )
        ],
        description="List of photo sources"
    )

    def get_source(self, source_id: str) -> Optional[Source]:
        """Get a source by ID."""
        for source in self.sources:
            if source.id == source_id:
                return source
        return None

    def get_enabled_sources(self) -> list[Source]:
        """Get all enabled sources."""
        return [s for s in self.sources if s.enabled]

    def get_syncable_sources(self) -> list[Source]:
        """Get sources that have rclone remotes configured."""
        return [s for s in self.sources if s.enabled and s.rclone_remote]


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
    sources: SourcesConfig = Field(default_factory=SourcesConfig)

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

    Auto-creates default config file if it doesn't exist.

    Returns:
        Settings instance
    """
    if not CONFIG_FILE.exists():
        # Create default config
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        default_settings = Settings()
        default_settings.to_yaml(CONFIG_FILE)

    return Settings.from_yaml()


def reload_settings() -> Settings:
    """
    Reload settings from disk, clearing the cache.

    Returns:
        Fresh Settings instance
    """
    get_settings.cache_clear()
    return get_settings()

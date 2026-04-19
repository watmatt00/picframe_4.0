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


class UpdatesConfig(BaseModel):
    """Update check settings."""
    auto_check: bool = Field(default=True, description="Enable automatic update checks")
    auto_apply: bool = Field(default=False, description="Automatically apply updates during scheduled run")
    frequency: str = Field(default="monthly", description="Check frequency: 'daily', 'weekly', or 'monthly'")
    day: int = Field(default=1, description="Day of month (1-28) or day of week (0-6, Mon=0); ignored for daily")
    check_time: str = Field(default="02:00", description="Time to run check (HH:MM, 24-hour)")
    last_checked: Optional[str] = Field(default=None, description="ISO datetime of last check")
    last_result: Optional[str] = Field(default=None, description="Result: 'up_to_date' | 'update_available' | 'error'")
    available_commit: Optional[str] = Field(default=None, description="Short hash if update available")


class SleepConfig(BaseModel):
    """Sleep mode schedule settings."""
    enabled: bool = Field(default=False, description="Enable automatic sleep/wake schedule")
    sleep_time: str = Field(default="22:00", description="Time to sleep (HH:MM, 24-hour)")
    wake_time: str = Field(default="07:00", description="Time to wake (HH:MM, 24-hour)")


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
    updates: UpdatesConfig = Field(default_factory=UpdatesConfig)
    sleep: SleepConfig = Field(default_factory=SleepConfig)

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

        # sources moved to sources.yaml — silently drop if present in old configs
        data.pop("sources", None)

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

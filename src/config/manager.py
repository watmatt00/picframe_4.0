"""
PicFrame 4.0 - Configuration Manager.

Handles configuration file read/write with file locking.
"""

import logging
from pathlib import Path
from typing import Any, Optional

from filelock import FileLock
import yaml

logger = logging.getLogger(__name__)

# Lock timeout in seconds
LOCK_TIMEOUT = 10


class ConfigManager:
    """
    Manages configuration file access with locking.

    Ensures atomic writes and prevents race conditions.
    """

    def __init__(self, config_path: Path):
        self._path = config_path
        self._lock_path = config_path.with_suffix(".lock")
        self._lock = FileLock(self._lock_path, timeout=LOCK_TIMEOUT)

    def read(self) -> dict[str, Any]:
        """
        Read configuration file.

        Returns:
            Configuration dictionary
        """
        with self._lock:
            if not self._path.exists():
                return {}

            try:
                with open(self._path) as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.error(f"Failed to read config: {e}")
                return {}

    def write(self, config: dict[str, Any]):
        """
        Write configuration file atomically.

        Uses write-to-temp-then-rename for atomic writes.

        Args:
            config: Configuration dictionary to write
        """
        with self._lock:
            # Ensure directory exists
            self._path.parent.mkdir(parents=True, exist_ok=True)

            # Write to temp file first
            temp_path = self._path.with_suffix(".tmp")

            try:
                with open(temp_path, "w") as f:
                    yaml.safe_dump(config, f, default_flow_style=False)

                # Atomic rename
                temp_path.rename(self._path)

                logger.info(f"Configuration saved to {self._path}")

            except Exception as e:
                logger.error(f"Failed to write config: {e}")
                # Clean up temp file
                if temp_path.exists():
                    temp_path.unlink()
                raise

    def update(self, updates: dict[str, Any]) -> dict[str, Any]:
        """
        Update specific configuration values.

        Args:
            updates: Dictionary of values to update (can be nested)

        Returns:
            Updated configuration
        """
        with self._lock:
            config = self.read()
            self._deep_update(config, updates)
            self.write(config)
            return config

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value by key.

        Supports dot notation for nested keys (e.g., "frame.name").

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        config = self.read()
        keys = key.split(".")

        value = config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def set(self, key: str, value: Any):
        """
        Set a configuration value by key.

        Supports dot notation for nested keys.

        Args:
            key: Configuration key
            value: Value to set
        """
        keys = key.split(".")
        updates = {}

        # Build nested dict for update
        current = updates
        for k in keys[:-1]:
            current[k] = {}
            current = current[k]
        current[keys[-1]] = value

        self.update(updates)

    @staticmethod
    def _deep_update(base: dict, updates: dict):
        """Recursively update a dictionary."""
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                ConfigManager._deep_update(base[key], value)
            else:
                base[key] = value


# Default config path
CONFIG_PATH = Path.home() / ".picframe" / "config.yaml"

# Global config manager instance
config_manager = ConfigManager(CONFIG_PATH)

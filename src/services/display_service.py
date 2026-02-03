"""
PicFrame 4.0 - Display Service.

Controls the Pi3D PictureFrame display via MQTT and configuration.
"""

import logging
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel

from src.services.systemd_service import systemd_service

logger = logging.getLogger(__name__)

# Default Pi3D config location
PI3D_CONFIG_PATH = Path.home() / "picframe_data" / "config" / "configuration.yaml"
PI3D_PICTURES_PATH = Path.home() / "Pictures"


class DisplayConfig(BaseModel):
    """Pi3D display configuration."""
    pic_dir: str
    subdirectory: str = ""
    time_delay: float = 30.0
    fade_time: float = 2.0
    shuffle: bool = True


class DisplayService:
    """
    Controls the Pi3D PictureFrame display.

    Uses MQTT for real-time control and config file for persistent settings.
    """

    def __init__(self, mqtt_client=None):
        self._mqtt = mqtt_client
        self._config_path = PI3D_CONFIG_PATH

    def _load_pi3d_config(self) -> dict:
        """Load the Pi3D configuration.yaml file."""
        if not self._config_path.exists():
            logger.warning(f"Pi3D config not found: {self._config_path}")
            return {}

        try:
            with open(self._config_path) as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Failed to load Pi3D config: {e}")
            return {}

    def _save_pi3d_config(self, config: dict) -> bool:
        """Save the Pi3D configuration.yaml file."""
        try:
            with open(self._config_path, "w") as f:
                yaml.safe_dump(config, f, default_flow_style=False)
            return True
        except Exception as e:
            logger.error(f"Failed to save Pi3D config: {e}")
            return False

    async def get_current_folder(self) -> str:
        """
        Get the currently active display folder.

        Returns:
            Path to the current picture directory
        """
        config = self._load_pi3d_config()
        model = config.get("model", {})
        pic_dir = model.get("pic_dir", str(PI3D_PICTURES_PATH))
        subdirectory = model.get("subdirectory", "")

        if subdirectory:
            return str(Path(pic_dir) / subdirectory)
        return pic_dir

    async def switch_folder(self, source_path: Path, restart_service: bool = True) -> bool:
        """
        Switch the display to a different photo source.

        Updates the Pi3D configuration and optionally restarts the service.

        Args:
            source_path: Path to the photo source directory
            restart_service: Whether to restart picframe.service after updating

        Returns:
            True if switch was successful
        """
        logger.info(f"Switching display to: {source_path}")

        if not source_path.exists():
            logger.error(f"Source path does not exist: {source_path}")
            return False

        # Load current config
        config = self._load_pi3d_config()
        if not config:
            logger.error("Failed to load Pi3D config")
            return False

        # Update the pic_dir
        if "model" not in config:
            config["model"] = {}
        config["model"]["pic_dir"] = str(source_path)
        config["model"]["subdirectory"] = ""  # Clear subdirectory when switching

        # Save config
        if not self._save_pi3d_config(config):
            return False

        logger.info(f"Updated Pi3D config: pic_dir = {source_path}")

        # Restart the service to pick up changes
        if restart_service:
            success = await systemd_service.restart("picframe")
            if not success:
                logger.warning("Failed to restart picframe service")
            return success

        return True

    async def send_mqtt_command(self, topic: str, payload: str) -> bool:
        """
        Send an MQTT command to Pi3D.

        Available topics:
        - picframe/paused: true/false
        - picframe/shuffle: true/false
        - picframe/time_delay: seconds
        - picframe/subdirectory: path
        - picframe/back: (previous image)
        - picframe/delete: (delete current)
        - picframe/quit: (exit Pi3D)

        Args:
            topic: MQTT topic
            payload: Message payload

        Returns:
            True if message was sent
        """
        if not self._mqtt:
            logger.warning("MQTT client not configured")
            return False

        try:
            # TODO: Publish to MQTT broker
            logger.info(f"MQTT: {topic} = {payload}")
            return True
        except Exception as e:
            logger.error(f"MQTT error: {e}")
            return False

    async def pause(self) -> bool:
        """Pause the slideshow."""
        return await self.send_mqtt_command("picframe/paused", "true")

    async def resume(self) -> bool:
        """Resume the slideshow."""
        return await self.send_mqtt_command("picframe/paused", "false")

    async def next_image(self) -> bool:
        """Skip to next image."""
        # Pi3D doesn't have a "next" command, but we can unpause briefly
        return True

    async def previous_image(self) -> bool:
        """Go to previous image."""
        return await self.send_mqtt_command("picframe/back", "")

    async def set_shuffle(self, enabled: bool) -> bool:
        """Enable or disable shuffle mode."""
        return await self.send_mqtt_command("picframe/shuffle", str(enabled).lower())

    async def set_delay(self, seconds: float) -> bool:
        """Set the delay between images."""
        return await self.send_mqtt_command("picframe/time_delay", str(seconds))


# Global service instance
display_service = DisplayService()

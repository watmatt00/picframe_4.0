"""
PicFrame 4.0 - Display Service.

Controls the Pi3D PictureFrame display via MQTT and configuration.
"""

import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

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

    async def get_current_folder(self) -> str:
        """
        Get the currently active display folder.

        Returns:
            Path to the current picture directory
        """
        # TODO: Parse Pi3D configuration.yaml
        # Look for model.pic_dir
        return str(PI3D_PICTURES_PATH)

    async def switch_folder(self, source_path: Path) -> bool:
        """
        Switch the display to a different photo source.

        This can be done either by:
        1. Updating the Pi3D config and restarting the service
        2. Sending MQTT command to change subdirectory (if within pic_dir)

        Args:
            source_path: Path to the photo source directory

        Returns:
            True if switch was successful
        """
        logger.info(f"Switching display to: {source_path}")

        # TODO: Implement folder switching
        # Option 1: Update config and restart
        # Option 2: Use MQTT subdirectory command
        return False

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

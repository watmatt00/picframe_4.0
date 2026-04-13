"""
PicFrame 4.0 - Display Service.

Controls the Pi3D PictureFrame display via its built-in HTTP API and configuration.
"""

import asyncio
import logging
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel

from src.services.systemd_service import systemd_service

logger = logging.getLogger(__name__)

# Pi3D config location
PI3D_CONFIG_PATH = Path.home() / "picframe_data" / "config" / "configuration.yaml"
# Base pictures directory — Pi3D pic_dir is always anchored here
PI3D_PICTURES_PATH = Path.home() / "Pictures"
# Pi3D built-in HTTP control port
PI3D_HTTP_PORT = 9000


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

    Prefers Pi3D's built-in HTTP API (port 9000) for real-time directory
    switching — no service restart, seamless fade transition.  Falls back
    to config-file update + service restart only when the target path is
    outside ~/Pictures or the HTTP API is unreachable.
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

    async def _pi3d_set(self, key: str, value: str) -> bool:
        """Send a live control command to Pi3D's HTTP API.

        Pi3D accepts GET /?<key>=<value> to change settings in real time
        without any service restart.  Returns True if the request succeeded.
        """
        encoded = urllib.parse.quote(str(value), safe="")
        url = f"http://localhost:{PI3D_HTTP_PORT}/?{key}={encoded}"
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None,
                lambda: urllib.request.urlopen(url, timeout=3),
            )
            logger.debug(f"Pi3D HTTP: {key}={value!r}")
            return True
        except Exception as e:
            logger.warning(f"Pi3D HTTP API unavailable ({key}={value!r}): {e}")
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

        Strategy:
        1. If source_path is inside ~/Pictures, use Pi3D's live HTTP API
           (GET /?subdirectory=<rel>) — seamless fade, no restart.
        2. Update Pi3D configuration.yaml for persistence across reboots.
        3. Fall back to service restart only when outside ~/Pictures or
           when the HTTP API is unreachable.

        Args:
            source_path: Path to the photo source directory.
            restart_service: Whether to restart if HTTP API is unavailable.

        Returns:
            True if switch was successful.
        """
        logger.info(f"Switching display to: {source_path}")

        source_resolved = source_path.expanduser().resolve()
        pictures_resolved = PI3D_PICTURES_PATH.expanduser().resolve()

        if not source_resolved.exists():
            logger.error(f"Source path does not exist: {source_resolved}")
            return False

        # Determine subdirectory relative to ~/Pictures (None = outside, must restart)
        subdir: Optional[str] = None
        try:
            rel = source_resolved.relative_to(pictures_resolved)
            subdir = "" if str(rel) == "." else str(rel)
        except ValueError:
            pass  # Outside ~/Pictures — will fall back to restart

        # Always update Pi3D config for persistence across reboots
        config = self._load_pi3d_config()
        if not config:
            logger.error("Failed to load Pi3D config")
            return False
        if "model" not in config:
            config["model"] = {}

        if subdir is not None:
            config["model"]["pic_dir"] = str(pictures_resolved)
            config["model"]["subdirectory"] = subdir
        else:
            config["model"]["pic_dir"] = str(source_resolved)
            config["model"]["subdirectory"] = ""

        if not self._save_pi3d_config(config):
            return False

        logger.info(
            f"Updated Pi3D config: pic_dir={config['model']['pic_dir']!r}, "
            f"subdirectory={config['model']['subdirectory']!r}"
        )

        # Prefer live HTTP API — seamless, no restart
        if subdir is not None:
            ok = await self._pi3d_set("subdirectory", subdir)
            if ok:
                logger.info(f"Switched display via HTTP API: subdirectory={subdir!r}")
                return True
            logger.warning("Pi3D HTTP API failed — falling back to service restart")

        # Fall back to service restart
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

    async def get_time_delay(self) -> float:
        """Read the current time_delay from Pi3D's HTTP API. Falls back to config."""
        url = f"http://localhost:{PI3D_HTTP_PORT}/?all"
        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(
                None,
                lambda: urllib.request.urlopen(url, timeout=3),
            )
            import json
            data = json.loads(response.read().decode())
            return float(data.get("time_delay", 30.0))
        except Exception as e:
            logger.warning(f"Could not read time_delay from Pi3D: {e}")
            config = self._load_pi3d_config()
            return float(config.get("model", {}).get("time_delay", 30.0))

    async def set_delay(self, seconds: float) -> bool:
        """Set the delay between images via Pi3D HTTP API."""
        return await self._pi3d_set("time_delay", str(seconds))


# Global service instance
display_service = DisplayService()

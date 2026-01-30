"""
PicFrame 4.0 - Device Storage.

JSON-based storage for paired mobile devices.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from filelock import FileLock

from src.auth.models import Device

logger = logging.getLogger(__name__)

# Storage location
DEVICES_PATH = Path.home() / ".picframe" / "devices.json"
LOCK_TIMEOUT = 10


class DeviceStorage:
    """
    Persistent storage for paired devices.

    Uses JSON file with file locking for safe concurrent access.
    """

    def __init__(self, path: Path = DEVICES_PATH):
        self._path = path
        self._lock_path = path.with_suffix(".lock")
        self._lock = FileLock(self._lock_path, timeout=LOCK_TIMEOUT)

    def _load(self) -> list[Device]:
        """Load devices from file."""
        if not self._path.exists():
            return []

        try:
            with open(self._path) as f:
                data = json.load(f)
            return [Device(**d) for d in data.get("devices", [])]
        except Exception as e:
            logger.error(f"Failed to load devices: {e}")
            return []

    def _save(self, devices: list[Device]):
        """Save devices to file with proper permissions."""
        self._path.parent.mkdir(parents=True, exist_ok=True)

        data = {"devices": [d.model_dump(mode="json") for d in devices]}

        temp_path = self._path.with_suffix(".tmp")
        with open(temp_path, "w") as f:
            json.dump(data, f, indent=2, default=str)

        # Set restrictive permissions before rename
        os.chmod(temp_path, 0o600)
        temp_path.rename(self._path)

    def list_devices(self) -> list[Device]:
        """
        List all paired devices.

        Returns:
            List of Device objects
        """
        with self._lock:
            return self._load()

    def get_device(self, device_id: str) -> Optional[Device]:
        """
        Get a device by ID.

        Args:
            device_id: Device identifier

        Returns:
            Device if found, None otherwise
        """
        with self._lock:
            devices = self._load()
            for device in devices:
                if device.id == device_id:
                    return device
            return None

    def add_device(self, device: Device) -> bool:
        """
        Add a new paired device.

        Args:
            device: Device to add

        Returns:
            True if added successfully
        """
        with self._lock:
            devices = self._load()

            # Check for duplicate ID
            if any(d.id == device.id for d in devices):
                logger.warning(f"Device {device.id} already exists")
                return False

            devices.append(device)
            self._save(devices)
            logger.info(f"Added device: {device.name} ({device.id})")
            return True

    def remove_device(self, device_id: str) -> bool:
        """
        Remove a paired device.

        Args:
            device_id: Device to remove

        Returns:
            True if device was removed
        """
        with self._lock:
            devices = self._load()
            original_count = len(devices)

            # Check if this is the last admin
            admin_count = sum(1 for d in devices if d.role == "admin")
            target_device = next((d for d in devices if d.id == device_id), None)

            if target_device and target_device.role == "admin" and admin_count <= 1:
                logger.error("Cannot remove last admin device")
                return False

            devices = [d for d in devices if d.id != device_id]

            if len(devices) < original_count:
                self._save(devices)
                logger.info(f"Removed device: {device_id}")
                return True

            return False

    def update_last_seen(self, device_id: str):
        """
        Update the last_seen timestamp for a device.

        Args:
            device_id: Device to update
        """
        with self._lock:
            devices = self._load()

            for device in devices:
                if device.id == device_id:
                    device.last_seen = datetime.now(timezone.utc)
                    break

            self._save(devices)

    def count_admins(self) -> int:
        """Count the number of admin devices."""
        with self._lock:
            devices = self._load()
            return sum(1 for d in devices if d.role == "admin")


# Global storage instance
device_storage = DeviceStorage()

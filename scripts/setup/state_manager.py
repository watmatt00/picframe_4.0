"""
PicFrame Setup - State Manager.

Manages ~/.picframe/state.yaml with atomic writes and file locking.
Tracks provisioning state, WiFi status, and setup mode flag.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from filelock import FileLock
import yaml

logger = logging.getLogger(__name__)

STATE_DIR = Path("/var/lib/picframe")
STATE_FILE = STATE_DIR / "state.yaml"
LOCK_TIMEOUT = 10

DEFAULT_STATE: dict[str, Any] = {
    "frame_name": "picframe",
    "provisioned": False,
    "first_run_complete": False,
    "koofr_configured": False,
    "needs_setup": False,
    "last_wifi_connected": None,
    "setup_mode_reason": None,  # "boot_no_wifi" | "extended_outage" | "unprovisioned"
}


class StateManager:
    """
    Manages the PicFrame state file (~/.picframe/state.yaml).

    Uses FileLock + write-to-temp-then-rename for atomic, race-condition-free
    updates. Safe to call from multiple processes simultaneously.
    """

    def __init__(self, state_path: Path = STATE_FILE):
        self._path = state_path
        self._lock_path = state_path.with_suffix(".lock")
        self._lock = FileLock(self._lock_path, timeout=LOCK_TIMEOUT)

    def read(self) -> dict[str, Any]:
        """
        Read state file, returning defaults for any missing keys.

        Returns:
            State dictionary with all keys populated.
        """
        with self._lock:
            if not self._path.exists():
                return DEFAULT_STATE.copy()
            try:
                with open(self._path) as f:
                    data = yaml.safe_load(f) or {}
                # Merge with defaults so new keys are always present
                state = DEFAULT_STATE.copy()
                state.update(data)
                return state
            except Exception as e:
                logger.error(f"Failed to read state.yaml: {e}")
                return DEFAULT_STATE.copy()

    def write(self, state: dict[str, Any]) -> None:
        """
        Write state file atomically.

        Args:
            state: Full state dictionary to write.
        """
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self._path.with_suffix(".tmp")
            try:
                with open(temp_path, "w") as f:
                    yaml.safe_dump(state, f, default_flow_style=False)
                temp_path.rename(self._path)
                logger.debug("state.yaml updated")
            except Exception as e:
                logger.error(f"Failed to write state.yaml: {e}")
                if temp_path.exists():
                    temp_path.unlink()
                raise

    def set(self, key: str, value: Any) -> None:
        """
        Set a single state value.

        Args:
            key: State key (top-level only).
            value: Value to set.
        """
        with self._lock:
            state = self.read()
            state[key] = value
            self.write(state)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a single state value.

        Args:
            key: State key.
            default: Default if key not found.

        Returns:
            State value or default.
        """
        return self.read().get(key, default)

    def is_provisioned(self) -> bool:
        """Return True if frame has been provisioned (WiFi + credentials configured)."""
        return bool(self.get("provisioned", False))

    def needs_setup(self) -> bool:
        """Return True if frame should enter setup mode on next boot."""
        return bool(self.get("needs_setup", False))

    def mark_needs_setup(self, reason: str) -> None:
        """
        Set the needs_setup flag so setup mode starts on next boot.

        Args:
            reason: One of "boot_no_wifi", "extended_outage", "unprovisioned".
        """
        state = self.read()
        state["needs_setup"] = True
        state["setup_mode_reason"] = reason
        self.write(state)
        logger.info(f"[{_ts()}] needs_setup flag set (reason: {reason})")

    def clear_needs_setup(self) -> None:
        """Clear the needs_setup flag after successful WiFi recovery or provisioning."""
        state = self.read()
        state["needs_setup"] = False
        state["setup_mode_reason"] = None
        self.write(state)
        logger.info(f"[{_ts()}] needs_setup flag cleared")

    def mark_wifi_connected(self) -> None:
        """Record the current time as the last successful WiFi association."""
        self.set("last_wifi_connected", datetime.now().isoformat(timespec="seconds"))

    def initialize(self) -> None:
        """
        Create state.yaml with defaults if it does not exist.

        Safe to call multiple times (idempotent).
        """
        if not self._path.exists():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self.write(DEFAULT_STATE.copy())
            logger.info(f"[{_ts()}] state.yaml initialized at {self._path}")

    def show(self) -> str:
        """Return a human-readable summary of current state."""
        state = self.read()
        lines = ["PicFrame State:"]
        for key, value in state.items():
            lines.append(f"  {key}: {value}")
        return "\n".join(lines)


def _ts() -> str:
    """Return a log timestamp string."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# Global instance
state_manager = StateManager()

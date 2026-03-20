"""
PicFrame 4.0 - systemd Service Control.

Wrapper for controlling systemd user services.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Whitelist of services that can be controlled
ALLOWED_SERVICES = frozenset({"picframe", "picframe-api"})

# Allowed sync intervals in seconds (0 = disabled)
VALID_SYNC_INTERVALS = frozenset({0, 300, 600, 900, 1800, 2700, 3600, 7200, 21600, 43200, 86400})

# OnCalendar expressions for clock-aligned firing (multiples of interval from midnight)
_SYNC_CALENDAR = {
    300:   "*:0/5",
    600:   "*:0/10",
    900:   "*:0/15",
    1800:  "*:0/30",
    2700:  (
        "*-*-* "
        "00:00,00:45,01:30,02:15,03:00,03:45,04:30,05:15,"
        "06:00,06:45,07:30,08:15,09:00,09:45,10:30,11:15,"
        "12:00,12:45,13:30,14:15,15:00,15:45,16:30,17:15,"
        "18:00,18:45,19:30,20:15,21:00,21:45,22:30,23:15"
    ),
    3600:  "*:00",
    7200:  "*-*-* 00,02,04,06,08,10,12,14,16,18,20,22:00",
    21600: "*-*-* 00,06,12,18:00",
    43200: "*-*-* 00,12:00",
    86400: "*-*-* 00:00",
}

_SYNC_TIMER_PATH = Path.home() / ".config" / "systemd" / "user" / "picframe-sync.timer"

_TIMER_TEMPLATE = """\
[Unit]
Description=PicFrame 4.0 Photo Sync Timer
After=picframe-api.service

[Timer]
# Run 15 minutes after boot
OnBootSec=15min
# Fire at clock-aligned intervals
OnCalendar={calendar}
Persistent=true

[Install]
WantedBy=timers.target
"""


async def update_sync_timer(interval_seconds: int) -> bool:
    """
    Write a new picframe-sync.timer unit with the given interval and reload systemd.

    If interval_seconds is 0, stop the timer instead.
    interval_seconds must be a value from VALID_SYNC_INTERVALS.
    Returns True on success.
    """
    if interval_seconds not in VALID_SYNC_INTERVALS:
        logger.error(f"Invalid sync interval: {interval_seconds}")
        return False

    try:
        if interval_seconds == 0:
            proc = await asyncio.create_subprocess_exec(
                "systemctl", "--user", "stop", "picframe-sync.timer",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            logger.info("Sync timer stopped (disabled)")
            return True

        calendar = _SYNC_CALENDAR[interval_seconds]
        content = _TIMER_TEMPLATE.format(calendar=calendar)

        # Atomic write: temp file then rename
        tmp_path = _SYNC_TIMER_PATH.with_suffix(".timer.tmp")
        tmp_path.write_text(content)
        tmp_path.rename(_SYNC_TIMER_PATH)

        # Reload systemd unit files
        proc = await asyncio.create_subprocess_exec(
            "systemctl", "--user", "daemon-reload",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error(f"daemon-reload failed: {stderr.decode()}")
            return False

        # Restart the timer so the new OnCalendar takes effect immediately
        proc = await asyncio.create_subprocess_exec(
            "systemctl", "--user", "restart", "picframe-sync.timer",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error(f"timer restart failed: {stderr.decode()}")
            return False

        logger.info(f"Sync timer updated: OnCalendar={calendar}")
        return True

    except Exception as e:
        logger.error(f"Failed to update sync timer: {e}")
        return False


class ServiceStatus(BaseModel):
    """Status of a systemd service."""
    name: str
    active: bool
    status: str  # "running", "stopped", "failed", "unknown"
    enabled: bool


class SystemdService:
    """
    Controls systemd user services.

    Only whitelisted services can be controlled for security.
    Uses systemctl --user for user-level services.
    """

    @staticmethod
    def _validate_service(name: str) -> bool:
        """Check if service is in the allowed list."""
        if name not in ALLOWED_SERVICES:
            logger.warning(f"Attempted to control non-whitelisted service: {name}")
            return False
        return True

    async def get_status(self, service_name: str) -> Optional[ServiceStatus]:
        """
        Get the status of a systemd service.

        Args:
            service_name: Name of the service (without .service suffix)

        Returns:
            ServiceStatus if service exists, None otherwise
        """
        if not self._validate_service(service_name):
            return None

        try:
            # Check if active
            proc = await asyncio.create_subprocess_exec(
                "systemctl", "--user", "is-active", f"{service_name}.service",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            status_str = stdout.decode().strip()
            active = status_str == "active"

            # Check if enabled
            proc = await asyncio.create_subprocess_exec(
                "systemctl", "--user", "is-enabled", f"{service_name}.service",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            enabled = stdout.decode().strip() == "enabled"

            return ServiceStatus(
                name=service_name,
                active=active,
                status="running" if active else status_str,
                enabled=enabled,
            )

        except Exception as e:
            logger.error(f"Failed to get status for {service_name}: {e}")
            return None

    async def restart(self, service_name: str) -> bool:
        """
        Restart a systemd service.

        Args:
            service_name: Name of the service to restart

        Returns:
            True if restart was successful
        """
        if not self._validate_service(service_name):
            return False

        try:
            logger.info(f"Restarting service: {service_name}")

            proc = await asyncio.create_subprocess_exec(
                "systemctl", "--user", "restart", f"{service_name}.service",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode == 0:
                logger.info(f"Service {service_name} restarted successfully")
                return True
            else:
                logger.error(
                    f"Failed to restart {service_name}: {stderr.decode()}"
                )
                return False

        except Exception as e:
            logger.error(f"Failed to restart {service_name}: {e}")
            return False

    async def start(self, service_name: str) -> bool:
        """Start a systemd service."""
        if not self._validate_service(service_name):
            return False

        try:
            proc = await asyncio.create_subprocess_exec(
                "systemctl", "--user", "start", f"{service_name}.service",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            return proc.returncode == 0
        except Exception as e:
            logger.error(f"Failed to start {service_name}: {e}")
            return False

    async def stop(self, service_name: str) -> bool:
        """Stop a systemd service."""
        if not self._validate_service(service_name):
            return False

        try:
            proc = await asyncio.create_subprocess_exec(
                "systemctl", "--user", "stop", f"{service_name}.service",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            return proc.returncode == 0
        except Exception as e:
            logger.error(f"Failed to stop {service_name}: {e}")
            return False

    async def list_services(self) -> list[ServiceStatus]:
        """
        List all controllable services and their status.

        Returns:
            List of ServiceStatus for all allowed services
        """
        statuses = []
        for name in ALLOWED_SERVICES:
            status = await self.get_status(name)
            if status:
                statuses.append(status)
        return statuses


# Global service instance
systemd_service = SystemdService()

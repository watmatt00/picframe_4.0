"""
PicFrame 4.0 - systemd Service Control.

Wrapper for controlling systemd user services.
"""

import asyncio
import logging
from typing import Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Whitelist of services that can be controlled
ALLOWED_SERVICES = frozenset({"picframe", "picframe-api"})


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

"""
Frame network addresses (LAN and Tailscale), shared by the dashboard and the API.
"""

import logging
import socket
import subprocess

logger = logging.getLogger(__name__)


def get_tailscale_ip() -> str:
    """Return the Tailscale IPv4 address, or "" if Tailscale isn't available."""
    try:
        result = subprocess.run(
            ["tailscale", "ip", "-4"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        logger.warning(f"Failed to get Tailscale IP: {e}")
    return ""


def get_lan_ip() -> str:
    """Return the LAN IP of the primary interface, or "" when offline.

    Uses a UDP socket "connect" (no packet is sent) to find the outbound interface.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception as e:
        logger.warning(f"Failed to get LAN IP: {e}")
    return ""

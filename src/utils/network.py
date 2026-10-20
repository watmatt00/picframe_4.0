"""
Frame network addresses (LAN and Tailscale) and reachability checks, shared by
the dashboard and the API.
"""

import logging
import socket
import ssl
import subprocess
import time
from typing import Optional
from urllib.parse import urlparse

import httpx

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


def get_wifi_ssid() -> str:
    """Return the connected WiFi network name via nmcli, or "" (wired, offline or unknown)."""
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                parts = line.split(":", 1)
                if len(parts) == 2 and parts[0] == "yes":
                    return parts[1].strip()
    except Exception as e:
        logger.warning(f"Failed to get WiFi SSID: {e}")
    return ""


# Remote access (Funnel) check results: hostname -> (monotonic time, ok)
_remote_cache: dict[str, tuple[float, bool]] = {}
REMOTE_OK_TTL = 300    # recheck a working Funnel every 5 min
REMOTE_FAIL_TTL = 60   # and a failing one every minute


def _public_ip(hostname: str) -> str:
    """Resolve hostname through public DNS (Cloudflare DoH), bypassing the tailnet's MagicDNS."""
    r = httpx.get(
        "https://cloudflare-dns.com/dns-query",
        params={"name": hostname, "type": "A"},
        headers={"accept": "application/dns-json"},
        timeout=5,
    )
    r.raise_for_status()
    return next((a["data"] for a in r.json().get("Answer", []) if a.get("type") == 1), "")


def _health_via(ip: str, hostname: str) -> bool:
    """GET https://hostname/health through ip (TLS with SNI = hostname); True on HTTP 200."""
    ctx = ssl.create_default_context()
    with socket.create_connection((ip, 443), timeout=10) as sock:
        with ctx.wrap_socket(sock, server_hostname=hostname) as tls:
            tls.sendall(f"GET /health HTTP/1.1\r\nHost: {hostname}\r\nConnection: close\r\n\r\n".encode())
            status_line = tls.recv(64).split(b"\r\n", 1)[0]
    return status_line.split(b" ")[1:2] == [b"200"]


def check_remote_access(funnel_url: str) -> Optional[bool]:
    """Whether the frame answers on its Funnel URL from the public internet.

    Goes out through Tailscale's public relay, the path phones off the tailnet
    use; the tailnet can work while Funnel doesn't (tkframe, 2026-10-20).
    None when no Funnel URL is configured. Cached, so it's cheap per status call.
    """
    hostname = urlparse(funnel_url or "").hostname
    if not hostname:
        return None
    now = time.monotonic()
    cached = _remote_cache.get(hostname)
    if cached and now - cached[0] < (REMOTE_OK_TTL if cached[1] else REMOTE_FAIL_TTL):
        return cached[1]
    try:
        ip = _public_ip(hostname)
        ok = bool(ip) and _health_via(ip, hostname)
    except Exception as e:
        logger.warning(f"Remote access check for {hostname} failed: {e}")
        ok = False
    _remote_cache[hostname] = (now, ok)
    return ok

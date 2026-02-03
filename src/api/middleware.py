"""
PicFrame 4.0 - API Middleware.

LAN-only restriction for dashboard routes.
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Dashboard paths that should only be accessible from LAN
DASHBOARD_PATHS = ["/", "/settings", "/devices", "/pairing", "/logs"]

# Static files for dashboard
STATIC_PATHS = ["/static/"]

# Local network prefixes
LOCAL_PREFIXES = [
    "192.168.",
    "10.",
    "172.16.", "172.17.", "172.18.", "172.19.",
    "172.20.", "172.21.", "172.22.", "172.23.",
    "172.24.", "172.25.", "172.26.", "172.27.",
    "172.28.", "172.29.", "172.30.", "172.31.",
    "127.",
]

# Tailscale CGNAT range (Funnel traffic comes from here)
TAILSCALE_PREFIX = "100."


def is_local_ip(ip: str) -> bool:
    """Check if an IP address is from a local network."""
    if not ip:
        return False
    return any(ip.startswith(prefix) for prefix in LOCAL_PREFIXES)


def is_dashboard_path(path: str) -> bool:
    """Check if the path is a dashboard route."""
    # Exact match for root
    if path == "/":
        return True
    # Check other dashboard paths
    for dashboard_path in DASHBOARD_PATHS[1:]:
        if path.startswith(dashboard_path):
            return True
    # Check static files
    for static_path in STATIC_PATHS:
        if path.startswith(static_path):
            return True
    return False


class LANOnlyDashboardMiddleware(BaseHTTPMiddleware):
    """
    Middleware to restrict dashboard access to LAN only.
    
    - LAN users (192.168.x.x, 10.x.x.x, etc.) can access everything
    - Funnel users (100.x.x.x) can only access API endpoints, not dashboard
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        # Only check dashboard paths
        if is_dashboard_path(path):
            client_ip = ""
            if request.client:
                client_ip = request.client.host
            
            # Check for X-Forwarded-For header (in case of proxy)
            forwarded_for = request.headers.get("X-Forwarded-For")
            if forwarded_for:
                # Take the first IP in the chain
                client_ip = forwarded_for.split(",")[0].strip()
            
            if not is_local_ip(client_ip):
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "Dashboard only available on local network. Use the mobile app for remote access.",
                        "client_ip": client_ip,
                    }
                )
        
        return await call_next(request)

"""
PicFrame 4.0 - API Middleware.

Deny-by-default restriction for non-local clients.
"""

import ipaddress

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Paths reachable from the public internet (Tailscale Funnel).
# Everything under /api/v1/ enforces JWT auth itself (except POST /api/v1/pair,
# which is the pairing entry point). Everything else is LAN/tailnet only.
PUBLIC_PREFIXES = ("/api/v1/",)
PUBLIC_PATHS = {"/health", "/version"}

BLOCKED_MESSAGE = "Only available on local network. Use the mobile app for remote access."

# Shown instead of JSON when a browser opens the Funnel URL (PL-128).
# Self-contained: no external assets, nothing about the caller or the frame.
BLOCKED_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PicFrame</title>
<style>
  body { margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
         font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         background: #f4f4f5; color: #18181b; }
  main { max-width: 26rem; margin: 1rem; padding: 2rem; border-radius: 12px; background: #fff;
         box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12); text-align: center; }
  h1 { font-size: 1.25rem; margin: 0 0 0.75rem; }
  p { margin: 0; line-height: 1.5; color: #52525b; }
  @media (prefers-color-scheme: dark) {
    body { background: #18181b; color: #f4f4f5; }
    main { background: #27272a; box-shadow: none; }
    p { color: #a1a1aa; }
  }
</style>
</head>
<body>
<main>
  <h1>PicFrame</h1>
  <p>This frame's dashboard is only available on its home network.
     To manage it from anywhere, use the PicFrame Manager app.</p>
</main>
</body>
</html>
"""

# Local networks: RFC 1918, loopback, and Tailscale peers (direct WireGuard or
# tailnet Serve). Funnel traffic is not local: uvicorn rewrites request.client
# from the proxy's X-Forwarded-For only when the TCP peer is 127.0.0.1 (see
# forwarded_allow_ips in src/main.py), so it holds the real public caller IP.
LOCAL_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),  # Tailscale CGNAT range
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fd7a:115c:a1e0::/48"),  # Tailscale IPv6 range
]


def is_local_ip(ip: str) -> bool:
    """Check if an IP address is from a local network or Tailscale peer."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in network for network in LOCAL_NETWORKS)


def is_public_path(path: str) -> bool:
    """Check if the path may be reached from the public internet."""
    return path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES)


class LANOnlyMiddleware(BaseHTTPMiddleware):
    """
    Restrict everything except the JWT-protected API to LAN and Tailscale peers.

    - LAN users (192.168.x.x, 10.x.x.x, etc.) can access everything
    - Tailscale peers (100.64.0.0/10) can access everything
    - Funnel/public internet users can only reach /api/v1/*, /health, /version
    """

    async def dispatch(self, request: Request, call_next):
        """Reject non-local requests to non-public paths with 403 (HTML for browsers)."""
        path = request.url.path

        if not is_public_path(path):
            client_ip = request.client.host if request.client else ""
            if not is_local_ip(client_ip):
                if "text/html" in request.headers.get("accept", ""):
                    return HTMLResponse(BLOCKED_HTML, status_code=403)
                return JSONResponse(status_code=403, content={"detail": BLOCKED_MESSAGE})

        return await call_next(request)

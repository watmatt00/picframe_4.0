"""
PicFrame 4.0 - API Middleware.

Deny-by-default restriction for non-local clients, and a request body cap
for upload routes.
"""

import ipaddress

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

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


class UploadSizeLimitMiddleware:
    """
    Reject upload request bodies over a byte cap before they are parsed (PL-060).

    Without this, Starlette receives and spools the whole multipart body before
    the route can check the file size. A Content-Length over the cap gets 413
    immediately; a body without Content-Length (chunked) is counted as it
    arrives and fails with 413 once it passes the cap.
    """

    def __init__(self, app: ASGIApp, path_prefix: str, max_body_bytes: int) -> None:
        """
        Args:
            app: The wrapped ASGI app.
            path_prefix: Only POST requests under this path are limited.
            max_body_bytes: Largest request body accepted, in bytes.
        """
        self.app = app
        self.path_prefix = path_prefix
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Apply the cap to matching requests; pass everything else through."""
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or not scope["path"].startswith(self.path_prefix)
        ):
            await self.app(scope, receive, send)
            return

        too_large = {"detail": f"Upload too large (max {self.max_body_bytes // (1024 * 1024)} MB)"}
        headers = dict(scope["headers"])
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                await JSONResponse(status_code=400, content={"detail": "Invalid Content-Length"})(
                    scope, receive, send
                )
                return
            if declared > self.max_body_bytes:
                await JSONResponse(status_code=413, content=too_large)(scope, receive, send)
                return

        received = 0
        overflowed = False
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received, overflowed
            if overflowed:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    # Stop reading: the app sees a client disconnect. An exception
                    # raised here would reach FastAPI wrapped by BaseHTTPMiddleware
                    # and come out as a generic 400.
                    overflowed = True
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal response_started
            if overflowed:
                return  # whatever the app sends after the cut-off is replaced by the 413
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except Exception:
            if not overflowed:
                raise
        if overflowed and not response_started:
            await JSONResponse(status_code=413, content=too_large)(scope, receive, send)

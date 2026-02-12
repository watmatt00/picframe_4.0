"""
PicFrame 4.0 API - FastAPI Application.

This is the main FastAPI application that provides:
- REST API endpoints for mobile app (JWT authenticated)
- Web dashboard for LAN access (no auth)
- Health and version endpoints

See docs/SPECIFICATION.md for full API documentation.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# API route imports
from src.api.routes import pairing, status, devices, services, display, folders, contributors, cloud, settings, logs

# Dashboard routes
from src.dashboard import routes as dashboard_routes

# Middleware
from src.api.middleware import LANOnlyDashboardMiddleware

app = FastAPI(
    title="PicFrame 4.0 API",
    description="Secure mobile management for Raspberry Pi picture frames",
    version="4.0.0",
)

# Add LAN-only middleware for dashboard routes
app.add_middleware(LANOnlyDashboardMiddleware)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/version")
async def version():
    """API version endpoint."""
    return {"version": "4.0.0", "api": "picframe"}


# DEBUG: Test token generation - REMOVE IN PRODUCTION
@app.get("/debug/token")
async def debug_token():
    """Generate a test token for development. REMOVE IN PRODUCTION."""
    from src.auth.jwt_handler import create_token
    import uuid
    token = create_token(
        device_id=str(uuid.uuid4()),
        device_name="Debug Device",
        role="admin",
        frame_id="tkframe",
    )
    return {"token": token, "warning": "DEBUG ENDPOINT - REMOVE IN PRODUCTION"}


# Include dashboard routes (LAN only, no auth)
app.include_router(dashboard_routes.router)

# Include API routes with /api/v1 prefix (JWT authenticated via mobile app)
app.include_router(pairing.router, prefix="/api/v1")
app.include_router(status.router, prefix="/api/v1")
app.include_router(devices.router, prefix="/api/v1")
app.include_router(services.router, prefix="/api/v1")
app.include_router(display.router, prefix="/api/v1")
app.include_router(folders.router, prefix="/api/v1")
app.include_router(contributors.router, prefix="/api/v1")
app.include_router(cloud.router, prefix="/api/v1")
app.include_router(settings.router, prefix="/api/v1")
app.include_router(logs.router, prefix="/api/v1")

# Mount static files for dashboard
static_dir = Path(__file__).parent.parent / "dashboard" / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

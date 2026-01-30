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
from src.api.routes import pairing, status, devices, services, display, folders, contributors

# Dashboard routes
from src.dashboard import routes as dashboard_routes

app = FastAPI(
    title="PicFrame 4.0 API",
    description="Secure mobile management for Raspberry Pi picture frames",
    version="4.0.0",
)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/version")
async def version():
    """API version endpoint."""
    return {"version": "4.0.0", "api": "picframe"}


# Include API routes (JWT authenticated)
app.include_router(pairing.router)
app.include_router(status.router)
app.include_router(devices.router)
app.include_router(services.router)
app.include_router(display.router)
app.include_router(folders.router)
app.include_router(contributors.router)

# Include dashboard routes (LAN only, no auth)
app.include_router(dashboard_routes.router)

# Mount static files for dashboard
static_dir = Path(__file__).parent.parent / "dashboard" / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

"""
PicFrame 4.0 - Dashboard Routes.

Server-rendered pages for the web dashboard.
Uses Jinja2 templates.
"""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["dashboard"])

# Template directory
TEMPLATE_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


@router.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    """
    Dashboard home page.

    Shows status overview: file counts, sync state, service health.
    """
    # TODO: Gather real status data
    context = {
        "request": request,
        "frame_name": "PicFrame",
        "current_source": "Main Photos",
        "local_count": 0,
        "remote_count": 0,
        "sync_status": "unknown",
        "services": [],
    }
    return templates.TemplateResponse("dashboard.html", context)


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """
    Settings page.

    Allows editing frame configuration.
    """
    context = {
        "request": request,
        "config": {},
    }
    return templates.TemplateResponse("settings.html", context)


@router.post("/settings")
async def save_settings(request: Request):
    """Save settings from form submission."""
    # TODO: Parse form data and save config
    return {"status": "ok"}


@router.get("/devices", response_class=HTMLResponse)
async def devices_page(request: Request):
    """
    Device management page.

    Lists paired devices with option to revoke.
    """
    context = {
        "request": request,
        "devices": [],
    }
    return templates.TemplateResponse("devices.html", context)


@router.get("/pairing", response_class=HTMLResponse)
async def pairing_page(request: Request):
    """
    Pairing page.

    Shows QR code for mobile app pairing.
    """
    # TODO: Generate pairing code and QR
    context = {
        "request": request,
        "qr_data_url": "",
        "code": "",
        "expires_in": 300,
    }
    return templates.TemplateResponse("pairing.html", context)


@router.post("/pairing/generate")
async def generate_pairing():
    """Generate a new pairing code."""
    # TODO: Generate pairing code
    return {"code": "", "qr_data_url": "", "expires_at": ""}


@router.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    """
    Log viewer page.

    Shows recent log entries.
    """
    context = {
        "request": request,
        "logs": [],
    }
    return templates.TemplateResponse("logs.html", context)


@router.get("/api/logs")
async def get_logs(lines: int = 100, log_type: str = "ops"):
    """
    Get recent log entries.

    Args:
        lines: Number of lines to return
        log_type: "ops" or "security"
    """
    # TODO: Read log files
    return {"logs": []}

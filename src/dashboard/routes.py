"""
PicFrame 4.0 - Dashboard Routes.

Server-rendered pages for the web dashboard.
Uses Jinja2 templates.
"""

import shutil
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from src.config.settings import get_settings
from src.config.manager import config_manager
from src.services.source_manager import source_manager
from src.services.sync_service import sync_service
from src.services.systemd_service import systemd_service
from src.services.display_service import display_service
from src.storage.devices import device_storage
from src.auth.pairing import generate_pairing_code
from src.utils.qr_generator import generate_qr_data_url
from src.utils.rclone import count_local_files

router = APIRouter(tags=["dashboard"])

# Template directory
TEMPLATE_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# Log files location
LOGS_DIR = Path.home() / ".picframe" / "logs"

# Track last service restart (in memory)
_last_restart: datetime | None = None


@router.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    """
    Dashboard home page.

    Shows status overview: file counts, sync state, service health.
    """
    settings = get_settings()

    # Get current source info
    current_source_id = settings.display.current_source
    sources = source_manager.list_sources()
    current_source = next((s for s in sources if s.id == current_source_id), None)

    # Count photos
    local_count = 0
    if current_source:
        local_count = count_local_files(current_source.local_path)

    # Determine sync status
    sync_status = "idle"
    if sync_service._is_syncing:
        sync_status = "syncing"
    elif sync_service._last_sync:
        sync_status = "match" if sync_service._last_sync.success else "error"

    # Get service statuses
    services = await systemd_service.list_services()

    # Get storage capacity
    pictures_path = Path.home() / "Pictures"
    try:
        usage = shutil.disk_usage(pictures_path)
        storage_used = round(usage.used / (1024**3), 1)
        storage_total = round(usage.total / (1024**3), 1)
        storage_percent = round((usage.used / usage.total) * 100, 1) if usage.total > 0 else 0
    except Exception:
        storage_used = 0
        storage_total = 0
        storage_percent = 0

    context = {
        "request": request,
        "frame_name": settings.frame.name,
        "frame_id": settings.frame.id,
        "current_source": current_source.name if current_source else "Unknown",
        "current_source_id": current_source_id,
        "sources": sources,
        "local_count": local_count,
        "remote_count": 0,
        "sync_status": sync_status,
        "is_syncing": sync_service._is_syncing,
        "services": services,
        "storage_used": storage_used,
        "storage_total": storage_total,
        "storage_percent": storage_percent,
        "rotation_interval": settings.display.rotation_interval,
        "sync_interval": settings.sync.interval,
        "log_level": settings.logging.level,
    }
    return templates.TemplateResponse("dashboard.html", context)


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """
    Settings page.

    Allows editing frame configuration.
    """
    settings = get_settings()

    context = {
        "request": request,
        "frame_id": settings.frame.id,
        "frame_name": settings.frame.name,
        "funnel_url": settings.frame.funnel_url,
        "current_source": settings.display.current_source,
        "rotation_interval": settings.display.rotation_interval,
        "sync_interval": settings.sync.interval,
        "log_level": settings.logging.level,
    }
    return templates.TemplateResponse("settings.html", context)


@router.post("/settings")
async def save_settings(
    request: Request,
    frame_name: str = Form(...),
    rotation_interval: int = Form(...),
    sync_interval: int = Form(...),
    log_level: str = Form(...),
):
    """Save settings from form submission."""
    config_manager.set("frame.name", frame_name)
    config_manager.set("display.rotation_interval", rotation_interval)
    config_manager.set("sync.interval", sync_interval)
    config_manager.set("logging.level", log_level)

    return RedirectResponse(url="/settings?saved=1", status_code=303)


@router.get("/devices", response_class=HTMLResponse)
async def devices_page(request: Request):
    """
    Device management page.

    Lists paired devices with option to revoke.
    """
    devices = device_storage.list_devices()
    admin_count = device_storage.count_admins()

    context = {
        "request": request,
        "devices": devices,
        "admin_count": admin_count,
        "can_revoke": admin_count > 1,
    }
    return templates.TemplateResponse("devices.html", context)


@router.post("/devices/{device_id}/revoke")
async def revoke_device(device_id: str):
    """Revoke a paired device."""
    device = device_storage.get_device(device_id)
    if not device:
        return RedirectResponse(url="/devices?error=not_found", status_code=303)

    # Check if this is the last admin
    if device.role == "admin" and device_storage.count_admins() <= 1:
        return RedirectResponse(url="/devices?error=last_admin", status_code=303)

    success = device_storage.remove_device(device_id)
    if success:
        return RedirectResponse(url="/devices?revoked=1", status_code=303)
    else:
        return RedirectResponse(url="/devices?error=failed", status_code=303)


@router.get("/pairing", response_class=HTMLResponse)
async def pairing_page(request: Request):
    """
    Pairing page.

    Shows QR code for mobile app pairing.
    """
    settings = get_settings()

    # Generate a new pairing code
    pairing_code = generate_pairing_code()

    if pairing_code:
        # Generate QR code with frame URL and code
        qr_data_url = generate_qr_data_url(
            url=settings.frame.funnel_url,
            code=pairing_code.code,
            frame_name=settings.frame.name,
        )
        context = {
            "request": request,
            "qr_data_url": qr_data_url,
            "code": pairing_code.code,
            "expires_in": 300,
            "frame_name": settings.frame.name,
            "funnel_url": settings.frame.funnel_url,
            "error": None,
        }
    else:
        context = {
            "request": request,
            "qr_data_url": "",
            "code": "",
            "expires_in": 0,
            "frame_name": settings.frame.name,
            "funnel_url": settings.frame.funnel_url,
            "error": "Rate limit exceeded. Try again in a few minutes.",
        }

    return templates.TemplateResponse("pairing.html", context)


@router.post("/pairing/generate")
async def generate_pairing_endpoint():
    """Generate a new pairing code (AJAX endpoint)."""
    settings = get_settings()
    pairing_code = generate_pairing_code()

    if pairing_code:
        qr_data_url = generate_qr_data_url(
            url=settings.frame.funnel_url,
            code=pairing_code.code,
            frame_name=settings.frame.name,
        )
        return {
            "code": pairing_code.code,
            "qr_data_url": qr_data_url,
            "expires_at": pairing_code.expires_at.isoformat(),
        }
    else:
        return {"error": "Rate limit exceeded"}


@router.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request, log_type: str = "ops", lines: int = 100):
    """
    Log viewer page.

    Shows recent log entries.
    """
    logs = _read_log_file(log_type, lines)

    context = {
        "request": request,
        "logs": logs,
        "log_type": log_type,
        "lines": lines,
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
    logs = _read_log_file(log_type, lines)
    return {"logs": logs, "log_type": log_type}


def _read_log_file(log_type: str, lines: int = 100) -> list[str]:
    """Read log file and return recent lines."""
    if log_type == "security":
        log_file = LOGS_DIR / "security.log"
    else:
        log_file = LOGS_DIR / "picframe.log"

    if not log_file.exists():
        return []

    try:
        with open(log_file, "r") as f:
            all_lines = f.readlines()
        # Return last N lines, reversed (newest first)
        return [line.strip() for line in all_lines[-lines:]][::-1]
    except Exception:
        return []


# Dashboard sync trigger (no auth required on LAN)
@router.post("/sync")
async def trigger_sync():
    """Trigger a sync from the dashboard."""
    sources = source_manager.list_sources()
    syncable = [s for s in sources if s.enabled and s.rclone_remote]

    if not syncable:
        return {"error": "No sources with remotes configured"}

    if sync_service._is_syncing:
        return {"error": "Sync already in progress"}

    # Sync the first enabled source
    source = syncable[0]
    from pathlib import Path

    # Run sync in background (don't await)
    import asyncio
    asyncio.create_task(
        sync_service.sync_source(
            source_id=source.id,
            local_path=Path(source.local_path),
            rclone_remote=source.rclone_remote,
        )
    )

    return {"status": "started", "source": source.id}


# Dashboard folder switch (no auth required on LAN)
@router.post("/switch-source")
async def switch_source(source_id: str = Form(...)):
    """Switch the display source from the dashboard."""
    source = source_manager.get_source(source_id)
    if not source:
        return RedirectResponse(url="/?error=source_not_found", status_code=303)

    source_path = Path(source.local_path)
    if not source_path.exists():
        source_path.mkdir(parents=True, exist_ok=True)

    success = await display_service.switch_folder(source_path)
    if success:
        config_manager.set("display.current_source", source_id)
        return RedirectResponse(url="/?switched=1", status_code=303)
    else:
        return RedirectResponse(url="/?error=switch_failed", status_code=303)


@router.get("/dashboard/status")
async def get_dashboard_status():
    """
    Get dashboard status as JSON for AJAX updates.

    Returns sync status, file counts, service status, storage info.
    """
    settings = get_settings()

    # Get current source info
    current_source_id = settings.display.current_source
    sources = source_manager.list_sources()
    current_source = next((s for s in sources if s.id == current_source_id), None)

    # Count photos
    local_count = 0
    if current_source:
        local_count = count_local_files(current_source.local_path)

    # Determine sync status
    sync_status = "idle"
    if sync_service._is_syncing:
        sync_status = "syncing"
    elif sync_service._last_sync:
        sync_status = "match" if sync_service._last_sync.success else "error"

    # Get service statuses
    services = await systemd_service.list_services()
    services_data = [
        {"name": s.name, "active": s.active, "status": s.status}
        for s in services
    ]

    # Get storage capacity
    pictures_path = Path.home() / "Pictures"
    try:
        usage = shutil.disk_usage(pictures_path)
        storage_used = round(usage.used / (1024**3), 1)
        storage_total = round(usage.total / (1024**3), 1)
        storage_percent = round((usage.used / usage.total) * 100, 1) if usage.total > 0 else 0
    except Exception:
        storage_used = 0
        storage_total = 0
        storage_percent = 0

    # Get last sync time
    last_sync = None
    if sync_service._last_sync:
        last_sync = sync_service._last_sync.timestamp.strftime("%Y-%m-%d %H:%M:%S")

    # Get recent logs
    logs = _read_log_file("ops", 20)

    # Get last restart time
    last_restart = None
    if _last_restart:
        last_restart = _last_restart.strftime("%Y-%m-%d %H:%M:%S")

    return {
        "sync_status": sync_status,
        "local_count": local_count,
        "remote_count": 0,
        "current_source": current_source.name if current_source else "Unknown",
        "services": services_data,
        "storage_used": storage_used,
        "storage_total": storage_total,
        "storage_percent": storage_percent,
        "last_sync": last_sync,
        "last_restart": last_restart,
        "logs": logs,
    }


@router.get("/current-image")
async def get_current_image():
    """
    Proxy the current image from Pi3D PictureFrame.

    Pi3D serves current image on port 9000.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:9000/current_image", timeout=5.0)
            return Response(
                content=resp.content,
                media_type=resp.headers.get("content-type", "image/jpeg"),
            )
    except Exception:
        # Return a placeholder or error
        return Response(content=b"", status_code=404)


# LAN-only service restart (no auth required - protected by LAN middleware)
ALLOWED_SERVICES = {"picframe", "picframe-api"}


@router.post("/services/{service_name}/restart")
async def restart_service_from_dashboard(service_name: str):
    """
    Restart a service from the dashboard.

    LAN-only endpoint, no JWT auth required.
    """
    global _last_restart

    if service_name not in ALLOWED_SERVICES:
        return {"error": f"Service '{service_name}' not allowed"}

    try:
        success = await systemd_service.restart_service(service_name)
        if success:
            _last_restart = datetime.now()
            return {"ok": True, "service": service_name}
        else:
            return {"ok": False, "error": "Restart failed"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

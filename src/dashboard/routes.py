"""
PicFrame 4.0 - Dashboard Routes.

Server-rendered pages for the web dashboard.
Uses Jinja2 templates.
"""

import asyncio
import logging
import re
from datetime import datetime
from pathlib import Path

import httpx
import yaml
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from src.config.settings import get_settings, reload_settings
from src.config.manager import config_manager
from src.services.source_manager import source_manager
from src.services.sync_service import sync_service
from src.services.systemd_service import systemd_service
from src.services.display_service import display_service
from src.services.status_service import (
    get_current_source,
    get_photo_counts,
    determine_sync_status,
    get_disk_capacity,
    PICTURES_PATH,
)
from src.storage.devices import device_storage
from src.auth.pairing import generate_pairing_code
from src.utils.qr_generator import generate_qr_data_url
from src.utils.rclone import count_local_files, rclone_list_remotes

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dashboard"])

# Template directory
TEMPLATE_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# Log files location
LOGS_DIR = Path.home() / ".picframe" / "logs"

# Picframe config file location
PICFRAME_CONFIG_PATH = Path.home() / "picframe_data" / "config" / "configuration.yaml"


def _get_picframe_config() -> dict:
    """Read picframe configuration.yaml file."""
    if PICFRAME_CONFIG_PATH.exists():
        try:
            with open(PICFRAME_CONFIG_PATH) as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Failed to read picframe config: {e}")
    return {}


def _get_tailscale_ip() -> str:
    """Get the Tailscale IPv4 address."""
    try:
        import subprocess
        result = subprocess.run(
            ["tailscale", "ip", "-4"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        logger.warning(f"Failed to get Tailscale IP: {e}")
    return ""



@router.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    """
    Dashboard home page.

    Shows status overview: file counts, sync state, service health.
    """
    settings = get_settings()

    # Get current source info (shared logic)
    current_source_id, current_source = get_current_source()
    sources = source_manager.list_sources()

    # Count photos (local only for initial page render)
    local_count = 0
    if current_source:
        local_count = count_local_files(current_source.local_path)

    # Determine sync status (shared logic)
    sync_status = determine_sync_status(local_count, 0)

    # Get service statuses
    services = await systemd_service.list_services()

    # Get storage capacity (shared logic)
    capacity = get_disk_capacity(PICTURES_PATH)

    # Get rotation interval from picframe config
    picframe_config = _get_picframe_config()
    rotation_interval = int(picframe_config.get("model", {}).get("time_delay", 30))
    pf_log_level = picframe_config.get("model", {}).get("log_level", "WARNING")

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
        "storage_used": capacity["used_gb"],
        "storage_total": capacity["total_gb"],
        "storage_percent": capacity["percent_used"],
        "rotation_interval": rotation_interval,
        "sync_interval": settings.sync.interval,
        "log_level": pf_log_level,
        "funnel_url": settings.frame.funnel_url or "",
        "tailscale_ip": _get_tailscale_ip(),
        "api_port": 8000,
    }
    return templates.TemplateResponse("dashboard.html", context)


@router.post("/devices/{device_id}/revoke")
async def revoke_device(device_id: str):
    """Revoke a paired device (AJAX endpoint)."""
    # Validate device_id format
    if not re.match(r"^[a-zA-Z0-9_-]+$", device_id):
        return {"ok": False, "error": "Invalid device ID"}

    device = device_storage.get_device(device_id)
    if not device:
        return {"ok": False, "error": "Device not found"}

    # Check if this is the last admin
    if device.role == "admin" and device_storage.count_admins() <= 1:
        return {"ok": False, "error": "Cannot revoke the last admin device"}

    success = device_storage.remove_device(device_id)
    if success:
        logger.info(f"Device '{device.name}' ({device_id}) revoked via dashboard")
        return {"ok": True}
    else:
        return {"ok": False, "error": "Failed to revoke device"}


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


def _last_matching_timestamp(log_file: Path, needle: str) -> str | None:
    """
    Find the timestamp of the last log line containing the needle string.

    Expects log format: "YYYY-MM-DD HH:MM:SS ..."
    """
    if not log_file.exists():
        return None

    last_line = None
    try:
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if needle.lower() in line.lower():
                    last_line = line
    except Exception:
        return None

    if not last_line:
        return None

    # Extract timestamp from start of line (first 19 chars: "YYYY-MM-DD HH:MM:SS")
    ts_str = last_line[:19]
    try:
        datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        return ts_str
    except ValueError:
        return None


def _get_last_sync_time() -> str | None:
    """Get timestamp of last sync from systemd timer stamp or logs."""
    # First check systemd timer stamp file (most reliable)
    stamp_file = Path.home() / ".local" / "share" / "systemd" / "timers" / "stamp-picframe-sync.timer"
    if stamp_file.exists():
        try:
            mtime = stamp_file.stat().st_mtime
            return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

    # Fallback to log file
    log_file = LOGS_DIR / "picframe.log"
    return _last_matching_timestamp(log_file, "sync") or \
           _last_matching_timestamp(log_file, "rclone")


async def _get_last_restart_time() -> str | None:
    """Get timestamp of last service restart from systemd."""
    latest = None
    for svc in ("picframe", "picframe-api"):
        try:
            proc = await asyncio.create_subprocess_exec(
                "systemctl", "--user", "show", f"{svc}.service",
                "--property=ActiveEnterTimestamp",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            line = stdout.decode().strip()
            # Format: ActiveEnterTimestamp=Wed 2026-02-11 14:28:23 MST
            if "=" in line:
                ts_str = line.split("=", 1)[1].strip()
                if ts_str:
                    # Parse systemd timestamp (e.g. "Wed 2026-02-11 14:28:23 MST")
                    # Strip day name and timezone for parsing
                    parts = ts_str.split()
                    if len(parts) >= 4:
                        dt = datetime.strptime(
                            f"{parts[1]} {parts[2]}", "%Y-%m-%d %H:%M:%S"
                        )
                        if latest is None or dt > latest:
                            latest = dt
        except Exception:
            continue
    return latest.strftime("%Y-%m-%d %H:%M:%S") if latest else None


# Dashboard sync trigger (no auth required on LAN)
@router.post("/sync")
async def trigger_sync():
    """Trigger a sync from the dashboard."""
    settings = get_settings()
    current_source_id = settings.display.current_source

    # Find the active source
    source = source_manager.get_source(current_source_id) if current_source_id else None

    if not source or not source.rclone_remote:
        # Fall back to first enabled source with a remote
        sources = source_manager.list_sources()
        syncable = [s for s in sources if s.enabled and s.rclone_remote]
        if not syncable:
            return {"error": "No sources with remotes configured"}
        source = syncable[0]

    if sync_service._is_syncing:
        return {"error": "Sync already in progress"}

    async def run_sync_with_logging():
        """Run sync and update timestamp/logs."""
        logger.info(f"Starting sync for source '{source.id}' from {source.rclone_remote}")
        try:
            await sync_service.sync_source(
                source_id=source.id,
                local_path=Path(source.local_path),
                rclone_remote=source.rclone_remote,
            )
            logger.info(f"Sync completed for source '{source.id}'")
        except Exception as e:
            logger.error(f"Sync failed for source '{source.id}': {e}")

        # Update the systemd timer stamp file to reflect manual sync
        stamp_file = Path.home() / ".local" / "share" / "systemd" / "timers" / "stamp-picframe-sync.timer"
        try:
            stamp_file.parent.mkdir(parents=True, exist_ok=True)
            stamp_file.touch()
        except Exception as e:
            logger.warning(f"Failed to update sync stamp file: {e}")

    # Run sync in background
    asyncio.create_task(run_sync_with_logging())

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
        reload_settings()  # Clear cached settings
        return RedirectResponse(url="/?switched=1", status_code=303)
    else:
        return RedirectResponse(url="/?error=switch_failed", status_code=303)


@router.get("/dashboard/status")
async def get_dashboard_status():
    """
    Get dashboard status as JSON for AJAX updates.

    Returns sync status, file counts, service status, storage info.
    """
    # Get current source info (shared logic)
    current_source_id, current_source = get_current_source()

    # Count photos (shared logic - uses rclone_count instead of manual subprocess)
    local_count, remote_count = await get_photo_counts(current_source)

    # Determine sync status (shared logic)
    sync_status = determine_sync_status(local_count, remote_count)

    # Get service statuses
    services = await systemd_service.list_services()
    services_data = [
        {"name": s.name, "active": s.active, "status": s.status}
        for s in services
    ]

    # Get storage capacity (shared logic)
    capacity = get_disk_capacity(PICTURES_PATH)

    # Get last sync/restart times
    last_sync = _get_last_sync_time()
    last_restart = await _get_last_restart_time()

    return {
        "sync_status": sync_status,
        "local_count": local_count,
        "remote_count": remote_count,
        "current_source": current_source.name if current_source else "Unknown",
        "services": services_data,
        "storage_used": capacity["used_gb"],
        "storage_total": capacity["total_gb"],
        "storage_percent": capacity["percent_used"],
        "last_sync": last_sync,
        "last_restart": last_restart,
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
    if service_name not in ALLOWED_SERVICES:
        return {"error": f"Service '{service_name}' not allowed"}

    try:
        success = await systemd_service.restart(service_name)
        if success:
            logger.info(f"Service {service_name} restarted successfully via dashboard")
            return {"ok": True, "service": service_name}
        else:
            logger.error(f"Failed to restart service {service_name}")
            return {"ok": False, "error": "Restart failed"}
    except Exception as e:
        logger.error(f"Error restarting service {service_name}: {e}")
        return {"ok": False, "error": str(e)}


# =============================================================================
# LAN-only Source Management API (no JWT auth - protected by LAN middleware)
# =============================================================================


class CreateSourceRequest(BaseModel):
    """Request to create a new photo source."""
    name: str


class ListDirsRequest(BaseModel):
    """Request to list remote directories."""
    remote: str
    path: str = ""


@router.get("/api/devices")
async def list_devices_api():
    """
    List paired devices as JSON for dashboard AJAX.

    LAN-only endpoint, no JWT auth required.
    """
    devices = device_storage.list_devices()
    admin_count = device_storage.count_admins()

    result = []
    for device in devices:
        result.append({
            "id": device.id,
            "name": device.name,
            "role": device.role,
            "paired_at": device.paired_at.strftime("%Y-%m-%d %H:%M") if device.paired_at else None,
            "last_seen": device.last_seen.strftime("%Y-%m-%d %H:%M") if device.last_seen else None,
        })

    return {
        "devices": result,
        "admin_count": admin_count,
        "device_count": len(result),
    }


@router.get("/api/sources")
async def list_sources_api():
    """
    List all configured sources for the dashboard.

    LAN-only endpoint, no JWT auth required.
    """
    settings = get_settings()
    current_source_id = settings.display.current_source
    sources = source_manager.list_sources()

    result = []
    for source in sources:
        photo_count = count_local_files(source.local_path)
        result.append({
            "id": source.id,
            "label": source.name,
            "remote": source.rclone_remote or "",
            "path": source.local_path,
            "enabled": source.enabled,
            "active": source.id == current_source_id,
            "photo_count": photo_count,
        })

    return {"sources": result}


@router.post("/api/sources/create")
async def create_source_api(request: CreateSourceRequest):
    """
    Create a new photo source from the dashboard.

    LAN-only endpoint, no JWT auth required.
    """
    if not request.name.strip():
        return {"ok": False, "error": "Name is required"}

    try:
        source = source_manager.create_source(name=request.name.strip())
        logger.info(f"Created source '{source.id}' via dashboard")
        return {"ok": True, "source_id": source.id}
    except Exception as e:
        logger.error(f"Failed to create source: {e}")
        return {"ok": False, "error": str(e)}


class DeleteSourceRequest(BaseModel):
    """Request to delete a source."""
    source_id: str


@router.post("/api/sources/delete")
async def delete_source_api(request: DeleteSourceRequest):
    """
    Delete a photo source from the dashboard.

    LAN-only endpoint, no JWT auth required.
    """
    if source_manager.delete_source(request.source_id):
        logger.info(f"Deleted source '{request.source_id}' via dashboard")
        return {"ok": True}
    else:
        return {"ok": False, "error": f"Source '{request.source_id}' not found"}


@router.get("/api/rclone/remotes")
async def list_rclone_remotes():
    """
    List configured rclone remotes.

    LAN-only endpoint, no JWT auth required.
    """
    try:
        remotes = await rclone_list_remotes()
        # Return with trailing colon as v3 expects
        return {"ok": True, "remotes": [f"{r}:" for r in remotes]}
    except Exception as e:
        logger.error(f"Failed to list rclone remotes: {e}")
        return {"ok": False, "error": str(e), "remotes": []}


@router.post("/api/rclone/list-dirs")
async def list_remote_dirs(request: ListDirsRequest):
    """
    List directories in an rclone remote.

    LAN-only endpoint, no JWT auth required.
    """
    # Validate remote name
    remote_name = request.remote.rstrip(":")
    if not re.match(r"^[a-zA-Z0-9_-]+$", remote_name):
        return {"ok": False, "error": "Invalid remote name", "dirs": []}

    # Build full path
    full_path = f"{remote_name}:{request.path}" if request.path else f"{remote_name}:"

    try:
        proc = await asyncio.create_subprocess_exec(
            "rclone", "lsf", full_path, "--dirs-only",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            error_msg = stderr.decode().strip() or "Failed to list directories"
            return {"ok": False, "error": error_msg, "dirs": []}

        # Parse directory names
        dirs = []
        for line in stdout.decode().strip().split("\n"):
            line = line.strip().rstrip("/")
            if line:
                # Check for invalid characters (like leading/trailing spaces)
                trimmed = line.strip()
                if trimmed != line:
                    dirs.append({
                        "name": line,
                        "valid": False,
                        "trimmed_name": trimmed,
                        "reason": "Name has leading/trailing spaces"
                    })
                else:
                    dirs.append({"name": line, "valid": True})

        return {"ok": True, "dirs": dirs}

    except FileNotFoundError:
        return {"ok": False, "error": "rclone not installed", "dirs": []}
    except Exception as e:
        logger.error(f"Failed to list remote dirs: {e}")
        return {"ok": False, "error": str(e), "dirs": []}


@router.get("/api/local/list-dirs")
async def list_local_dirs():
    """
    List directories in ~/Pictures for local storage selection.

    LAN-only endpoint, no JWT auth required.
    """
    pictures_path = Path.home() / "Pictures"
    base_path = str(pictures_path)

    if not pictures_path.exists():
        return {"ok": True, "dirs": [], "base_path": base_path}

    try:
        dirs = [
            {"name": d.name, "path": str(d)}
            for d in sorted(pictures_path.iterdir())
            if d.is_dir() and not d.name.startswith(".")
        ]
        return {"ok": True, "dirs": dirs, "base_path": base_path}
    except Exception as e:
        logger.error(f"Failed to list local dirs: {e}")
        return {"ok": False, "error": str(e), "dirs": [], "base_path": base_path}


class FrameLiveRequest(BaseModel):
    """Request to switch active source."""
    target_dir: str


@router.post("/api/frame-live")
async def frame_live(request: FrameLiveRequest):
    """
    Switch to a different photo source and trigger sync.

    LAN-only endpoint, no JWT auth required.
    """
    # Find source by path
    sources = source_manager.list_sources()
    target_source = None
    for source in sources:
        if source.local_path == request.target_dir:
            target_source = source
            break

    if not target_source:
        return {"ok": False, "error": "Source not found for path"}

    target_path = Path(request.target_dir)
    if not target_path.exists():
        target_path.mkdir(parents=True, exist_ok=True)

    try:
        # Switch display folder
        success = await display_service.switch_folder(target_path)
        if not success:
            return {"ok": False, "error": "Failed to switch folder"}

        # Update config
        config_manager.set("display.current_source", target_source.id)
        reload_settings()  # Clear cached settings

        # Trigger sync if remote configured
        sync_triggered = False
        if target_source.rclone_remote and not sync_service._is_syncing:
            asyncio.create_task(
                sync_service.sync_source(
                    source_id=target_source.id,
                    local_path=target_path,
                    rclone_remote=target_source.rclone_remote,
                )
            )
            sync_triggered = True

        logger.info(f"Switched to source '{target_source.id}' via dashboard")
        return {"ok": True, "sync_triggered": sync_triggered}

    except Exception as e:
        logger.error(f"Failed to switch source: {e}")
        return {"ok": False, "error": str(e)}


@router.post("/api/config/test-remote")
async def test_remote_connection(request: dict):
    """
    Test rclone remote connection.

    LAN-only endpoint, no JWT auth required.
    """
    remote = request.get("remote", "")
    if not remote:
        return {"ok": False, "error": "No remote specified"}

    try:
        proc = await asyncio.create_subprocess_exec(
            "rclone", "lsf", remote, "--max-depth", "1",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode == 0:
            # Count files/dirs
            lines = [l for l in stdout.decode().strip().split("\n") if l.strip()]
            return {"ok": True, "file_count": len(lines)}
        else:
            error_msg = stderr.decode().strip() or "Connection failed"
            return {"ok": False, "error": error_msg}

    except FileNotFoundError:
        return {"ok": False, "error": "rclone not installed"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


class SaveSettingsRequest(BaseModel):
    """Request to save frame settings."""
    frame_name: str
    rotation_interval: int
    sync_interval: int
    log_level: str


@router.post("/api/settings")
async def save_settings_api(request: SaveSettingsRequest):
    """
    Save frame settings from the dashboard.

    LAN-only endpoint, no JWT auth required.
    Writes to picframe's configuration.yaml and restarts if needed.
    """
    try:
        # Read current picframe config
        if PICFRAME_CONFIG_PATH.exists():
            with open(PICFRAME_CONFIG_PATH) as f:
                picframe_config = yaml.safe_load(f) or {}
        else:
            logger.error(f"Picframe config not found: {PICFRAME_CONFIG_PATH}")
            return {"ok": False, "error": "Picframe config file not found"}

        # Check if rotation interval is changing
        current_delay = picframe_config.get("model", {}).get("time_delay", 30)
        rotation_changed = float(current_delay) != float(request.rotation_interval)

        # Update picframe config
        if "model" not in picframe_config:
            picframe_config["model"] = {}
        picframe_config["model"]["time_delay"] = float(request.rotation_interval)
        picframe_config["model"]["log_level"] = request.log_level.upper()

        # Write picframe config
        with open(PICFRAME_CONFIG_PATH, "w") as f:
            yaml.safe_dump(picframe_config, f, default_flow_style=False)

        logger.info(f"Picframe config saved: time_delay={request.rotation_interval}")

        # Also save to v4 dashboard config
        config_manager.set("frame.name", request.frame_name)
        config_manager.set("display.rotation_interval", request.rotation_interval)
        config_manager.set("sync.interval", request.sync_interval)
        config_manager.set("logging.level", request.log_level)

        # Restart picframe if rotation interval changed
        restarted = False
        if rotation_changed:
            logger.info("Rotation interval changed, restarting picframe service")
            restarted = await systemd_service.restart("picframe")
            if restarted:
                logger.info("Picframe service restarted successfully")
            else:
                logger.warning("Failed to restart picframe service")

        return {"ok": True, "restarted": restarted}
    except Exception as e:
        logger.error(f"Failed to save settings: {e}")
        return {"ok": False, "error": str(e)}

"""
PicFrame 4.0 - Dashboard Routes.

Server-rendered pages for the web dashboard.
Uses Jinja2 templates.
"""

import asyncio
import io
import logging
import os
import re
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import yaml
from fastapi import APIRouter, Query, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, field_validator

from src.config.settings import get_settings, reload_settings
from src.config.manager import config_manager
from src.services.source_manager import source_manager
from src.services.sync_service import sync_service
from src.services.systemd_service import systemd_service, update_sync_timer, VALID_SYNC_INTERVALS
from src.services.display_service import display_service
from src.services.update_service import check_for_updates, save_check_result, get_local_commit, get_local_version, apply_update, get_current_branch
from src.services.sleep_scheduler import is_sleeping
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
from src.utils.rclone import count_local_files, rclone_list_remotes, _validate_filename_raw
from src.services import photo_tools_service as photo_tools
from src.services import backup_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dashboard"])

# Template directory
TEMPLATE_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# Log files location
LOGS_DIR = Path.home() / ".picframe" / "logs"

# Picframe config file location
PICFRAME_CONFIG_PATH = Path.home() / "picframe_data" / "config" / "configuration.yaml"


def _format_last_checked(iso_str: str | None) -> str:
    """Format an ISO datetime string as a human-friendly string."""
    if not iso_str:
        return "Never"
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%-d %b %Y at %-I:%M %p")
    except Exception:
        return iso_str


PICFRAME_APP_CONFIG = Path.home() / ".picframe" / "config.yaml"


def _is_koofr_configured() -> bool:
    """Return True if cloud sync is configured on this frame.

    Checks three signals in order:
    1. state.yaml has koofr_configured=true (explicit Phase 6 first-run completion)
    2. config.yaml has sync.koofr_user (Koofr credentials saved via dashboard)
    3. Any enabled source already has an rclone_remote (pre-existing sync config)
    """
    try:
        # 1. Explicit Phase 6 state flag
        state_path = Path("/var/lib/picframe/state.yaml")
        if state_path.exists():
            with open(state_path) as f:
                state = yaml.safe_load(f) or {}
            if state.get("koofr_configured"):
                return True

        if not PICFRAME_APP_CONFIG.exists():
            return False

        with open(PICFRAME_APP_CONFIG) as f:
            config = yaml.safe_load(f) or {}

        # 2. Koofr credentials saved via dashboard
        if config.get("sync", {}).get("koofr_user", "").strip():
            return True

        # 3. Any enabled source already has a cloud remote (pre-existing config)
        sources_path = Path.home() / ".picframe" / "sources.yaml"
        if sources_path.exists():
            with open(sources_path) as f:
                sources_data = yaml.safe_load(f) or {}
            for source in sources_data.get("sources", []):
                if source.get("enabled") and source.get("rclone_remote", "").strip():
                    return True

    except Exception:
        pass
    return False


async def _validate_koofr_credentials(user: str, password: str) -> tuple[bool, str]:
    """
    Test Koofr credentials using a temporary rclone config.

    Returns (is_valid, error_message).
    """
    # Obscure the password
    try:
        proc = await asyncio.create_subprocess_exec(
            "rclone", "obscure", password,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)
        if proc.returncode != 0:
            return False, "Failed to process Koofr password."
        obscured = stdout.decode().strip()
    except asyncio.TimeoutError:
        return False, "Credential check timed out."
    except FileNotFoundError:
        return False, "rclone is not installed."

    config_content = (
        "[koofr-test]\n"
        "type = koofr\n"
        f"user = {user}\n"
        f"password = {obscured}\n"
    )

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".conf", delete=False, dir="/tmp"
        ) as f:
            f.write(config_content)
            tmp_path = f.name
        os.chmod(tmp_path, 0o600)

        proc = await asyncio.create_subprocess_exec(
            "rclone", "lsd", "koofr-test:", "--config", tmp_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            await asyncio.wait_for(proc.communicate(), timeout=20)
        except asyncio.TimeoutError:
            proc.kill()
            return False, "Koofr connection timed out. Check your internet connection."

        if proc.returncode == 0:
            logger.info(f"Koofr credentials validated for '{user}'")
            return True, ""
        return False, "Could not connect to Koofr. Check your email and password."

    except Exception as e:
        logger.error(f"Koofr validation error: {e}")
        return False, "Failed to validate Koofr credentials."
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


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


def _get_lan_ip() -> str:
    """Get the LAN IP address of the primary network interface."""
    try:
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception as e:
        logger.warning(f"Failed to get LAN IP: {e}")
    return ""


def _get_wifi_ssid() -> str:
    """Get the currently connected WiFi SSID via nmcli."""
    try:
        import subprocess
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

    # Get update status for Settings tab card
    local_commit = await get_local_commit()
    local_version = await get_local_version()
    update_branch = await get_current_branch()

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
        # Update check card context
        "update_auto_check": settings.updates.auto_check,
        "update_auto_apply": settings.updates.auto_apply,
        "update_frequency": settings.updates.frequency,
        "update_day": settings.updates.day,
        "update_check_time": settings.updates.check_time,
        "update_last_checked": _format_last_checked(settings.updates.last_checked),
        "update_last_result": settings.updates.last_result,
        "update_available_commit": settings.updates.available_commit,
        "update_local_commit": local_commit,
        "update_local_version": local_version,
        "update_branch": update_branch,
        "koofr_configured": _is_koofr_configured(),
        "lan_ip": _get_lan_ip(),
        "wifi_ssid": _get_wifi_ssid(),
        # Sleep mode schedule
        "sleep_enabled": settings.sleep.enabled,
        "sleep_time": settings.sleep.sleep_time,
        "wake_time": settings.sleep.wake_time,
    }
    return templates.TemplateResponse(request, "dashboard.html", context)


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
        url = settings.frame.funnel_url or ""
        if not url:
            ts_ip = _get_tailscale_ip()
            if ts_ip:
                url = f"http://{ts_ip}:8000"
        if not url:
            return {"error": "No address available — set funnel_url in config or ensure Tailscale is running"}
        qr_data_url = generate_qr_data_url(
            url=url,
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
                local_path=Path(source.local_path).expanduser(),
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

    source_path = Path(source.local_path).expanduser()
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

    # Calculate next sync time from last sync + interval
    next_sync = None
    if last_sync:
        try:
            settings = get_settings()
            last_dt = datetime.strptime(last_sync, "%Y-%m-%d %H:%M:%S")
            next_dt = last_dt + timedelta(seconds=settings.sync.interval)
            next_sync = next_dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

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
        "next_sync": next_sync,
        "last_restart": last_restart,
        "koofr_configured": _is_koofr_configured(),
        "is_sleeping": is_sleeping(),
    }


@router.post("/dashboard/koofr-setup")
async def koofr_setup(request: Request):
    """
    Save and validate Koofr credentials. Step 2 of first-run setup.

    Validates credentials live via rclone before writing anything.
    On success, saves to ~/.picframe/config.yaml and returns 200.
    """
    data = await request.json()
    koofr_user = str(data.get("koofr_user", "")).strip()
    koofr_pass = str(data.get("koofr_pass", "")).strip()

    import re as _re
    EMAIL_RE = _re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    if not EMAIL_RE.match(koofr_user):
        return {"success": False, "error": "Invalid Koofr email address."}
    if not koofr_pass:
        return {"success": False, "error": "Koofr password is required."}

    valid, error_msg = await _validate_koofr_credentials(koofr_user, koofr_pass)
    if not valid:
        return {"success": False, "error": error_msg}

    # Write credentials to config.yaml
    try:
        config: dict = {}
        if PICFRAME_APP_CONFIG.exists():
            with open(PICFRAME_APP_CONFIG) as f:
                config = yaml.safe_load(f) or {}
        config.setdefault("sync", {}).update({
            "koofr_user": koofr_user,
            "koofr_pass": koofr_pass,
        })
        tmp = PICFRAME_APP_CONFIG.with_suffix(".tmp")
        with open(tmp, "w") as f:
            yaml.safe_dump(config, f, default_flow_style=False)
        tmp.chmod(0o600)
        tmp.rename(PICFRAME_APP_CONFIG)
        logger.info(f"Koofr credentials saved for '{koofr_user}'")
    except Exception as e:
        logger.error(f"Failed to save Koofr config: {e}")
        return {"success": False, "error": "Failed to save credentials. Please try again."}

    # Mark koofr_configured in state.yaml so watchdog won't regenerate setup image
    _set_koofr_configured()

    # Restore original no_pictures.jpg if setup image was generated by watchdog
    _restore_setup_image()

    return {"success": True}


def _set_koofr_configured() -> None:
    """Set koofr_configured=true in /var/lib/picframe/state.yaml."""
    state_path = Path("/var/lib/picframe/state.yaml")
    try:
        state: dict = {}
        if state_path.exists():
            with open(state_path) as f:
                state = yaml.safe_load(f) or {}
        state["koofr_configured"] = True
        tmp = state_path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            yaml.safe_dump(state, f, default_flow_style=False)
        tmp.replace(state_path)
        logger.info("state.yaml: koofr_configured set to true")
    except Exception as e:
        logger.warning(f"Could not update state.yaml koofr_configured: {e}")


def _restore_setup_image() -> None:
    """Restore the original no_pictures.jpg from backup if present."""
    no_pictures = Path.home() / "picframe_data" / "data" / "no_pictures.jpg"
    backup = Path.home() / "picframe_data" / "data" / "no_pictures.setup-backup"
    if backup.exists():
        import shutil
        try:
            shutil.copy2(str(backup), str(no_pictures))
            backup.unlink()
            logger.info("Restored original no_pictures.jpg after Koofr setup")
        except Exception as e:
            logger.warning(f"Could not restore no_pictures.jpg: {e}")


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

    @field_validator("sync_interval")
    @classmethod
    def must_be_valid_interval(cls, v: int) -> int:
        if v not in VALID_SYNC_INTERVALS:
            raise ValueError(f"sync_interval must be one of {sorted(VALID_SYNC_INTERVALS)}")
        return v


class SaveUpdateScheduleRequest(BaseModel):
    """Request to save update schedule settings."""
    auto_check: bool
    auto_apply: bool
    frequency: str
    day: int
    check_time: str


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
        settings = get_settings()
        current_sync_interval = settings.sync.interval
        config_manager.set("frame.name", request.frame_name)
        config_manager.set("display.rotation_interval", request.rotation_interval)
        config_manager.set("sync.interval", request.sync_interval)
        config_manager.set("logging.level", request.log_level)
        reload_settings()

        # Restart picframe if rotation interval changed
        restarted = False
        if rotation_changed:
            logger.info("Rotation interval changed, restarting picframe service")
            restarted = await systemd_service.restart("picframe")
            if restarted:
                logger.info("Picframe service restarted successfully")
            else:
                logger.warning("Failed to restart picframe service")

        # Update systemd sync timer if interval changed
        if request.sync_interval != current_sync_interval:
            await update_sync_timer(request.sync_interval)

        return {"ok": True, "restarted": restarted}
    except Exception as e:
        logger.error(f"Failed to save settings: {e}")
        return {"ok": False, "error": str(e)}


@router.get("/api/updates/settings")
async def get_update_settings():
    """
    Get current update configuration and last check result.

    LAN-only endpoint, no JWT auth required.
    """
    settings = get_settings()
    local_commit = await get_local_commit()
    local_version = await get_local_version()
    branch = await get_current_branch()
    return {
        "auto_check": settings.updates.auto_check,
        "auto_apply": settings.updates.auto_apply,
        "frequency": settings.updates.frequency,
        "day": settings.updates.day,
        "check_time": settings.updates.check_time,
        "last_checked": settings.updates.last_checked,
        "last_result": settings.updates.last_result,
        "local_version": local_version,
        "local_commit": local_commit,
        "branch": branch,
    }


@router.post("/api/updates/check")
async def check_for_updates_api():
    """
    Trigger an immediate update check.

    LAN-only endpoint, no JWT auth required.
    """
    result = await check_for_updates()
    save_check_result(result)

    return {
        "ok": result.get("error") is None,
        "up_to_date": result.get("up_to_date"),
        "local_commit": result.get("local_commit"),
        "remote_commit": result.get("remote_commit"),
        "local_version": result.get("local_version"),
        "remote_version": result.get("remote_version"),
        "checked_at": result.get("checked_at"),
        "branch": result.get("branch"),
        "error": result.get("error"),
    }


@router.post("/api/updates/schedule")
async def save_update_schedule(request: SaveUpdateScheduleRequest):
    """
    Save update schedule configuration.

    LAN-only endpoint, no JWT auth required.
    """
    # Validate frequency
    if request.frequency not in ("daily", "weekly", "monthly"):
        return {"ok": False, "error": "frequency must be 'daily', 'weekly', or 'monthly'"}

    # Validate day (only relevant for non-daily)
    if request.frequency == "monthly" and not (1 <= request.day <= 28):
        return {"ok": False, "error": "day must be 1-28 for monthly frequency"}
    if request.frequency == "weekly" and not (0 <= request.day <= 6):
        return {"ok": False, "error": "day must be 0-6 for weekly frequency"}

    # Validate check_time
    if not re.match(r"^\d{2}:\d{2}$", request.check_time):
        return {"ok": False, "error": "check_time must be HH:MM format"}
    hour, minute = int(request.check_time[:2]), int(request.check_time[3:])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return {"ok": False, "error": "check_time has invalid hour or minute"}

    try:
        config_manager.set("updates.auto_check", request.auto_check)
        config_manager.set("updates.auto_apply", request.auto_apply)
        config_manager.set("updates.frequency", request.frequency)
        config_manager.set("updates.day", request.day)
        config_manager.set("updates.check_time", request.check_time)
        reload_settings()

        logger.info(
            f"Update schedule saved: auto_check={request.auto_check}, auto_apply={request.auto_apply}, "
            f"frequency={request.frequency}, day={request.day}, time={request.check_time}"
        )
        return {"ok": True}
    except Exception as e:
        logger.error(f"Failed to save update schedule: {e}")
        return {"ok": False, "error": str(e)}


class SleepScheduleRequest(BaseModel):
    """Request to save sleep mode schedule."""
    enabled: bool
    sleep_time: str
    wake_time: str

    @field_validator("sleep_time", "wake_time")
    @classmethod
    def must_be_hhmm(cls, v: str) -> str:
        import re as _re
        if not _re.match(r"^([01]\d|2[0-3]):[0-5]\d$", v):
            raise ValueError("Time must be in HH:MM format (00:00–23:59)")
        return v


@router.post("/api/sleep-schedule")
async def save_sleep_schedule(request: SleepScheduleRequest):
    """Save sleep mode schedule from the dashboard."""
    try:
        config_manager.set("sleep.enabled", request.enabled)
        config_manager.set("sleep.sleep_time", request.sleep_time)
        config_manager.set("sleep.wake_time", request.wake_time)
        reload_settings()
        logger.info(
            f"Sleep schedule saved: enabled={request.enabled}, "
            f"sleep={request.sleep_time}, wake={request.wake_time}"
        )
        return {"ok": True}
    except Exception as e:
        logger.error(f"Failed to save sleep schedule: {e}")
        return {"ok": False, "error": str(e)}


# =============================================================================
# LAN-only Thumbnail API (no JWT auth - protected by LAN middleware)
# Serves thumbnails for the Tools tab. Accepts filenames with special chars
# (Google Photos IDs, spaces) that the JWT thumbnail endpoint rejects.
# =============================================================================

THUMB_CACHE_DIR = Path("/tmp/pfthumb")
THUMB_SIZE = (128, 128)


@router.get("/api/thumbnail/{source_id}")
async def dashboard_thumbnail(source_id: str, filename: str = Query(...)):
    """Return a JPEG thumbnail for any photo in a source. LAN-only, no JWT."""
    if not _validate_filename_raw(filename):
        return Response(status_code=400)
    source = source_manager.get_source(source_id)
    if not source:
        return Response(status_code=404)
    local_file = Path(source.local_path).expanduser() / filename
    if not local_file.is_file():
        return Response(status_code=404)
    try:
        local_file.resolve().relative_to(Path(source.local_path).expanduser().resolve())
    except ValueError:
        return Response(status_code=400)

    mtime = int(local_file.stat().st_mtime)
    cache_path = THUMB_CACHE_DIR / f"dash_{source_id}_{filename}_{mtime}.jpg"
    if cache_path.exists():
        return Response(content=cache_path.read_bytes(), media_type="image/jpeg")

    try:
        from PIL import Image  # noqa: PLC0415

        # Register HEIC opener if available
        try:
            import pillow_heif  # noqa: PLC0415
            pillow_heif.register_heif_opener()
        except ImportError:
            pass

        THUMB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with Image.open(local_file) as img:
            img = img.convert("RGB")
            img.thumbnail(THUMB_SIZE, Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=70, optimize=True)
            jpeg_bytes = buf.getvalue()

        tmp = cache_path.with_suffix(".tmp")
        tmp.write_bytes(jpeg_bytes)
        tmp.rename(cache_path)
        return Response(content=jpeg_bytes, media_type="image/jpeg")

    except Exception as exc:
        logger.warning(f"Thumbnail failed for {filename}: {exc}")
        return Response(status_code=500)


# =============================================================================
# LAN-only Photo Tools API (no JWT auth - protected by LAN middleware)
# Same service layer as /api/v1/sources/{id}/tools/* — no duplication.
# =============================================================================


@router.get("/api/tools/{source_id}/scan/files")
async def tools_scan_files(source_id: str):
    """List all files in a source with EXIF dates. LAN-only, no JWT."""
    try:
        result = photo_tools.scan_files(source_id)
        return {"ok": True, **result.model_dump()}
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        logger.error(f"tools scan_files error: {exc}")
        return {"ok": False, "error": str(exc)}


@router.get("/api/tools/{source_id}/scan/filenames")
async def tools_scan_filenames(source_id: str):
    """Scan for filename issues. LAN-only, no JWT."""
    try:
        result = photo_tools.scan_filenames(source_id)
        return {"ok": True, **result.model_dump()}
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        logger.error(f"tools scan_filenames error: {exc}")
        return {"ok": False, "error": str(exc)}


@router.post("/api/tools/{source_id}/apply/filenames")
async def tools_apply_filenames(source_id: str, request: dict):
    """Apply filename fixes. LAN-only, no JWT."""
    fixes_raw = request.get("fixes", [])
    try:
        fixes = [photo_tools.FilenameFix(**f) for f in fixes_raw]
        result = await photo_tools.apply_filenames(source_id, fixes)
        return {"ok": True, **result.model_dump()}
    except (ValueError, TypeError) as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        logger.error(f"tools apply_filenames error: {exc}")
        return {"ok": False, "error": str(exc)}


@router.get("/api/tools/{source_id}/scan/duplicates")
async def tools_scan_duplicates(source_id: str):
    """Scan for exact duplicates. LAN-only, no JWT."""
    try:
        result = photo_tools.scan_duplicates(source_id)
        return {"ok": True, **result.model_dump()}
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        logger.error(f"tools scan_duplicates error: {exc}")
        return {"ok": False, "error": str(exc)}


@router.post("/api/tools/{source_id}/apply/duplicates")
async def tools_apply_duplicates(source_id: str, request: dict):
    """Delete selected duplicates. LAN-only, no JWT."""
    to_delete = request.get("to_delete", [])
    if not to_delete:
        return {"ok": False, "error": "to_delete list is empty"}
    try:
        result = await photo_tools.apply_duplicates(source_id, to_delete)
        return {"ok": True, **result.model_dump()}
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        logger.error(f"tools apply_duplicates error: {exc}")
        return {"ok": False, "error": str(exc)}


@router.get("/api/tools/{source_id}/scan/videos")
async def tools_scan_videos(source_id: str):
    """Scan for video files. LAN-only, no JWT."""
    try:
        result = photo_tools.scan_videos(source_id)
        return {"ok": True, **result.model_dump()}
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        logger.error(f"tools scan_videos error: {exc}")
        return {"ok": False, "error": str(exc)}


@router.post("/api/tools/{source_id}/apply/videos")
async def tools_apply_videos(source_id: str, request: dict):
    """Delete selected video files. LAN-only, no JWT."""
    to_delete = request.get("to_delete", [])
    if not to_delete:
        return {"ok": False, "error": "to_delete list is empty"}
    try:
        result = await photo_tools.apply_videos(source_id, to_delete)
        return {"ok": True, **result.model_dump()}
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        logger.error(f"tools apply_videos error: {exc}")
        return {"ok": False, "error": str(exc)}


@router.post("/api/tools/{source_id}/rename")
async def tools_rename_file(source_id: str, request: dict):
    """Rename a single file by name (cloud-first). LAN-only, no JWT."""
    original = (request.get("original") or "").strip()
    proposed = (request.get("proposed") or "").strip()
    if not original or not proposed:
        return {"ok": False, "error": "original and proposed are required"}
    if not _validate_filename_raw(original) or not _validate_filename_raw(proposed):
        return {"ok": False, "error": "Invalid filename"}
    if original == proposed:
        return {"ok": False, "error": "Original and new name are the same"}
    try:
        result = await photo_tools.rename_file(source_id, original, proposed)
        if result.succeeded:
            return {"ok": True}
        err = result.failed[0]["error"] if result.failed else "Rename failed"
        return {"ok": False, "error": err}
    except (ValueError, TypeError) as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        logger.error(f"tools rename_file error: {exc}")
        return {"ok": False, "error": str(exc)}


class DeleteBackupRequest(BaseModel):
    """Request body for deleting a backup archive."""
    filename: str


@router.get("/api/tools/backup/{source_id}/list")
async def list_source_backups(source_id: str):
    """List existing tar.gz backups for a source. LAN-only, no JWT."""
    source = source_manager.get_source(source_id)
    if not source:
        return {"ok": False, "error": "Source not found"}
    try:
        backups = backup_service.list_backups(source_id)
        return {"ok": True, "backups": backups}
    except Exception as exc:
        logger.error("backup list error: %s", exc)
        return {"ok": False, "error": str(exc)}


@router.post("/api/tools/backup/{source_id}/create")
async def create_source_backup(source_id: str):
    """Create a tar.gz backup of the source's local photos. LAN-only, no JWT."""
    source = source_manager.get_source(source_id)
    if not source:
        return {"ok": False, "error": "Source not found"}
    try:
        result = await backup_service.create_backup(source_id, source.local_path)
        return {"ok": True, **result}
    except Exception as exc:
        logger.error("backup create error: %s", exc)
        return {"ok": False, "error": str(exc)}


@router.post("/api/tools/backup/{source_id}/delete")
async def delete_source_backup(source_id: str, body: DeleteBackupRequest):
    """Delete a backup archive. LAN-only, no JWT."""
    source = source_manager.get_source(source_id)
    if not source:
        return {"ok": False, "error": "Source not found"}
    try:
        backup_service.delete_backup(source_id, body.filename)
        return {"ok": True}
    except (ValueError, FileNotFoundError) as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        logger.error("backup delete error: %s", exc)
        return {"ok": False, "error": str(exc)}


@router.post("/api/updates/apply")
async def apply_update_api():
    """
    Apply available updates by running git pull.

    LAN-only endpoint, no JWT auth required.
    """
    result = await apply_update()

    if result["success"]:
        logger.info("Update applied via dashboard — restarting API")
        async def _restart_after_response():
            await asyncio.sleep(1)
            await systemd_service.restart("picframe-api")
        asyncio.create_task(_restart_after_response())
    else:
        logger.error(f"Update apply failed via dashboard: {result['error']}")

    return {
        "ok": result["success"],
        "output": result.get("output"),
        "error": result.get("error"),
    }

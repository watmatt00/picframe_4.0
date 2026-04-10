"""
PicFrame Setup - WiFi Watchdog.

Monitors WiFi association and manages the needs_setup flag in state.yaml.
Runs as a system-level service (root). Never touches the display process.

WiFi check: association only (iw dev wlan0 link).
Never pings 8.8.8.8 — internet down != WiFi down.
"""

import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HOSTAPD_CONF_PATH = Path("/etc/hostapd/picframe-hostapd.conf")
AP_PORTAL_IP = "192.168.4.1"
ISSUE_PATH = Path("/etc/issue")
ISSUE_BACKUP_PATH = Path("/etc/issue.picframe-backup")

# Frame user info — set by systemd service from install.conf
FRAME_USER_HOME = Path(os.environ.get("PICFRAME_USER_HOME", "/home/pi"))
FRAME_USER = os.environ.get("PICFRAME_USER", FRAME_USER_HOME.name)
NO_PICTURES_PATH = FRAME_USER_HOME / "picframe_data" / "data" / "no_pictures.jpg"
NO_PICTURES_BACKUP = FRAME_USER_HOME / "picframe_data" / "data" / "no_pictures.setup-backup"


# Allow running from any working directory
sys.path.insert(0, str(Path(__file__).parent))

from state_manager import state_manager

# Outage threshold before setting needs_setup flag
WIFI_OUTAGE_THRESHOLD_SECONDS = 600  # 10 minutes
POLL_INTERVAL_SECONDS = 30
LOG_FORMAT = "[%(asctime)s] %(levelname)-5s %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt=LOG_DATE_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(Path("/var/log/picframe-watchdog.log")),
    ],
)
logger = logging.getLogger("watchdog")


def _get_lan_ip() -> str:
    """Return the IPv4 address of wlan0 or eth0, or empty string if not available."""
    for iface in ("wlan0", "eth0"):
        try:
            result = subprocess.run(
                ["ip", "-4", "addr", "show", iface],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("inet "):
                    return line.split()[1].split("/")[0]
        except Exception:
            pass
    return ""


def _load_font(size: int):
    """Load a TrueType font from common system paths, fall back to PIL default."""
    from PIL import ImageFont
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/piboto/Piboto-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def generate_setup_image(frame_name: str) -> None:
    """
    Generate a first-run Step 2 instruction image and write it to
    ~/picframe_data/data/no_pictures.jpg so Pi3D displays it when there
    are no photos yet.

    Backs up the original file first. Restored by restore_no_pictures()
    once Koofr is configured.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        logger.warning("Pillow not installed — skipping setup image generation")
        return

    if not NO_PICTURES_PATH.parent.exists():
        logger.warning(f"no_pictures.jpg parent dir not found: {NO_PICTURES_PATH.parent}")
        return

    # Backup original if not already backed up
    if not NO_PICTURES_BACKUP.exists() and NO_PICTURES_PATH.exists():
        import shutil
        shutil.copy2(str(NO_PICTURES_PATH), str(NO_PICTURES_BACKUP))
        logger.info(f"Backed up original no_pictures.jpg to {NO_PICTURES_BACKUP.name}")

    # Primary URL is always mDNS — IP shown as fallback footnote (matches success.html)
    primary_url = f"http://{frame_name}.local:8000"
    lan_ip = _get_lan_ip()
    fallback_note = f"If that doesn't work, try:  http://{lan_ip}:8000" if lan_ip else ""

    # Build image: 1920x1080 dark background
    W, H = 1920, 1080
    img = Image.new("RGB", (W, H), color=(18, 18, 28))
    draw = ImageDraw.Draw(img)

    yellow = (255, 200, 0)
    white = (235, 235, 235)
    green = (100, 220, 100)
    gray = (140, 140, 140)

    font_title = _load_font(72)
    font_body = _load_font(48)
    font_url = _load_font(56)
    font_small = _load_font(32)

    cx = W // 2
    y = 150

    draw.text((cx, y), "Step 2 of 2 — Finish Setup", font=font_title, fill=yellow, anchor="mm")
    y += 90
    draw.line([(cx - 500, y), (cx + 500, y)], fill=(60, 60, 80), width=2)
    y += 55

    draw.text((cx, y), "WiFi connected!  Now finish setup from your phone or computer:", font=font_body, fill=white, anchor="mm")
    y += 85

    draw.text((cx, y), "1.  Rejoin your home WiFi network", font=font_body, fill=white, anchor="mm")
    y += 70
    draw.text((cx, y), "2.  Open a browser and go to:", font=font_body, fill=white, anchor="mm")
    y += 75

    # URL box — primary mDNS address
    pad = 28
    url_bbox = draw.textbbox((cx, y), primary_url, font=font_url, anchor="mm")
    draw.rounded_rectangle(
        [url_bbox[0] - pad, url_bbox[1] - pad // 2, url_bbox[2] + pad, url_bbox[3] + pad // 2],
        radius=12, fill=(10, 30, 10), outline=green, width=2,
    )
    draw.text((cx, y), primary_url, font=font_url, fill=green, anchor="mm")
    y += 85

    draw.text((cx, y), "3.  Enter your Koofr email and password in the banner", font=font_body, fill=white, anchor="mm")
    y += 80

    draw.line([(cx - 500, y), (cx + 500, y)], fill=(60, 60, 80), width=2)
    y += 38

    # Footnote: IP fallback + frame name
    if fallback_note:
        draw.text((cx, y), fallback_note, font=font_small, fill=gray, anchor="mm")
        y += 44
    draw.text((cx, y), f"Frame: {frame_name}", font=font_small, fill=gray, anchor="mm")

    try:
        img.save(str(NO_PICTURES_PATH), "JPEG", quality=92)
        subprocess.run(["chown", f"{FRAME_USER}:{FRAME_USER}", str(NO_PICTURES_PATH)], check=False)
        logger.info(f"Setup instruction image written to {NO_PICTURES_PATH} (primary: {primary_url})")
    except Exception as e:
        logger.error(f"Failed to write setup image: {e}")


def restore_no_pictures() -> None:
    """Restore the original no_pictures.jpg from the setup backup, if present."""
    if NO_PICTURES_BACKUP.exists():
        import shutil
        try:
            shutil.copy2(str(NO_PICTURES_BACKUP), str(NO_PICTURES_PATH))
            NO_PICTURES_BACKUP.unlink()
            subprocess.run(["chown", f"{FRAME_USER}:{FRAME_USER}", str(NO_PICTURES_PATH)], check=False)
            logger.info("Restored original no_pictures.jpg")
        except Exception as e:
            logger.error(f"Failed to restore no_pictures.jpg: {e}")


def is_wifi_associated() -> bool:
    """
    Check if wlan0 is associated with an access point.

    Uses 'iw dev wlan0 link' and looks for 'Connected to'.
    Never tests internet reachability.

    Returns:
        True if associated, False otherwise.
    """
    try:
        result = subprocess.run(
            ["iw", "dev", "wlan0", "link"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return "Connected to" in result.stdout
    except subprocess.TimeoutExpired:
        logger.warning("iw command timed out")
        return False
    except FileNotFoundError:
        logger.error("iw not found — is wireless-tools installed?")
        return False
    except Exception as e:
        logger.error(f"WiFi check failed: {e}")
        return False


def _get_hostapd_value(key: str, default: str) -> str:
    """Read a single key=value from the hostapd config file."""
    try:
        for line in HOSTAPD_CONF_PATH.read_text().splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return default


def _update_hostapd_ssid(frame_name: str) -> None:
    """Rewrite the hostapd SSID line to match the current frame name."""
    try:
        content = HOSTAPD_CONF_PATH.read_text()
        new_ssid = f"PicFrame-{frame_name}"
        lines = [
            f"ssid={new_ssid}" if line.startswith("ssid=") else line
            for line in content.splitlines()
        ]
        HOSTAPD_CONF_PATH.write_text("\n".join(lines) + "\n")
        logger.info(f"hostapd SSID updated to '{new_ssid}'")
    except Exception as e:
        logger.warning(f"Could not update hostapd SSID: {e}")


def _write_setup_issue(frame_name: str) -> None:
    """
    Write WiFi setup instructions to /etc/issue so they appear above
    the login prompt. Terminal stays fully usable — user can log in
    normally and the setup info is visible in the header.

    Backs up the original /etc/issue first; restored by _restore_issue().
    """
    ap_ssid = f"PicFrame-{frame_name}"
    ap_password = _get_hostapd_value("wpa_passphrase", "picframe")

    W = 50
    sep = "+" + "-" * W + "+"

    def row(text: str = "") -> str:
        return f"| {text:<{W - 1}}|"

    lines = [
        sep,
        row(f"  PicFrame \u2014 WiFi Setup Mode"),
        sep,
        row(),
        row("  Connect to this WiFi network:"),
        row(),
        row(f"  Network  :  {ap_ssid}"),
        row(f"  Password :  {ap_password}"),
        row(),
        row(f"  Open a browser to: http://{AP_PORTAL_IP}"),
        row(),
        row("  Enter your home WiFi credentials"),
        row("  in the page that opens."),
        row(),
        sep,
        "",
    ]

    content = "\n".join(lines) + "\n"
    try:
        if not ISSUE_BACKUP_PATH.exists():
            ISSUE_PATH.rename(ISSUE_BACKUP_PATH)
        ISSUE_PATH.write_text(content)
        subprocess.run(["systemctl", "restart", "getty@tty1"], check=False)
        logger.info(f"Setup info written to /etc/issue (SSID: {ap_ssid})")
    except Exception as e:
        logger.warning(f"Could not write setup info to /etc/issue: {e}")


def _restore_issue() -> None:
    """Restore /etc/issue from backup if a setup-mode backup exists."""
    try:
        if ISSUE_BACKUP_PATH.exists():
            ISSUE_BACKUP_PATH.rename(ISSUE_PATH)
            subprocess.run(["systemctl", "restart", "getty@tty1"], check=False)
            logger.info("Restored /etc/issue from backup")
    except Exception as e:
        logger.warning(f"Could not restore /etc/issue: {e}")


def start_setup_mode() -> None:
    """
    Enter setup mode: stop the photo display, write dnsmasq config,
    start BLE and AP services, and show setup instructions on the console.
    """
    logger.info("Starting setup mode")

    state = state_manager.read()
    frame_name = state.get("frame_name", "picframe")

    # Keep hostapd SSID in sync with current frame name
    _update_hostapd_ssid(frame_name)

    # Stop the photo display — picframe runs as a user service under 'matt'
    # Use -M matt@ to reach the user session bus from root
    subprocess.run(
        ["systemctl", "--user", "-M", "matt@", "stop", "picframe"],
        check=False,
    )
    logger.info("Stopped picframe display service")

    # Write dnsmasq config for DNS hijack (any URL → 192.168.4.1)
    dnsmasq_conf = (
        "interface=wlan0\n"
        "dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h\n"
        "address=/#/192.168.4.1\n"
    )
    try:
        Path("/tmp/picframe-dnsmasq.conf").write_text(dnsmasq_conf)
    except Exception as e:
        logger.error(f"Failed to write dnsmasq config: {e}")

    # Start BLE + AP simultaneously
    try:
        subprocess.run(
            ["systemctl", "start", "picframe-ble-setup", "picframe-ap-setup"],
            check=True,
        )
        logger.info("Setup mode services started (BLE + AP)")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to start setup mode services: {e}")

    # Show instructions in the login header (/etc/issue)
    _write_setup_issue(frame_name)


def stop_setup_mode() -> None:
    """Stop BLE and AP setup services."""
    logger.info("Stopping setup mode services")
    subprocess.run(
        ["systemctl", "stop", "picframe-ble-setup", "picframe-ap-setup"],
        check=False,
    )


def run_monitoring_loop(in_setup_mode: bool = False) -> None:
    """
    Main watchdog loop. Polls WiFi every 30 seconds.

    On loss: starts 10-min countdown, sets needs_setup flag at expiry.
    On recovery: clears needs_setup flag.
    Display is never touched.

    In setup mode: wlan0 is controlled by hostapd (AP mode) and wpa_supplicant
    may reconnect in the background. Do not poll WiFi — the portal/BLE handler
    writes new credentials and reboots when the user is done. Just idle.

    Args:
        in_setup_mode: True if setup mode services were started this boot.
    """
    wifi_down_since: float | None = None
    flag_already_set = False

    logger.info("Watchdog monitoring loop started")

    while True:
        # In setup mode, wlan0 is owned by hostapd — don't poll WiFi.
        # The portal handles rebooting when the user submits credentials.
        if in_setup_mode:
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        associated = is_wifi_associated()

        if associated:
            state_manager.mark_wifi_connected()

            if wifi_down_since is not None:
                duration = time.monotonic() - wifi_down_since
                logger.info(f"WiFi recovered after {duration:.0f}s")
                wifi_down_since = None
                flag_already_set = False

            # Normal recovery: clear flag if it was set during this outage
            if state_manager.needs_setup():
                state_manager.clear_needs_setup()
                logger.info("needs_setup flag cleared after WiFi recovery")

        else:
            if wifi_down_since is None:
                wifi_down_since = time.monotonic()
                logger.warning("WiFi association lost — starting 10-min countdown")

            outage_duration = time.monotonic() - wifi_down_since

            if outage_duration >= WIFI_OUTAGE_THRESHOLD_SECONDS and not flag_already_set:
                state_manager.mark_needs_setup("extended_outage")
                flag_already_set = True
                logger.warning(
                    f"WiFi down {outage_duration:.0f}s — needs_setup flag set. "
                    "Will enter setup mode on next reboot."
                )
            elif not flag_already_set:
                remaining = WIFI_OUTAGE_THRESHOLD_SECONDS - outage_duration
                logger.info(f"WiFi down {outage_duration:.0f}s — {remaining:.0f}s until flag set")

        time.sleep(POLL_INTERVAL_SECONDS)


def main() -> None:
    """Entry point for the watchdog service."""
    logger.info("PicFrame WiFi Watchdog starting")

    # Restore /etc/issue if a previous setup run left the custom version
    _restore_issue()

    # Ensure state file exists
    state_manager.initialize()

    state = state_manager.read()
    provisioned = state.get("provisioned", False)
    needs_setup = state.get("needs_setup", False)
    reason = state.get("setup_mode_reason", "none")

    logger.info(
        f"Boot state: provisioned={provisioned}, needs_setup={needs_setup}, "
        f"reason={reason}, state_file={state_manager._path}"
    )

    # Boot-time check: enter setup mode immediately if flagged
    if not provisioned:
        logger.info("Frame not provisioned — entering setup mode")
        state_manager.mark_needs_setup("unprovisioned")
        start_setup_mode()
        run_monitoring_loop(in_setup_mode=True)
        return

    if needs_setup:
        reason = state.get("setup_mode_reason", "unknown")
        logger.info(f"needs_setup=true (reason: {reason}) — entering setup mode")
        start_setup_mode()
        run_monitoring_loop(in_setup_mode=True)
        return

    # Show setup instruction image if Koofr hasn't been configured yet
    frame_name = state.get("frame_name", "picframe")
    koofr_configured = state.get("koofr_configured", False)
    if not koofr_configured:
        logger.info("koofr_configured=false — generating setup instruction image")
        generate_setup_image(frame_name)
    else:
        # Ensure setup image is cleaned up if it was left from a previous run
        restore_no_pictures()

    # Normal operation: check WiFi on boot, then monitor
    if is_wifi_associated():
        state_manager.mark_wifi_connected()
        logger.info("WiFi associated at boot — last_wifi_connected updated")
    else:
        logger.warning("WiFi not associated at boot — starting 10-min countdown")

    run_monitoring_loop()


if __name__ == "__main__":
    main()

"""
PicFrame Setup - WiFi Watchdog.

Monitors WiFi association and manages the needs_setup flag in state.yaml.
Runs as a system-level service (root). Never touches the display process.

WiFi check: association only (iw dev wlan0 link).
Never pings 8.8.8.8 — internet down != WiFi down.
"""

import logging
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HOSTAPD_CONF_PATH = Path("/etc/hostapd/picframe-hostapd.conf")
AP_PORTAL_IP = "192.168.4.1"
ISSUE_PATH = Path("/etc/issue")
ISSUE_BACKUP_PATH = Path("/etc/issue.picframe-backup")


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

    # Normal operation: check WiFi on boot, then monitor
    if is_wifi_associated():
        state_manager.mark_wifi_connected()
        logger.info("WiFi associated at boot — last_wifi_connected updated")
    else:
        logger.warning("WiFi not associated at boot — starting 10-min countdown")

    run_monitoring_loop()


if __name__ == "__main__":
    main()

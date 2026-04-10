"""
PicFrame Setup - AP Captive Portal.

Flask web app running on port 80 during setup mode.
Step 1 of 2: collects frame name + WiFi credentials only.
Step 2 (Koofr setup) happens via the dashboard after WiFi is connected.

Runs alongside hostapd (hotspot) and dnsmasq (DNS hijack).
"""

import logging
import os
import re
import subprocess
import sys
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for
import yaml

# Allow running from parent directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from state_manager import state_manager

LOG_FORMAT = "[%(asctime)s] %(levelname)-5s %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
logger = logging.getLogger("portal")

# Portal runs as root (port 80). Use the env var set by the systemd service
# (written by install_setup.sh) to find the frame user's home directory.
# Never use Path.home() here — that resolves to /root when running as root.
PICFRAME_USER_HOME = Path(os.environ.get("PICFRAME_USER_HOME", "/home/pi"))
PICFRAME_CONFIG_PATH = PICFRAME_USER_HOME / ".picframe" / "config.yaml"

# Frame user — needed to chown files written by root back to the correct owner
PICFRAME_USER = os.environ.get("PICFRAME_USER", PICFRAME_USER_HOME.name)

# Input validation patterns
SSID_RE = re.compile(r"^[\w\s\-\.]{1,32}$")
PASSWORD_RE = re.compile(r"^(.{8,63})?$")  # empty = open network, or 8–63 chars
FRAME_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")

app = Flask(__name__, template_folder="templates", static_folder="static")


# ── Captive portal detection redirects ──────────────────────────────────────

CAPTIVE_DETECT_PATHS = [
    "/generate_204",
    "/hotspot-detect.html",
    "/library/test/success.html",
    "/ncsi.txt",
    "/connecttest.txt",
    "/redirect",
    "/canonical.html",
]

for _path in CAPTIVE_DETECT_PATHS:
    app.add_url_rule(
        _path,
        endpoint=f"captive_{_path.strip('/').replace('.', '_').replace('/', '_')}",
        view_func=lambda: redirect(url_for("index")),
    )


# ── Main routes ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the appropriate config form based on provisioning state."""
    state = state_manager.read()
    is_first_run = not state.get("provisioned", False)
    frame_name = state.get("frame_name", "picframe")
    if is_first_run:
        return render_template("index.html", frame_name=frame_name)
    return render_template("reconfigure.html", frame_name=frame_name)


@app.route("/skip")
def skip():
    """
    Skip WiFi setup and return to gallery.

    Clears the needs_setup flag and reboots to normal operation.
    Only available when the frame is already provisioned (not first-run).
    """
    state = state_manager.read()
    if not state.get("provisioned", False):
        # Can't skip on first run — WiFi must be configured
        return redirect(url_for("index"))

    logger.info("User skipped WiFi setup — clearing flag and rebooting to gallery")
    state_manager.clear_needs_setup()
    subprocess.run(["systemctl", "stop", "picframe-ble-setup"], check=False)
    subprocess.Popen(["sh", "-c", "sleep 2 && reboot"])
    return render_template("skip.html")


@app.route("/save", methods=["POST"])
def save():
    """Validate input, write config files, reboot."""
    state = state_manager.read()
    is_first_run = not state.get("provisioned", False)

    errors = []

    # ── WiFi credentials (required always) ──────────────────────────────────
    ssid = request.form.get("ssid", "").strip()
    wifi_password = request.form.get("wifi_password", "").strip()

    if not SSID_RE.match(ssid):
        errors.append("Invalid WiFi network name (1–32 characters, letters/numbers/spaces/hyphens).")
    if wifi_password and not PASSWORD_RE.match(wifi_password):
        errors.append("WiFi password must be 8–63 characters (or leave blank for an open network).")

    # ── First-run: frame name only (Koofr configured in Step 2 via dashboard) ──
    frame_name = ""

    if is_first_run:
        frame_name = request.form.get("frame_name", "").strip()
        if not FRAME_NAME_RE.match(frame_name):
            errors.append("Frame name must be 1–32 characters (letters, numbers, hyphens, underscores).")

    if errors:
        template = "index.html" if is_first_run else "reconfigure.html"
        return render_template(
            template,
            errors=errors,
            frame_name=frame_name or state.get("frame_name", "picframe"),
        )

    # ── Configure WiFi via NetworkManager ────────────────────────────────────
    try:
        _write_wifi_credentials(ssid, wifi_password)
    except Exception as e:
        logger.error(f"Failed to configure WiFi: {e}")
        template = "index.html" if is_first_run else "reconfigure.html"
        return render_template(
            template,
            errors=["Failed to save WiFi configuration. Please try again."],
            frame_name=frame_name or state.get("frame_name", "picframe"),
        )

    # ── First-run: write frame name, mark provisioned ────────────────────────
    if is_first_run:
        try:
            _write_picframe_config(frame_name)
            state_manager.set("frame_name", frame_name)
            state_manager.set("provisioned", True)
            # koofr_configured stays False — Step 2 happens on the dashboard
        except Exception as e:
            logger.error(f"Failed to write picframe config: {e}")
            return render_template(
                "index.html",
                errors=["Failed to save frame configuration. Please try again."],
                frame_name=frame_name,
            )

    # ── Clear setup flag and reboot ───────────────────────────────────────────
    state_manager.clear_needs_setup()
    logger.info(f"Configuration saved for SSID '{ssid}'. Rebooting...")

    # Stop the BLE service if running
    subprocess.run(["systemctl", "stop", "picframe-ble-setup"], check=False)

    # Reboot after a brief delay so the response can be sent
    subprocess.Popen(["sh", "-c", "sleep 2 && reboot"])

    return render_template("success.html")


# ── Helper functions ─────────────────────────────────────────────────────────

def _write_wifi_credentials(ssid: str, password: str) -> None:
    """
    Configure WiFi credentials using NetworkManager (nmcli).

    Deletes any existing 'picframe-wifi' connection and creates a new one
    with autoconnect enabled so it persists across reboots.

    Args:
        ssid: WiFi network name.
        password: WiFi password (WPA2-PSK), or empty string for open networks.
    """
    # Remove old picframe-wifi connection if it exists
    subprocess.run(
        ["nmcli", "con", "delete", "picframe-wifi"],
        capture_output=True, check=False,
    )

    # Create connection
    subprocess.run(
        ["nmcli", "con", "add", "type", "wifi", "ifname", "wlan0",
         "con-name", "picframe-wifi", "ssid", ssid],
        capture_output=True, text=True, check=True,
    )

    if password:
        # WPA2-PSK secured network
        subprocess.run(
            ["nmcli", "con", "modify", "picframe-wifi",
             "wifi-sec.key-mgmt", "wpa-psk",
             "wifi-sec.psk", password,
             "connection.autoconnect", "yes",
             "connection.autoconnect-priority", "10"],
            capture_output=True, text=True, check=True,
        )
        logger.info(f"NetworkManager 'picframe-wifi' configured (WPA2) for SSID '{ssid}'")
    else:
        # Open network — no security settings
        subprocess.run(
            ["nmcli", "con", "modify", "picframe-wifi",
             "connection.autoconnect", "yes",
             "connection.autoconnect-priority", "10"],
            capture_output=True, text=True, check=True,
        )
        logger.info(f"NetworkManager 'picframe-wifi' configured (open) for SSID '{ssid}'")


def _write_picframe_config(frame_name: str) -> None:
    """
    Write frame name to ~/.picframe/config.yaml. Merges into existing config.

    Koofr credentials are NOT written here — that is Step 2, handled by
    the dashboard after WiFi is connected.

    Args:
        frame_name: Human-readable frame name.
    """
    config: dict = {}
    if PICFRAME_CONFIG_PATH.exists():
        with open(PICFRAME_CONFIG_PATH) as f:
            config = yaml.safe_load(f) or {}

    config.setdefault("frame", {})["name"] = frame_name

    tmp = PICFRAME_CONFIG_PATH.with_suffix(".tmp")
    try:
        PICFRAME_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w") as f:
            yaml.safe_dump(config, f, default_flow_style=False)
        tmp.chmod(0o600)
        tmp.rename(PICFRAME_CONFIG_PATH)
        # Portal runs as root — restore ownership to the frame user so the API can read it
        subprocess.run(["chown", f"{PICFRAME_USER}:{PICFRAME_USER}", str(PICFRAME_CONFIG_PATH)], check=False)
        logger.info(f"picframe config updated (frame_name='{frame_name}')")
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise


if __name__ == "__main__":
    # Must run as root (port 80 requires root)
    if os.geteuid() != 0:
        sys.exit("ERROR: captive portal must run as root (port 80 requires root)")
    app.run(host="0.0.0.0", port=80, debug=False)

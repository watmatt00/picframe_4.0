"""
PicFrame Setup - AP Captive Portal.

Flask web app running on port 80 during setup mode.
Collects WiFi credentials (and Koofr creds on first run),
writes wpa_supplicant.conf atomically, then reboots.

Runs alongside hostapd (hotspot) and dnsmasq (DNS hijack).
"""

import logging
import os
import re
import subprocess
import sys
import tempfile
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

# Input validation patterns
SSID_RE = re.compile(r"^[\w\s\-\.]{1,32}$")
PASSWORD_RE = re.compile(r"^(.{8,63})?$")  # empty = open network, or 8–63 chars
FRAME_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

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

    # ── First-run extra fields ───────────────────────────────────────────────
    frame_name = ""
    koofr_user = ""
    koofr_pass = ""

    if is_first_run:
        frame_name = request.form.get("frame_name", "").strip()
        koofr_user = request.form.get("koofr_user", "").strip()
        koofr_pass = request.form.get("koofr_pass", "").strip()

        if not FRAME_NAME_RE.match(frame_name):
            errors.append("Frame name must be 1–32 characters (letters, numbers, hyphens, underscores).")
        if not EMAIL_RE.match(koofr_user):
            errors.append("Koofr email address is invalid.")
        if not koofr_pass:
            errors.append("Koofr password is required.")

    if errors:
        template = "index.html" if is_first_run else "reconfigure.html"
        return render_template(
            template,
            errors=errors,
            frame_name=frame_name or state.get("frame_name", "picframe"),
        )

    # ── First-run: validate Koofr credentials before writing anything ─────────
    if is_first_run:
        valid, error_msg = _validate_koofr_credentials(koofr_user, koofr_pass)
        if not valid:
            return render_template(
                "index.html",
                errors=[error_msg],
                frame_name=frame_name,
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

    # ── First-run: write frame name and Koofr creds ──────────────────────────
    if is_first_run:
        try:
            _write_picframe_config(frame_name, koofr_user, koofr_pass)
            state_manager.set("frame_name", frame_name)
            state_manager.set("provisioned", True)
            state_manager.set("koofr_configured", True)
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

def _validate_koofr_credentials(user: str, password: str) -> tuple[bool, str]:
    """
    Test Koofr credentials by running a quick rclone lsd with a temp config.

    Creates a throwaway rclone config, runs 'rclone lsd koofr-test:' with a
    20-second timeout, then deletes the temp file. Never touches the main
    rclone config.

    Args:
        user: Koofr account email.
        password: Koofr account password (plain text).

    Returns:
        Tuple of (is_valid, error_message).
    """
    # Step 1: obscure the password for the rclone config format
    try:
        result = subprocess.run(
            ["rclone", "obscure", password],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            logger.error(f"rclone obscure failed: {result.stderr}")
            return False, "Failed to process Koofr password."
        obscured = result.stdout.strip()
    except FileNotFoundError:
        logger.error("rclone not found — cannot validate Koofr credentials")
        return False, "rclone is not installed. Cannot validate credentials."
    except subprocess.TimeoutExpired:
        return False, "Credential check timed out."

    # Step 2: write a throwaway rclone config
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

        # Step 3: test the credentials — list root folders, 20s timeout
        result = subprocess.run(
            ["rclone", "lsd", "koofr-test:", "--config", tmp_path],
            capture_output=True, text=True, timeout=20,
        )
        if result.returncode == 0:
            logger.info(f"Koofr credentials validated for '{user}'")
            return True, ""
        logger.warning(f"Koofr validation failed for '{user}': {result.stderr.strip()}")
        return False, "Could not connect to Koofr. Check your email and password."

    except subprocess.TimeoutExpired:
        return False, "Koofr connection timed out. Check your internet connection."
    except Exception as e:
        logger.error(f"Koofr validation error: {e}")
        return False, "Failed to validate Koofr credentials."
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


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


def _write_picframe_config(frame_name: str, koofr_user: str, koofr_pass: str) -> None:
    """
    Write frame name and Koofr credentials to ~/.picframe/config.yaml.

    Merges into existing config if present.

    Args:
        frame_name: Human-readable frame name.
        koofr_user: Koofr account email.
        koofr_pass: Koofr account password.
    """
    config: dict = {}
    if PICFRAME_CONFIG_PATH.exists():
        with open(PICFRAME_CONFIG_PATH) as f:
            config = yaml.safe_load(f) or {}

    config.setdefault("frame", {})["name"] = frame_name

    # Koofr credentials stored under sync section
    config.setdefault("sync", {}).update({
        "koofr_user": koofr_user,
        "koofr_pass": koofr_pass,
    })

    tmp = PICFRAME_CONFIG_PATH.with_suffix(".tmp")
    try:
        PICFRAME_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w") as f:
            yaml.safe_dump(config, f, default_flow_style=False)
        tmp.chmod(0o600)
        tmp.rename(PICFRAME_CONFIG_PATH)
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

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

WPA_SUPPLICANT_PATH = Path("/etc/wpa_supplicant/wpa_supplicant.conf")
PICFRAME_CONFIG_PATH = Path.home() / ".picframe" / "config.yaml"

# Input validation patterns
SSID_RE = re.compile(r"^[\w\s\-\.]{1,32}$")
PASSWORD_RE = re.compile(r"^.{8,63}$")
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
    if not PASSWORD_RE.match(wifi_password):
        errors.append("WiFi password must be 8–63 characters.")

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

    # ── Write wpa_supplicant.conf atomically ─────────────────────────────────
    try:
        _write_wpa_supplicant(ssid, wifi_password)
    except Exception as e:
        logger.error(f"Failed to write wpa_supplicant.conf: {e}")
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

def _write_wpa_supplicant(ssid: str, password: str) -> None:
    """
    Write /etc/wpa_supplicant/wpa_supplicant.conf atomically.

    Uses wpa_passphrase to properly hash the PSK rather than storing plaintext.

    Args:
        ssid: WiFi network name.
        password: WiFi password.
    """
    # Generate the network block using wpa_passphrase
    result = subprocess.run(
        ["wpa_passphrase", ssid, password],
        capture_output=True,
        text=True,
        check=True,
    )
    # Remove plaintext password comment line from output
    network_block = "\n".join(
        line for line in result.stdout.splitlines()
        if not line.strip().startswith("#psk=")
    )

    content = (
        "ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\n"
        "update_config=1\n"
        "country=US\n\n"
        f"{network_block}\n"
    )

    # Atomic write: write to temp then rename
    tmp = WPA_SUPPLICANT_PATH.with_suffix(".tmp")
    try:
        tmp.write_text(content)
        tmp.chmod(0o600)
        tmp.rename(WPA_SUPPLICANT_PATH)
        logger.info(f"wpa_supplicant.conf written for SSID '{ssid}'")
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise


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

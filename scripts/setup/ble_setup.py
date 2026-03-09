"""
PicFrame Setup - BLE GATT Peripheral Server.

Advertises the frame as a BLE peripheral during setup mode.
The iOS app writes WiFi credentials via the GATT characteristic.

Service UUID:        4fafc201-1fb5-459e-8fcc-c5c9c331914b
Characteristic UUID: beb5483e-36e1-4688-b7f5-ea07361b26a8

Requires: pip3 install bless
Runs as root (system service).
"""

import asyncio
import json
import logging
import re
import subprocess
import sys
from pathlib import Path

from bless import BlessServer, BlessGATTCharacteristic, GATTCharacteristicProperties, GATTAttributePermissions

sys.path.insert(0, str(Path(__file__).parent))
from state_manager import state_manager

LOG_FORMAT = "[%(asctime)s] %(levelname)-5s %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt=LOG_DATE_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(Path.home() / ".picframe" / "logs" / "ble_setup.log"),
    ],
)
logger = logging.getLogger("ble_setup")

# PicFrame BLE service and characteristic UUIDs
SERVICE_UUID = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
CHAR_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"

WPA_SUPPLICANT_PATH = Path("/etc/wpa_supplicant/wpa_supplicant.conf")

# Input validation
SSID_RE = re.compile(r"^[\w\s\-\.]{1,32}$")
PASSWORD_RE = re.compile(r"^.{8,63}$")

# Shutdown event — set when credentials are received and applied
shutdown_event = asyncio.Event()


def validate_credentials(ssid: str, password: str) -> tuple[bool, str]:
    """
    Validate WiFi credentials received via BLE.

    Args:
        ssid: WiFi network name.
        password: WiFi password.

    Returns:
        Tuple of (is_valid, error_message).
    """
    if not SSID_RE.match(ssid):
        return False, f"Invalid SSID: '{ssid}'"
    if not PASSWORD_RE.match(password):
        return False, "Password must be 8-63 characters"
    return True, ""


def write_wpa_supplicant(ssid: str, password: str) -> None:
    """
    Write /etc/wpa_supplicant/wpa_supplicant.conf using wpa_passphrase.

    Args:
        ssid: WiFi network name.
        password: WiFi password (plain text — hashed by wpa_passphrase).

    Raises:
        subprocess.CalledProcessError: If wpa_passphrase fails.
        OSError: If file write fails.
    """
    result = subprocess.run(
        ["wpa_passphrase", ssid, password],
        capture_output=True,
        text=True,
        check=True,
    )
    # Strip plaintext password comment
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


def on_characteristic_write(
    characteristic: BlessGATTCharacteristic,
    value: bytearray,
    **kwargs,
) -> None:
    """
    Handle a write to the WiFi credentials characteristic.

    Expected JSON payload: {"ssid": "...", "password": "..."}

    Args:
        characteristic: The GATT characteristic that was written.
        value: Raw bytes written by the central (iOS app).
    """
    try:
        payload = json.loads(value.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error(f"BLE: invalid JSON payload: {e}")
        return

    ssid = payload.get("ssid", "")
    password = payload.get("password", "")

    valid, error = validate_credentials(ssid, password)
    if not valid:
        logger.error(f"BLE: credential validation failed: {error}")
        return

    logger.info(f"BLE: received credentials for SSID '{ssid}'")

    try:
        write_wpa_supplicant(ssid, password)
        state_manager.clear_needs_setup()
        logger.info("BLE: WiFi configured. Stopping AP service and rebooting...")
    except Exception as e:
        logger.error(f"BLE: failed to apply credentials: {e}")
        return

    # Signal the event loop to shut down and reboot
    asyncio.get_event_loop().call_soon_threadsafe(shutdown_event.set)


async def run_ble_server() -> None:
    """
    Start the GATT server and advertise until credentials are received.
    """
    state = state_manager.read()
    frame_name = state.get("frame_name", "picframe")
    device_name = f"PicFrame-{frame_name}"

    logger.info(f"Starting BLE GATT server as '{device_name}'")

    server = BlessServer(name=device_name)
    server.read_request_func = lambda char, **kw: char.value
    server.write_request_func = on_characteristic_write

    await server.add_new_service(SERVICE_UUID)
    await server.add_new_characteristic(
        SERVICE_UUID,
        CHAR_UUID,
        GATTCharacteristicProperties.write,
        None,
        GATTAttributePermissions.writeable,
    )

    await server.start()
    logger.info(f"BLE advertising as '{device_name}' (service {SERVICE_UUID})")

    # Wait until credentials are received and applied
    await shutdown_event.wait()

    await server.stop()
    logger.info("BLE server stopped")

    # Stop the AP service if it's running, then reboot
    subprocess.run(["systemctl", "stop", "picframe-ap-setup"], check=False)
    subprocess.run(["reboot"], check=False)


def main() -> None:
    """Entry point for the BLE setup service."""
    logger.info("PicFrame BLE Setup Service starting")
    asyncio.run(run_ble_server())


if __name__ == "__main__":
    main()

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
import time
from pathlib import Path

from bless import BlessServer, BlessGATTCharacteristic, GATTCharacteristicProperties, GATTAttributePermissions

sys.path.insert(0, str(Path(__file__).parent))
from state_manager import state_manager
from wifi_config import write_wifi_credentials

LOG_FORMAT = "[%(asctime)s] %(levelname)-5s %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_log_handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
try:
    _log_handlers.append(logging.FileHandler(Path("/var/log/picframe-ble-setup.log")))
except OSError:
    pass  # Not running as root (e.g. tests) — journal/stdout only

logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt=LOG_DATE_FORMAT,
    handlers=_log_handlers,
)
logger = logging.getLogger("ble_setup")

# PicFrame BLE service and characteristic UUIDs
SERVICE_UUID = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
CHAR_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"

RFKILL_SYSFS = Path("/sys/class/rfkill")

# Input validation
SSID_RE = re.compile(r"^[\w\s\-\.]{1,32}$")
PASSWORD_RE = re.compile(r"^(.{8,63})?$")  # empty = open network, or 8–63 chars

# Shutdown event — set when credentials are received and applied
shutdown_event = asyncio.Event()


def validate_credentials(ssid: str, password: str) -> tuple[bool, str]:
    """
    Validate WiFi credentials received via BLE.

    Args:
        ssid: WiFi network name.
        password: WiFi password, or empty string for open networks.

    Returns:
        Tuple of (is_valid, error_message).
    """
    if not SSID_RE.match(ssid):
        return False, f"Invalid SSID: '{ssid}'"
    if password and not PASSWORD_RE.match(password):
        return False, "Password must be 8-63 characters (or empty for open networks)"
    return True, ""


def ensure_bluetooth_ready() -> None:
    """
    Unblock Bluetooth via rfkill and power on the adapter.

    Raspberry Pi OS can leave Bluetooth soft-blocked (persisted across reboots
    by systemd-rfkill). A blocked/unpowered adapter makes BlueZ reject
    advertisement registration ("Failed to register advertisement").
    Uses sysfs directly because the rfkill CLI is not installed by default.
    """
    for entry in RFKILL_SYSFS.glob("rfkill*"):
        try:
            if (entry / "type").read_text().strip() != "bluetooth":
                continue
            soft = entry / "soft"
            if soft.read_text().strip() == "1":
                soft.write_text("0")
                name = (entry / "name").read_text().strip()
                logger.info(f"Unblocked Bluetooth rfkill soft block ({name})")
        except OSError as e:
            logger.warning(f"Could not check/unblock {entry.name}: {e}")

    # Adapter may take a moment to come up after unblocking
    output = ""
    for _ in range(5):
        try:
            result = subprocess.run(
                ["bluetoothctl", "power", "on"],
                capture_output=True, text=True, timeout=10,
            )
            output = (result.stdout + result.stderr).strip()
            if "succeeded" in output:
                logger.info("Bluetooth adapter powered on")
                return
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            output = str(e)
        time.sleep(1)
    logger.warning(f"Could not power on Bluetooth adapter: {output}")


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
        write_wifi_credentials(ssid, password)
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

    try:
        await server.start()
    except Exception as e:
        # Return normally (exit status 0) so systemd's Restart=on-failure does
        # not crash-loop. WiFi setup remains available via the captive portal.
        logger.error(
            f"BLE setup unavailable — could not start advertising: {e}. "
            "WiFi setup is still available via the captive portal."
        )
        return
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
    ensure_bluetooth_ready()
    asyncio.run(run_ble_server())


if __name__ == "__main__":
    main()

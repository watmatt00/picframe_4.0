"""
PicFrame Setup - Shared WiFi configuration helper.

Writes WiFi credentials as a NetworkManager connection profile. Used by both
the captive portal (ap_portal/portal.py) and the BLE setup service
(ble_setup.py) so the two setup paths configure WiFi identically.
"""

import logging
import subprocess

logger = logging.getLogger("wifi_config")

CONNECTION_NAME = "picframe-wifi"


def write_wifi_credentials(ssid: str, password: str) -> None:
    """
    Configure WiFi credentials using NetworkManager (nmcli).

    Deletes any existing 'picframe-wifi' connection and creates a new one
    with autoconnect enabled so it persists across reboots. The profile is
    marked hidden so networks that don't broadcast their SSID still connect
    (NetworkManager probes for the SSID directly; visible networks are
    unaffected).

    Callers must validate ssid/password before calling.

    Args:
        ssid: WiFi network name.
        password: WiFi password (WPA2-PSK), or empty string for open networks.

    Raises:
        subprocess.CalledProcessError: If nmcli fails to create the profile.
    """
    # Remove old picframe-wifi connection if it exists
    subprocess.run(
        ["nmcli", "con", "delete", CONNECTION_NAME],
        capture_output=True, check=False,
    )

    cmd = [
        "nmcli", "con", "add", "type", "wifi", "ifname", "wlan0",
        "con-name", CONNECTION_NAME, "ssid", ssid,
        "802-11-wireless.hidden", "yes",
        "connection.autoconnect", "yes",
        "connection.autoconnect-priority", "10",
    ]
    if password:
        cmd += ["wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", password]

    subprocess.run(cmd, capture_output=True, text=True, check=True)

    net_type = "WPA2" if password else "open"
    logger.info(f"NetworkManager '{CONNECTION_NAME}' configured ({net_type}) for SSID '{ssid}'")

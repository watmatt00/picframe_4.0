#!/bin/bash
# PicFrame Phase 6 Setup Installer
# Installs WiFi recovery, setup mode (BLE + AP), and picframe-config tool.
#
# Run as root:  sudo bash scripts/setup/install_setup.sh
# Run from:     ~/picframe_4.0/ (project root)

set -euo pipefail

TIMESTAMP() { date +'%Y-%m-%d %H:%M:%S'; }
LOG()   { echo "[$(TIMESTAMP)] $*"; }
ERROR() { echo "[$(TIMESTAMP)] ERROR: $*" >&2; }
WARN()  { echo "[$(TIMESTAMP)] WARN:  $*"; }

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SETUP_DIR="${PROJECT_DIR}/scripts/setup"
SETUP_VENV="${SETUP_DIR}/venv"
SETUP_PYTHON="${SETUP_VENV}/bin/python3"
SYSTEMD_SRC="${SETUP_DIR}/systemd"
SYSTEMD_DEST="/etc/systemd/system"
HOSTAPD_CONF="/etc/hostapd/picframe-hostapd.conf"
STATE_FILE="/var/lib/picframe/state.yaml"
CONFIG_DIR="${HOME}/.picframe"

# ── Preflight checks ──────────────────────────────────────────────────────────

if [[ $EUID -ne 0 ]]; then
    ERROR "This script must be run as root: sudo bash $0"
    exit 1
fi

# Check for Raspberry Pi
if ! grep -qi "raspberry pi" /proc/device-tree/model 2>/dev/null; then
    WARN "This does not appear to be a Raspberry Pi."
    read -r -p "Continue anyway? [y/N] " confirm
    [[ "$confirm" =~ ^[Yy]$ ]] || exit 1
fi

LOG "Starting PicFrame Phase 6 installation"
LOG "Project directory: ${PROJECT_DIR}"

# ── System packages ───────────────────────────────────────────────────────────

LOG "Installing system packages (hostapd, dnsmasq, bluez, python3-venv, wireless-tools)..."
apt-get update -qq
apt-get install -y hostapd dnsmasq bluez python3-venv python3-full wireless-tools

# Disable hostapd and dnsmasq system-wide services (we manage them ourselves)
systemctl disable --now hostapd 2>/dev/null || true
systemctl disable --now dnsmasq 2>/dev/null || true
LOG "System packages installed"

# ── Python venv for setup scripts ────────────────────────────────────────────

LOG "Creating setup venv at ${SETUP_VENV}..."
python3 -m venv "${SETUP_VENV}"
LOG "Installing Python packages into setup venv (flask, bless, pyyaml, filelock)..."
"${SETUP_VENV}/bin/pip" install --quiet flask bless pyyaml filelock
LOG "Python packages installed"

# ── hostapd config ────────────────────────────────────────────────────────────

LOG "Creating /var/lib/picframe/ state directory..."
mkdir -p /var/lib/picframe
chmod 755 /var/lib/picframe

LOG "Writing hostapd configuration..."

# Read frame name from state.yaml if it exists, else use default
FRAME_NAME="picframe"
if [[ -f "$STATE_FILE" ]]; then
    FRAME_NAME=$(python3 -c "import yaml; d=yaml.safe_load(open('${STATE_FILE}')); print(d.get('frame_name','picframe'))" 2>/dev/null || echo "picframe")
fi

mkdir -p /etc/hostapd

cat > "${HOSTAPD_CONF}" <<EOF
interface=wlan0
driver=nl80211
ssid=PicFrame-${FRAME_NAME}
hw_mode=g
channel=6
wpa=2
wpa_passphrase=picframe
wpa_key_mgmt=WPA-PSK
wpa_pairwise=CCMP
ieee80211n=1
EOF

chmod 600 "${HOSTAPD_CONF}"
LOG "hostapd config written (SSID: PicFrame-${FRAME_NAME}, password: picframe)"

# ── Systemd service files ─────────────────────────────────────────────────────

LOG "Installing systemd service files..."

for service in picframe-watchdog.service picframe-ble-setup.service picframe-ap-setup.service; do
    if [[ ! -f "${SYSTEMD_SRC}/${service}" ]]; then
        ERROR "Service file not found: ${SYSTEMD_SRC}/${service}"
        exit 1
    fi
    cp "${SYSTEMD_SRC}/${service}" "${SYSTEMD_DEST}/${service}"
    LOG "  Installed ${service}"
done

systemctl daemon-reload
LOG "Systemd daemon reloaded"

# Enable watchdog (starts at boot). BLE + AP are started on-demand by watchdog.
systemctl enable picframe-watchdog
LOG "picframe-watchdog enabled (starts at boot)"

# ── picframe-config bash wrapper ──────────────────────────────────────────────

LOG "Installing picframe-config tool..."
cp "${SETUP_DIR}/picframe-config" /usr/local/bin/picframe-config
chmod +x /usr/local/bin/picframe-config
LOG "picframe-config installed to /usr/local/bin/picframe-config"

# ── Initialize state.yaml ─────────────────────────────────────────────────────

if [[ ! -f "$STATE_FILE" ]]; then
    LOG "Initializing state.yaml..."
    sudo -u "${SUDO_USER:-$(logname)}" "${SETUP_PYTHON}" - <<PYEOF
import sys
sys.path.insert(0, '${SETUP_DIR}')
from state_manager import state_manager
state_manager.initialize()
PYEOF
    LOG "state.yaml initialized"
else
    LOG "state.yaml already exists — not overwriting"
fi

# ── Summary ───────────────────────────────────────────────────────────────────

echo ""
echo "============================================="
LOG "Phase 6 installation complete!"
echo "============================================="
echo ""
echo "Services installed:"
echo "  picframe-watchdog  (enabled, starts at boot)"
echo "  picframe-ble-setup (started on demand)"
echo "  picframe-ap-setup  (started on demand)"
echo ""
echo "Tools installed:"
echo "  /usr/local/bin/picframe-config"
echo ""
echo "State file: /var/lib/picframe/state.yaml"
echo ""
echo "Next steps:"
echo "  1. Reboot: sudo reboot"
echo "  2. Watchdog starts automatically"
echo "  3. If WiFi is lost for >10 min, frame enters setup mode on next reboot"
echo ""
echo "To test setup mode manually:"
echo "  picframe-config --force-setup && sudo reboot"
echo ""

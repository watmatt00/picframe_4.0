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

check_service() {
    local service="$1"
    if ! systemctl is-active --quiet "$service" 2>/dev/null; then
        ERROR "$service failed to start — aborting install"
        systemctl status "$service" --no-pager -l || true
        journalctl -u "$service" -n 30 --no-pager || true
        exit 1
    fi
    LOG "  ✓ $service is running"
}

check_cmd() {
    local label="$1"; shift
    if ! "$@" >/dev/null 2>&1; then
        ERROR "$label check failed — aborting install"
        "$@" 2>&1 || true
        exit 1
    fi
    LOG "  ✓ $label"
}

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SETUP_DIR="${PROJECT_DIR}/scripts/setup"
SETUP_VENV="${SETUP_DIR}/venv"
SETUP_PYTHON="${SETUP_VENV}/bin/python3"
SYSTEMD_SRC="${SETUP_DIR}/systemd"
SYSTEMD_DEST="/etc/systemd/system"
HOSTAPD_CONF="/etc/hostapd/picframe-hostapd.conf"
STATE_FILE="/var/lib/picframe/state.yaml"
INSTALL_CONF="/var/lib/picframe/install.conf"

# Determine the invoking user's home directory (script runs as root via sudo)
FRAME_USER="${SUDO_USER:-$(logname 2>/dev/null || echo pi)}"
FRAME_USER_HOME="$(getent passwd "$FRAME_USER" | cut -d: -f6)"
CONFIG_DIR="${FRAME_USER_HOME}/.picframe"

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
"${SETUP_VENV}/bin/pip" install --quiet flask bless pyyaml filelock pillow
LOG "Python packages installed"

# ── hostapd config ────────────────────────────────────────────────────────────

LOG "Creating /var/lib/picframe/ state directory..."
mkdir -p /var/lib/picframe
chmod 755 /var/lib/picframe

# ── Write install.conf ────────────────────────────────────────────────────────

LOG "Writing install.conf (frame user: ${FRAME_USER}, home: ${FRAME_USER_HOME})..."
cat > "${INSTALL_CONF}" <<EOF
# Written by install_setup.sh — do not edit manually
PICFRAME_USER=${FRAME_USER}
PICFRAME_USER_HOME=${FRAME_USER_HOME}
PICFRAME_PROJECT_DIR=${PROJECT_DIR}
PICFRAME_SETUP_PYTHON=${SETUP_PYTHON}
EOF
chmod 644 "${INSTALL_CONF}"
LOG "install.conf written"

LOG "Writing hostapd configuration..."

# Read frame name from state.yaml if it exists, else use default
FRAME_NAME="picframe"
if [[ -f "$STATE_FILE" ]]; then
    FRAME_NAME=$(python3 -c "import yaml; d=yaml.safe_load(open('${STATE_FILE}')); print(d.get('frame_name','picframe'))" 2>/dev/null || echo "picframe")
fi

mkdir -p /etc/hostapd

# ── AP password ───────────────────────────────────────────────────────────────
# Generate a random 8-char password from the Pi serial number for
# reproducibility across reinstalls. Falls back to random bytes if serial
# is unavailable. Displayed automatically in /etc/issue by watchdog.py.
PI_SERIAL=$(grep Serial /proc/cpuinfo 2>/dev/null | awk '{print $3}' | tail -c 9 | tr -d '\n' || true)
if [[ -n "$PI_SERIAL" ]]; then
    AP_PASSWORD=$(echo "${PI_SERIAL}" | tr '[:upper:]' '[:lower:]' | tr -dc 'a-z0-9' | head -c 8)
else
    AP_PASSWORD=$(tr -dc 'a-z0-9' < /dev/urandom | head -c 8)
fi
LOG "AP password: ${AP_PASSWORD}"

cat > "${HOSTAPD_CONF}" <<EOF
interface=wlan0
driver=nl80211
ssid=PicFrame-${FRAME_NAME}
hw_mode=g
channel=6
wpa=2
wpa_passphrase=${AP_PASSWORD}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=CCMP
ieee80211n=1
EOF

chmod 600 "${HOSTAPD_CONF}"
LOG "hostapd config written (SSID: PicFrame-${FRAME_NAME}, password: ${AP_PASSWORD})"

# ── Systemd service files ─────────────────────────────────────────────────────

LOG "Installing systemd service files..."

for service in picframe-watchdog.service picframe-ble-setup.service picframe-ap-setup.service; do
    if [[ ! -f "${SYSTEMD_SRC}/${service}" ]]; then
        ERROR "Service file not found: ${SYSTEMD_SRC}/${service}"
        exit 1
    fi
    # Substitute __PROJECT_DIR__ and __USER_HOME__ placeholders
    sed \
        -e "s|__PROJECT_DIR__|${PROJECT_DIR}|g" \
        -e "s|__USER_HOME__|${FRAME_USER_HOME}|g" \
        -e "s|__FRAME_USER__|${FRAME_USER}|g" \
        "${SYSTEMD_SRC}/${service}" > "${SYSTEMD_DEST}/${service}"
    LOG "  Installed ${service} (PROJECT_DIR=${PROJECT_DIR}, USER_HOME=${FRAME_USER_HOME}, USER=${FRAME_USER})"
done

systemctl daemon-reload
LOG "Systemd daemon reloaded"

# Enable watchdog (starts at boot). BLE + AP are started on-demand by watchdog.
systemctl enable picframe-watchdog
systemctl start picframe-watchdog
LOG "picframe-watchdog enabled and started"
check_service picframe-watchdog

# ── picframe-config bash wrapper ──────────────────────────────────────────────

LOG "Installing picframe-config tool..."
cp "${SETUP_DIR}/picframe-config" /usr/local/bin/picframe-config
chmod +x /usr/local/bin/picframe-config
LOG "picframe-config installed to /usr/local/bin/picframe-config"
check_cmd "picframe-config" picframe-config --show

# ── Initialize state.yaml ─────────────────────────────────────────────────────

if [[ ! -f "$STATE_FILE" ]]; then
    LOG "Initializing state.yaml..."
    "${SETUP_PYTHON}" - <<PYEOF
import sys
sys.path.insert(0, '${SETUP_DIR}')
from state_manager import state_manager
state_manager.initialize()
PYEOF
    LOG "state.yaml initialized at ${STATE_FILE}"
else
    LOG "state.yaml already exists — not overwriting"
fi

# ── Party mode: polkit rule + state.yaml permissions ─────────────────────────
# Allows the API (NoNewPrivileges=true) to manage watchdog units via D-Bus
# and write state.yaml for --clear-setup, without requiring sudo.

LOG "Installing party mode polkit rule..."
mkdir -p /etc/polkit-1/rules.d
cat > /etc/polkit-1/rules.d/50-picframe.rules << 'POLKIT_EOF'
/* Allow sudo-group users to manage PicFrame system services without interaction */
polkit.addRule(function(action, subject) {
    var partyUnits = [
        "picframe-watchdog.service",
        "picframe-ble-setup.service",
        "picframe-ap-setup.service"
    ];
    if (subject.isInGroup("sudo")) {
        if (action.id === "org.freedesktop.systemd1.manage-units") {
            var unit = action.lookup("unit") || "";
            if (partyUnits.indexOf(unit) >= 0) {
                return polkit.Result.YES;
            }
        }
        if (action.id === "org.freedesktop.systemd1.manage-unit-files") {
            return polkit.Result.YES;
        }
    }
});
POLKIT_EOF
LOG "Polkit rule installed: /etc/polkit-1/rules.d/50-picframe.rules"

LOG "Setting state.yaml group permissions for party mode..."
chown root:sudo "${STATE_FILE}"
chmod 664 "${STATE_FILE}"
LOG "state.yaml: sudo group can now write (for party mode --clear-setup)"

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
echo "If running standalone (not via setup_api.sh), reboot when ready:"
echo "  sudo reboot"
echo ""
echo "After reboot: watchdog starts automatically."
echo "If WiFi is lost for >10 min, frame enters setup mode on next reboot."
echo ""
echo "To test setup mode manually:"
echo "  picframe-config --force-setup && sudo reboot"
echo ""

#!/bin/bash
set -euo pipefail

# PicFrame API setup script
# Run after install_picframe.sh to set up rclone, Tailscale, the API, and Phase 6.
# Usage: bash setup_api.sh [--branch=dev|main] [--frame-name=tkframe]

# ── Args ──────────────────────────────────────────────────────────────────────
BRANCH="main"
FRAME_NAME=""
for arg in "$@"; do
    case $arg in
        --branch=*)     BRANCH="${arg#--branch=}" ;;
        --frame-name=*) FRAME_NAME="${arg#--frame-name=}" ;;
    esac
done

REPO_URL="https://github.com/watmatt00/picframe_4.0.git"
PROJECT_DIR="$HOME/picframe_4.0"

log() { echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"; }

# ── Install-time check helpers ────────────────────────────────────────────────
check_service() {
    local service="$1"
    local sc="systemctl --user" jc="journalctl --user -u"
    if ! $sc is-active --quiet "$service" 2>/dev/null; then
        log "ERROR: $service failed to start — aborting install"
        $sc status "$service" --no-pager -l || true
        $jc "$service" -n 30 --no-pager || true
        exit 1
    fi
    log "  ✓ $service is running"
}

check_cmd() {
    local label="$1"; shift
    if ! "$@" >/dev/null 2>&1; then
        log "ERROR: $label check failed — aborting install"
        "$@" 2>&1 || true
        exit 1
    fi
    log "  ✓ $label"
}

check_path() {
    local label="$1" path="$2"
    if [[ ! -e "$path" ]]; then
        log "ERROR: $label not found at $path — aborting install"
        exit 1
    fi
    log "  ✓ $label"
}

check_api_local() {
    log "Waiting for API to be ready..."
    for i in $(seq 1 20); do
        if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
            log "  ✓ API health (local) OK"
            return 0
        fi
        sleep 1
    done
    log "ERROR: API health check timed out after 20s — aborting install"
    systemctl --user status picframe-api.service --no-pager -l || true
    journalctl --user -u picframe-api.service -n 30 --no-pager || true
    exit 1
}

check_funnel() {
    local funnel_url="$1"
    local hostname; hostname=$(echo "$funnel_url" | sed 's|https://||' | sed 's|/.*||')
    # Ensure dig is available to query public DNS (bypasses Tailscale MagicDNS)
    if ! command -v dig &>/dev/null; then
        sudo apt-get install -y -q dnsutils
    fi
    local public_ip; public_ip=$(dig +short "$hostname" @8.8.8.8 2>/dev/null | grep -v '\.$' | head -1 || true)
    if [[ -z "$public_ip" ]]; then
        log "ERROR: Funnel not resolving via public DNS — node may not be approved"
        log "  Check: https://login.tailscale.com/admin/machines"
        exit 1
    fi
    if ! curl -sf --connect-timeout 10 --resolve "$hostname:443:$public_ip" "https://$hostname/health" >/dev/null 2>&1; then
        log "ERROR: Funnel public path unreachable ($public_ip) — check Tailscale admin"
        log "  Check: https://login.tailscale.com/admin/machines"
        exit 1
    fi
    log "  ✓ Funnel reachable via public internet ($public_ip)"
}

# ── Hostname ──────────────────────────────────────────────────────────────────
# Set hostname before Tailscale registers so the Funnel URL uses the right name.
if [[ -z "$FRAME_NAME" ]]; then
    read -rp "Enter frame name (e.g. tkframe, kframe): " FRAME_NAME
fi
CURRENT_HOSTNAME=$(hostname)
if [[ "$CURRENT_HOSTNAME" != "$FRAME_NAME" ]]; then
    log "Setting hostname to $FRAME_NAME (was $CURRENT_HOSTNAME)..."
    sudo hostnamectl set-hostname "$FRAME_NAME"
    log "Hostname updated. SSH prompt will show new name after next login."
fi

# ── Step 1: rclone ────────────────────────────────────────────────────────────
log "--- Step 1: rclone ---"
if command -v rclone &>/dev/null; then
    log "rclone already installed: $(rclone version --no-check-update 2>/dev/null | head -1)"
else
    log "Installing rclone..."
    curl https://rclone.org/install.sh | sudo bash
    log "rclone installed."
fi
check_cmd "rclone installed" rclone version --no-check-update

# ── Step 2: Tailscale + Funnel ────────────────────────────────────────────────
log "--- Step 2: Tailscale ---"
if ! command -v tailscale &>/dev/null; then
    log "Installing Tailscale..."
    curl -fsSL https://tailscale.com/install.sh | sh
fi

if ! tailscale status &>/dev/null; then
    log "Authenticating Tailscale..."
    sudo tailscale up
    echo ""
    echo "============================================="
    echo "  Open the URL above in a browser to"
    echo "  authenticate this device to your tailnet."
    echo "  Press ENTER when done."
    echo "============================================="
    read -r
    tailscale status
fi
log "Tailscale connected."
check_cmd "Tailscale connected" tailscale status

log "Enabling Tailscale Funnel on port 8000..."
FUNNEL_OUTPUT=$(sudo tailscale funnel --bg 8000 2>&1 || true)

# If Funnel requires policy approval for this node, the output contains a URL.
# Display it and wait for the user to approve before continuing.
APPROVAL_URL=$(echo "$FUNNEL_OUTPUT" | grep -o 'https://login.tailscale.com/f/funnel[^ ]*' || true)
if [[ -n "$APPROVAL_URL" ]]; then
    echo ""
    echo "============================================="
    echo "  Tailscale Funnel needs policy approval."
    echo "  Open this URL in a browser to approve:"
    echo ""
    echo "  $APPROVAL_URL"
    echo ""
    echo "  Then press ENTER to continue."
    echo "============================================="
    read -r
    sudo tailscale funnel --bg 8000 || true
fi

FUNNEL_URL=$(tailscale funnel status 2>/dev/null | grep "^https://" | awk '{print $1}' | head -1 || true)
if [[ -z "$FUNNEL_URL" ]]; then
    log "WARNING: Could not detect Funnel URL — you may need to approve Funnel in the Tailscale admin console."
    log "  https://login.tailscale.com/admin/acls"
    read -rp "Enter your Funnel URL manually (e.g. https://tkframe.whale-ayu.ts.net): " FUNNEL_URL
fi
log "Funnel URL: $FUNNEL_URL"
check_funnel "$FUNNEL_URL"

# ── Step 3: Clone picframe_4.0 ────────────────────────────────────────────────
log "--- Step 3: Clone picframe_4.0 ($BRANCH) ---"
if [[ -d "$PROJECT_DIR/.git" ]]; then
    log "Repo already exists, updating to $BRANCH..."
    git -C "$PROJECT_DIR" fetch origin
    git -C "$PROJECT_DIR" checkout "$BRANCH"
    git -C "$PROJECT_DIR" pull
else
    git clone "$REPO_URL" "$PROJECT_DIR"
    git -C "$PROJECT_DIR" checkout "$BRANCH"
fi

log "Creating Python venv..."
python3 -m venv "$PROJECT_DIR/venv"
"$PROJECT_DIR/venv/bin/pip" install --upgrade pip -q
"$PROJECT_DIR/venv/bin/pip" install -e "$PROJECT_DIR" -q
log "picframe_4.0 installed."
check_path "Python venv" "$PROJECT_DIR/venv"

# ── Step 4: Generate and configure config.yaml ────────────────────────────────
log "--- Step 4: Configuration ---"
mkdir -p "$HOME/.picframe"

if [[ ! -f "$HOME/.picframe/config.yaml" ]]; then
    log "Generating default config (starting API briefly)..."
    cd "$PROJECT_DIR"
    "$PROJECT_DIR/venv/bin/python" -m src.main &
    API_PID=$!
    sleep 4
    kill "$API_PID" 2>/dev/null || true
    wait "$API_PID" 2>/dev/null || true
    cd ~
fi

log "Writing frame config: name=$FRAME_NAME funnel=$FUNNEL_URL..."
"$PROJECT_DIR/venv/bin/python3" - <<PYEOF
import yaml, os
path = os.path.expanduser('~/.picframe/config.yaml')
with open(path) as f:
    config = yaml.safe_load(f) or {}
config.setdefault('frame', {})
config['frame']['id'] = '${FRAME_NAME}'
config['frame']['name'] = '${FRAME_NAME}'
config['frame']['funnel_url'] = '${FUNNEL_URL}'
with open(path, 'w') as f:
    yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
print("Config updated.")
PYEOF
check_path "config.yaml" "$HOME/.picframe/config.yaml"

# ── Step 5: Deploy systemd services ───────────────────────────────────────────
log "--- Step 5: Systemd services ---"
mkdir -p "$HOME/.config/systemd/user"
cp "$PROJECT_DIR/systemd/picframe-api.service"   "$HOME/.config/systemd/user/"
cp "$PROJECT_DIR/systemd/picframe-sync.service"  "$HOME/.config/systemd/user/"
cp "$PROJECT_DIR/systemd/picframe-sync.timer"    "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable --now picframe-api.service
systemctl --user enable --now picframe-sync.timer
check_service picframe-api.service
check_api_local
log "API running, sync timer running."

# ── Step 6: Phase 6 WiFi recovery ─────────────────────────────────────────────
log "--- Step 6: Phase 6 WiFi recovery installer ---"
echo ""
echo "============================================="
echo "  NOTE: The next installer will suggest"
echo "  'sudo reboot' — IGNORE IT."
echo "  DO NOT reboot until this script finishes"
echo "  and prints 'PicFrame setup complete!'."
echo "============================================="
echo ""
sudo bash "$PROJECT_DIR/scripts/setup/install_setup.sh"

# ── Step 7: Mark provisioned (WiFi already connected — skip portal) ───────────
log "--- Step 7: Mark provisioned ---"
if ping -c 1 -W 2 8.8.8.8 &>/dev/null; then
    log "WiFi connected — marking frame as provisioned to skip AP portal..."
    sudo "$PROJECT_DIR/venv/bin/python3" - <<PYEOF
import sys
sys.path.insert(0, '${PROJECT_DIR}/scripts/setup')
from state_manager import state_manager
state_manager.set('provisioned', True)
state_manager.set('needs_setup', False)
state_manager.set('frame_name', '${FRAME_NAME}')
print("provisioned=true, needs_setup=false")
PYEOF
else
    log "WARNING: No internet — frame will enter setup mode on next boot."
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "============================================="
echo "  PicFrame setup complete!"
echo "  Frame name : $FRAME_NAME"
echo "  Branch     : $BRANCH"
echo "  Funnel URL : $FUNNEL_URL"
echo "  Dashboard  : http://$(hostname).local:8000"
echo "============================================="
echo ""
echo ""
log "Running post-install verification..."
VERIFY_SCRIPT="$PROJECT_DIR/scripts/setup/verify_install.sh"
if [[ -f "$VERIFY_SCRIPT" ]]; then
    bash "$VERIFY_SCRIPT" --funnel-url="$FUNNEL_URL" || true
else
    echo "Verify:"
    echo "  systemctl --user status picframe-api.service"
    echo "  sudo systemctl status picframe-watchdog"
    echo "  curl http://localhost:8000/health"
    echo "  sudo picframe-config --show"
fi

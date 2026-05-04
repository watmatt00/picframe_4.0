#!/bin/bash
set -euo pipefail

# PicFrame Combined Installer
# Replaces install_picframe.sh + setup_api.sh.
#
# Handles multiple reboots via systemd resume service.
# All interactive prompts occur before the first reboot.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/watmatt00/picframe_4.0/main/scripts/setup/install.sh \
#     -o /tmp/install.sh && sudo bash /tmp/install.sh
#
# Optional flags (set before first run; saved automatically):
#   --ts-authkey=tskey-auth-xxx   Tailscale pre-auth key (avoids browser auth)
#   --branch=dev|main             App branch to clone (default: main)
#   --frame-name=NAME             Frame hostname (prompted if omitted)
#   --with-samba                  Install Samba file sharing
#   --with-mqtt                   Install Mosquitto MQTT broker

# ── Guard ─────────────────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    echo "ERROR: Run with sudo: sudo bash $0" >&2; exit 1
fi

# ── Parse args ────────────────────────────────────────────────────────────────
ACTUAL_USER=${SUDO_USER:-}
WITH_SAMBA="false"
WITH_MQTT="false"
BRANCH="main"
FRAME_NAME=""
TS_AUTHKEY=""
# Remaining state variables — may be overwritten by saved state below
KOOFR_EMAIL=""
KOOFR_PASS=""
FUNNEL_URL=""

for arg in "$@"; do
    case $arg in
        --user=*)        ACTUAL_USER="${arg#--user=}" ;;
        --with-samba)    WITH_SAMBA="true" ;;
        --with-mqtt)     WITH_MQTT="true" ;;
        --branch=*)      BRANCH="${arg#--branch=}" ;;
        --frame-name=*)  FRAME_NAME="${arg#--frame-name=}" ;;
        --ts-authkey=*)  TS_AUTHKEY="${arg#--ts-authkey=}" ;;
    esac
done
ORIG_ARGS="$*"

if [[ -z "$ACTUAL_USER" || "$ACTUAL_USER" == "root" ]]; then
    echo "ERROR: Run via sudo from a normal user account, not directly as root." >&2
    exit 1
fi
ACTUAL_HOME=$(getent passwd "$ACTUAL_USER" | cut -d: -f6)

# ── Load saved state (resumed installs) ───────────────────────────────────────
# Written by save_state() during Phase 0; persists across reboots.
STATE_ENV="$ACTUAL_HOME/install_state.env"
if [[ -f "$STATE_ENV" ]]; then
    # shellcheck disable=SC1090
    source "$STATE_ENV"
fi
# --ts-authkey is not saved in state (single-use); always take it from the flag.
for arg in "$@"; do
    [[ "$arg" == --ts-authkey=* ]] && TS_AUTHKEY="${arg#--ts-authkey=}"
done
# --with-samba/mqtt flags are additive (flag always enables even if state says false).
for arg in "$@"; do
    [[ "$arg" == --with-samba ]] && WITH_SAMBA="true"
    [[ "$arg" == --with-mqtt ]]  && WITH_MQTT="true"
done

# ── Self-persist ──────────────────────────────────────────────────────────────
# Copy script to a stable path so the resume service can re-exec after reboots.
PERSISTENT_SCRIPT="$ACTUAL_HOME/install_picframe_resume.sh"
CURRENT_PATH="$(realpath "$0" 2>/dev/null || echo "$0")"
if [[ "$CURRENT_PATH" != "$PERSISTENT_SCRIPT" ]]; then
    echo "Saving installer to $PERSISTENT_SCRIPT for reboot resume..."
    if [[ -f "$CURRENT_PATH" && "$CURRENT_PATH" != */bash && "$CURRENT_PATH" != /bin/bash ]]; then
        cp "$CURRENT_PATH" "$PERSISTENT_SCRIPT"
    else
        # Fallback: re-download (happens when script is run via pipe).
        # Update this URL to main when promoting install.sh to main branch.
        curl -fsSL "https://raw.githubusercontent.com/watmatt00/picframe_4.0/dev/scripts/setup/install.sh" \
            -o "$PERSISTENT_SCRIPT"
    fi
    chown "$ACTUAL_USER:$ACTUAL_USER" "$PERSISTENT_SCRIPT"
    chmod +x "$PERSISTENT_SCRIPT"
    exec bash "$PERSISTENT_SCRIPT" $ORIG_ARGS
fi

# ── Helpers ───────────────────────────────────────────────────────────────────
PROGRESS_FILE="$ACTUAL_HOME/install_progress.txt"
LOG_FILE="$ACTUAL_HOME/install_log.txt"
RESUME_SERVICE="picframe-install"
REPO_URL="https://github.com/watmatt00/picframe_4.0.git"
PROJECT_DIR="$ACTUAL_HOME/picframe_4.0"

log()       { echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }
save_step() { echo "$1" > "$PROGRESS_FILE"; chown "$ACTUAL_USER:$ACTUAL_USER" "$PROGRESS_FILE"; }
last_step() { [[ -f "$PROGRESS_FILE" ]] && cat "$PROGRESS_FILE" || echo "0"; }
as_user()   { sudo -u "$ACTUAL_USER" "$@"; }

save_state() {
    {
        printf 'FRAME_NAME=%q\n'  "$FRAME_NAME"
        printf 'BRANCH=%q\n'      "$BRANCH"
        printf 'KOOFR_EMAIL=%q\n' "$KOOFR_EMAIL"
        printf 'KOOFR_PASS=%q\n'  "$KOOFR_PASS"
        printf 'WITH_SAMBA=%q\n'  "$WITH_SAMBA"
        printf 'WITH_MQTT=%q\n'   "$WITH_MQTT"
        printf 'FUNNEL_URL=%q\n'  "$FUNNEL_URL"
    } > "$STATE_ENV"
    chown "$ACTUAL_USER:$ACTUAL_USER" "$STATE_ENV"
    chmod 600 "$STATE_ENV"
}

check_internet() {
    log "Checking internet connection..."
    while ! ping -c 1 -W 2 8.8.8.8 &>/dev/null; do
        log "  No connection, retrying in 5s..."
        sleep 5
    done
    log "  ✓ Internet OK"
}

check_user_service() {
    local service="$1"
    local uid; uid=$(id -u "$ACTUAL_USER")
    local xdg="/run/user/$uid"
    log "  Waiting for $service to start..."
    for i in $(seq 1 30); do
        if sudo -u "$ACTUAL_USER" XDG_RUNTIME_DIR="$xdg" systemctl --user is-active --quiet "$service" 2>/dev/null; then
            log "  ✓ $service is running"
            return 0
        fi
        sleep 1
    done
    log "ERROR: $service failed to start after 30s — aborting install"
    sudo -u "$ACTUAL_USER" XDG_RUNTIME_DIR="$xdg" systemctl --user status "$service" --no-pager -l || true
    sudo -u "$ACTUAL_USER" XDG_RUNTIME_DIR="$xdg" journalctl --user -u "$service" -n 30 --no-pager || true
    exit 1
}

user_systemctl() {
    local uid; uid=$(id -u "$ACTUAL_USER")
    sudo -u "$ACTUAL_USER" XDG_RUNTIME_DIR="/run/user/$uid" systemctl --user "$@"
}

wait_for_user_systemd() {
    local uid; uid=$(id -u "$ACTUAL_USER")
    local xdg="/run/user/$uid"
    # Wait for the D-Bus socket, not just the directory — systemctl --user needs
    # the socket to be ready. The directory appears before D-Bus is accepting connections.
    log "  Waiting for user systemd D-Bus socket..."
    for i in $(seq 1 60); do
        if [[ -S "$xdg/bus" ]]; then
            log "  ✓ User systemd ready"
            return 0
        fi
        sleep 1
    done
    log "ERROR: User systemd D-Bus socket not ready after 60s — check loginctl enable-linger"
    exit 1
}

add_resume_service() {
    cat > "/etc/systemd/system/$RESUME_SERVICE.service" <<EOF
[Unit]
Description=Resume picframe install after reboot

[Service]
ExecStart=/bin/bash $PERSISTENT_SCRIPT --user=$ACTUAL_USER
Type=oneshot
RemainAfterExit=true
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable "$RESUME_SERVICE"
}

remove_resume_service() {
    timeout 10 systemctl disable "$RESUME_SERVICE" 2>/dev/null || true
    rm -f "/etc/systemd/system/$RESUME_SERVICE.service"
    timeout 15 systemctl daemon-reload 2>/dev/null || true
}

reboot_and_resume() {
    add_resume_service
    save_step "$1"
    log "Rebooting (will resume at step $1)..."
    reboot; exit 0
}

apply_picframe_defaults() {
    local pconf="$1"
    as_user python3 - "$pconf" <<'PYEOF'
import sys, yaml
p = sys.argv[1]
with open(p) as f:
    cfg = yaml.safe_load(f) or {}
cfg["show_text_tm"] = 0
cfg["show_text"] = ""
cfg["time_delay"] = 20
cfg.setdefault("recent_n", 7)
cfg.setdefault("reshuffle_num", 1)
cfg.setdefault("use_http", True)
with open(p, "w") as f:
    yaml.safe_dump(cfg, f, default_flow_style=False)
print(f"  ✓ Display defaults applied to {p}")
PYEOF
}

check_funnel_dns() {
    local funnel_url="$1"
    local hostname; hostname=$(echo "$funnel_url" | sed 's|https://||' | sed 's|/.*||')
    local public_ip deadline attempt=0
    deadline=$(( $(date +%s) + 90 ))
    log "  Waiting for Funnel DNS to propagate (up to 90s)..."
    while [[ $(date +%s) -lt $deadline ]]; do
        public_ip=$(curl -sf --connect-timeout 5 \
            "https://cloudflare-dns.com/dns-query?name=${hostname}&type=A" \
            -H "accept: application/dns-json" \
            | python3 -c "import json,sys; d=json.load(sys.stdin); print(next((a['data'] for a in d.get('Answer',[]) if a['type']==1),''))" 2>/dev/null || true)
        if [[ -n "$public_ip" ]]; then
            log "  ✓ Funnel DNS resolves ($public_ip)"
            return 0
        fi
        attempt=$(( attempt + 1 ))
        log "  DNS not yet propagated (attempt $attempt) — retrying in 10s..."
        sleep 10
    done
    # Non-fatal: DNS propagation can take several minutes; install continues.
    log "  WARNING: Funnel not resolving via public DNS after 90s — continuing anyway."
    log "  Check: https://login.tailscale.com/admin/machines"
}

# ── Main ──────────────────────────────────────────────────────────────────────
LAST=$(last_step)
log "=== PicFrame install | user=$ACTUAL_USER step=$LAST frame=${FRAME_NAME:-?} branch=${BRANCH:-?} ==="

# ── Phase 0: Preflight interview + pre-reboot setup ──────────────────────────
# All interactive prompts happen here, before any reboot.
if [[ "$LAST" -lt 1 ]]; then

    # Restore TTY stdin — needed when script is piped (curl ... | bash)
    [[ -e /dev/tty ]] && exec < /dev/tty

    echo ""
    echo "============================================="
    echo "  PicFrame Installer"
    echo "  All questions answered before any changes."
    echo "============================================="
    echo ""

    # Frame name / hostname
    CURRENT_HOSTNAME=$(hostname)
    if [[ -z "$FRAME_NAME" ]]; then
        read -rp "Frame name (hostname) [$CURRENT_HOSTNAME]: " FRAME_NAME
        FRAME_NAME="${FRAME_NAME:-$CURRENT_HOSTNAME}"
    fi

    # Branch
    read -rp "Branch [$BRANCH] (dev/main): " _branch
    BRANCH="${_branch:-$BRANCH}"

    # Tailscale pre-auth key
    if [[ -z "$TS_AUTHKEY" ]]; then
        echo ""
        echo "  Tailscale pre-auth key (recommended — eliminates browser auth step)."
        echo "  Generate at: https://login.tailscale.com/admin/settings/keys"
        echo "  Leave blank to authenticate via browser instead."
        read -rp "Tailscale auth key: " TS_AUTHKEY
    fi

    # Koofr credentials
    echo ""
    echo "  Koofr photo sync — use an APP PASSWORD, not your main password."
    echo "  Generate at: https://app.koofr.net → Preferences → App passwords"
    echo ""
    read -rp "Koofr email: " KOOFR_EMAIL
    read -rsp "Koofr app password: " KOOFR_PASS
    echo ""

    # Review + confirm
    echo ""
    echo "--- Review ---"
    echo "  Frame name : $FRAME_NAME"
    echo "  Branch     : $BRANCH"
    if [[ -n "$TS_AUTHKEY" ]]; then
        echo "  Tailscale  : auth key ✓ (${TS_AUTHKEY:0:20}...)"
    else
        echo "  Tailscale  : browser auth (URL will be shown)"
    fi
    echo "  Koofr      : $KOOFR_EMAIL / ********"
    echo "  User       : $ACTUAL_USER  ($ACTUAL_HOME)"
    echo ""
    read -rp "Proceed? [y/N]: " _confirm
    [[ "$_confirm" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }

    # Save state before doing anything (chmod 600 — contains Koofr password)
    save_state

    log "--- Phase 0: Pre-reboot setup ---"
    check_internet

    # Install dev machine SSH key so remote access works immediately after install
    DEV_SSH_KEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHrV8Em76vyRlFrV26Slap2qrJqVN/JWsPfirOh5H4mr watmatt00@gmail.com"
    SSH_AUTH="$ACTUAL_HOME/.ssh/authorized_keys"
    mkdir -p "$ACTUAL_HOME/.ssh"
    chmod 700 "$ACTUAL_HOME/.ssh"
    chown "$ACTUAL_USER:$ACTUAL_USER" "$ACTUAL_HOME/.ssh"
    if ! grep -qF "$DEV_SSH_KEY" "$SSH_AUTH" 2>/dev/null; then
        echo "$DEV_SSH_KEY" >> "$SSH_AUTH"
        chown "$ACTUAL_USER:$ACTUAL_USER" "$SSH_AUTH"
        chmod 600 "$SSH_AUTH"
        log "  ✓ Dev SSH key installed"
    else
        log "  ✓ Dev SSH key already present"
    fi

    # Python 3.11+ check
    if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
        PYTHON_VER=$(python3 -c "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}.{v.micro}')")
        log "  ✓ Python $PYTHON_VER"
    else
        log "ERROR: Python 3.11+ required. Run: sudo apt upgrade python3"; exit 1
    fi

    # Hostname + /etc/hosts
    if [[ "$(hostname)" != "$FRAME_NAME" ]]; then
        log "  Setting hostname to $FRAME_NAME..."
        hostnamectl set-hostname "$FRAME_NAME"
        if grep -q "^127\.0\.1\.1" /etc/hosts; then
            sed -i "s/^127\.0\.1\.1.*/127.0.1.1\t$FRAME_NAME/" /etc/hosts
        else
            printf '127.0.1.1\t%s\n' "$FRAME_NAME" >> /etc/hosts
        fi
        log "  ✓ Hostname → $FRAME_NAME (/etc/hosts updated)"
    fi

    # rclone
    if command -v rclone &>/dev/null; then
        log "  ✓ rclone already installed: $(rclone version 2>/dev/null | head -1)"
    else
        log "  Installing rclone..."
        curl https://rclone.org/install.sh | bash
        log "  ✓ rclone installed"
    fi

    # Tailscale install
    if ! command -v tailscale &>/dev/null; then
        log "  Installing Tailscale..."
        curl -fsSL https://tailscale.com/install.sh | sh
    fi

    # Tailscale auth
    if ! tailscale status &>/dev/null 2>&1; then
        log "  Authenticating Tailscale..."
        _ts_authed=false
        if [[ -n "$TS_AUTHKEY" ]]; then
            if tailscale up --authkey="$TS_AUTHKEY" --hostname="$FRAME_NAME" 2>&1 | tee -a "$LOG_FILE"; then
                log "  ✓ Tailscale authenticated via auth key"
                _ts_authed=true
            else
                log "  WARNING: Auth key rejected — falling back to browser auth"
            fi
        fi
        if [[ "$_ts_authed" == "false" ]]; then
            tailscale up --hostname="$FRAME_NAME"
            echo ""
            echo "============================================="
            echo "  Open the URL above in a browser to"
            echo "  authenticate this device to your tailnet."
            echo "  Press ENTER when done."
            echo "============================================="
            read -r
        fi
    fi
    log "  ✓ Tailscale connected"

    # Funnel — timeout + temp file prevents silent blocking when approval is needed
    log "  Enabling Tailscale Funnel on port 8000..."
    _funnel_tmp=$(mktemp)
    if ! timeout 15 tailscale funnel --bg 8000 > "$_funnel_tmp" 2>&1; then
        _approval_url=$(grep -o 'https://login.tailscale.com/f/funnel[^ ]*' "$_funnel_tmp" || true)
        if [[ -n "$_approval_url" ]]; then
            echo ""
            echo "============================================="
            echo "  Tailscale Funnel needs policy approval."
            echo "  Open this URL in a browser to approve:"
            echo ""
            echo "  $_approval_url"
            echo ""
            echo "  Then press ENTER to continue."
            echo "============================================="
            read -r
            timeout 15 tailscale funnel --bg 8000 || true
        fi
    fi
    rm -f "$_funnel_tmp"

    # Derive Funnel URL (always https://<hostname>.<tailnet>.ts.net — deterministic)
    FUNNEL_URL=$(tailscale funnel status 2>/dev/null | grep "^https://" | awk '{print $1}' | head -1 || true)
    if [[ -z "$FUNNEL_URL" ]]; then
        log "  WARNING: Could not detect Funnel URL automatically."
        read -rp "  Enter your Funnel URL (e.g. https://$FRAME_NAME.whale-ayu.ts.net): " FUNNEL_URL
    fi
    log "  ✓ Funnel URL: $FUNNEL_URL"
    check_funnel_dns "$FUNNEL_URL"

    # Update state with Funnel URL now that we have it
    save_state
    log "  ✓ State saved"

    reboot_and_resume 1
fi

# ── Phase 1: OS update ────────────────────────────────────────────────────────
if [[ "$LAST" -lt 2 ]]; then
    check_internet
    log "--- Phase 1: OS update ---"
    apt-get update && apt-get upgrade -y
    log "  ✓ OS updated"
    reboot_and_resume 2
fi

# ── Phase 2: Console mode (no desktop environment needed) ────────────────────
if [[ "$LAST" -lt 3 ]]; then
    log "--- Phase 2: Console mode ---"
    raspi-config nonint do_boot_behaviour B2
    log "  ✓ Boot target set to console"
    reboot_and_resume 3
fi

# ── Phase 3: Samba (optional — pass --with-samba to enable) ──────────────────
if [[ "$LAST" -lt 4 ]]; then
    if [[ "$WITH_SAMBA" == "true" ]]; then
        check_internet
        log "--- Phase 3: Samba ---"
        apt-get install -y samba
        if ! pdbedit -L | grep -q "^$ACTUAL_USER:"; then
            (printf '%s\n%s\n' "$ACTUAL_USER" "$ACTUAL_USER") | smbpasswd -a "$ACTUAL_USER" -s
        fi
        cat > /etc/samba/smb.conf <<EOF
[global]
security = user
workgroup = WORKGROUP
server role = standalone server
map to guest = never
encrypt passwords = yes
vfs objects = catia fruit streams_xattr
fruit:metadata = stream
fruit:posix_rename = yes
fruit:veto_appledouble = no
fruit:delete_empty_adfiles = yes

[$ACTUAL_USER]
comment = Home Directory
browseable = yes
path = $ACTUAL_HOME
read only = no
create mask = 0775
directory mask = 0775
EOF
        systemctl restart smbd
        log "  ✓ Samba configured (share: \\\\$(hostname)\\$ACTUAL_USER, password: $ACTUAL_USER)"
    else
        log "--- Phase 3: Samba skipped ---"
    fi
    save_step 4
fi

# ── Phase 4: Core packages ────────────────────────────────────────────────────
if [[ "$LAST" -lt 5 ]]; then
    check_internet
    log "--- Phase 4: Core packages ---"
    apt-get install -y git libsdl2-dev xwayland labwc wlr-randr vlc ffmpeg \
        python3-gi python3-gi-cairo gir1.2-gtk-3.0
    if [[ "$WITH_MQTT" == "true" ]]; then
        apt-get install -y mosquitto mosquitto-clients
        log "  ✓ Mosquitto installed"
    fi
    as_user mkdir -p \
        "$ACTUAL_HOME/Pictures" \
        "$ACTUAL_HOME/picframe_data/deleted_pictures"
    log "  ✓ Directories created"
    reboot_and_resume 5
fi

# ── Phase 5: picframe from PyPI + init + display defaults ─────────────────────
if [[ "$LAST" -lt 6 ]]; then
    check_internet
    log "--- Phase 5: picframe pip install ---"
    as_user python3 -m venv "$ACTUAL_HOME/venv_picframe"
    as_user "$ACTUAL_HOME/venv_picframe/bin/pip" install --upgrade pip -q
    as_user "$ACTUAL_HOME/venv_picframe/bin/pip" install picframe
    log "  Running picframe -i to initialize config and data directories..."
    if printf '\n\n\n' | as_user "$ACTUAL_HOME/venv_picframe/bin/picframe" -i "$ACTUAL_HOME/" \
            2>&1 | tee -a "$LOG_FILE"; then
        log "  ✓ picframe initialized"
        PCONF="$ACTUAL_HOME/picframe_data/config/configuration.yaml"
        [[ -f "$PCONF" ]] && apply_picframe_defaults "$PCONF"
    else
        log "ERROR: picframe init failed. Check $LOG_FILE"; exit 1
    fi
    save_step 6
fi

# ── Phase 6: Clone picframe_4.0 repo + venv ───────────────────────────────────
if [[ "$LAST" -lt 7 ]]; then
    check_internet
    log "--- Phase 6: Clone picframe_4.0 ($BRANCH) ---"
    if [[ -d "$PROJECT_DIR/.git" ]]; then
        log "  Repo exists, updating to $BRANCH..."
        as_user git -C "$PROJECT_DIR" fetch origin
        as_user git -C "$PROJECT_DIR" checkout "$BRANCH"
        as_user git -C "$PROJECT_DIR" pull
    else
        as_user git clone "$REPO_URL" "$PROJECT_DIR"
        as_user git -C "$PROJECT_DIR" checkout "$BRANCH"
    fi
    as_user python3 -m venv "$PROJECT_DIR/venv"
    as_user "$PROJECT_DIR/venv/bin/pip" install --upgrade pip -q
    as_user "$PROJECT_DIR/venv/bin/pip" install -e "$PROJECT_DIR" -q
    log "  ✓ picframe_4.0 installed (branch: $BRANCH)"
    save_step 7
fi

# ── Phase 7: Write ~/.picframe/config.yaml ────────────────────────────────────
if [[ "$LAST" -lt 8 ]]; then
    log "--- Phase 7: App config ---"
    as_user mkdir -p "$ACTUAL_HOME/.picframe"
    APP_CONF="$ACTUAL_HOME/.picframe/config.yaml"
    if [[ ! -f "$APP_CONF" ]]; then
        log "  Generating default config (running API briefly)..."
        as_user bash -c "
            cd '$PROJECT_DIR'
            '$PROJECT_DIR/venv/bin/python' -m src.main &
            _pid=\$!
            sleep 5
            kill \$_pid 2>/dev/null || true
            wait \$_pid 2>/dev/null || true
        " || true
    fi
    as_user "$PROJECT_DIR/venv/bin/python3" - "$APP_CONF" "$FRAME_NAME" "$FUNNEL_URL" <<'PYEOF'
import sys, yaml
path, frame_name, funnel_url = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    with open(path) as f:
        config = yaml.safe_load(f) or {}
except FileNotFoundError:
    config = {}
config.setdefault('frame', {})
config['frame']['id'] = frame_name
config['frame']['name'] = frame_name
config['frame']['funnel_url'] = funnel_url
import tempfile, os, pathlib
tmp = pathlib.Path(path).with_suffix('.tmp')
with open(tmp, 'w') as f:
    yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
os.replace(tmp, path)
print(f"  ✓ config.yaml written (frame: {frame_name})")
PYEOF
    save_step 8
fi

# ── Phase 8: start_picframe.sh + labwc + picframe display service ─────────────
if [[ "$LAST" -lt 9 ]]; then
    log "--- Phase 8: labwc display service ---"

    # start_picframe.sh — called by labwc autostart
    cat > "$ACTUAL_HOME/start_picframe.sh" <<EOF
#!/bin/bash
source $ACTUAL_HOME/venv_picframe/bin/activate
export SDL_VIDEODRIVER=x11
picframe &
EOF
    chmod +x "$ACTUAL_HOME/start_picframe.sh"
    chown "$ACTUAL_USER:$ACTUAL_USER" "$ACTUAL_HOME/start_picframe.sh"

    as_user mkdir -p \
        "$ACTUAL_HOME/.config/labwc" \
        "$ACTUAL_HOME/.config/systemd/user/default.target.wants"

    # labwc autostart — runs start_picframe.sh when compositor starts
    printf '%s\n' "$ACTUAL_HOME/start_picframe.sh" > "$ACTUAL_HOME/.config/labwc/autostart"
    chown "$ACTUAL_USER:$ACTUAL_USER" "$ACTUAL_HOME/.config/labwc/autostart"

    # labwc rc.xml — disable window decorations (fullscreen frameless display)
    cat > "$ACTUAL_HOME/.config/labwc/rc.xml" <<'EOF'
<windowRules>
    <windowRule identifier="*" serverDecoration="no" />
</windowRules>
EOF
    chown "$ACTUAL_USER:$ACTUAL_USER" "$ACTUAL_HOME/.config/labwc/rc.xml"

    # systemd user service — labwc is the entry point; launches picframe via autostart
    SERVICE_FILE="$ACTUAL_HOME/.config/systemd/user/picframe.service"
    cat > "$SERVICE_FILE" <<'EOF'
[Unit]
Description=PictureFrame on Pi

[Service]
ExecStart=/usr/bin/labwc
Restart=always

[Install]
WantedBy=default.target
EOF
    chown "$ACTUAL_USER:$ACTUAL_USER" "$SERVICE_FILE"

    WANTS_DIR="$ACTUAL_HOME/.config/systemd/user/default.target.wants"
    as_user ln -sf "$SERVICE_FILE" "$WANTS_DIR/picframe.service"

    # Enable linger so user services start at boot without an interactive login
    loginctl enable-linger "$ACTUAL_USER"
    log "  ✓ picframe display service enabled (labwc → start_picframe.sh)"

    reboot_and_resume 9
fi

# ── Phase 9: Systemd user services (API, sync, lights) ────────────────────────
if [[ "$LAST" -lt 10 ]]; then
    log "--- Phase 9: API/sync/lights services ---"
    wait_for_user_systemd

    as_user mkdir -p "$ACTUAL_HOME/.config/systemd/user"
    for svc in picframe-api.service picframe-sync.service picframe-sync.timer picframe-lights.service; do
        if [[ -f "$PROJECT_DIR/systemd/$svc" ]]; then
            cp "$PROJECT_DIR/systemd/$svc" "$ACTUAL_HOME/.config/systemd/user/"
            chown "$ACTUAL_USER:$ACTUAL_USER" "$ACTUAL_HOME/.config/systemd/user/$svc"
            log "  Installed $svc"
        else
            log "  WARNING: $svc not found in $PROJECT_DIR/systemd/ — skipping"
        fi
    done

    user_systemctl daemon-reload
    user_systemctl enable --now picframe-api.service
    user_systemctl enable --now picframe-sync.timer
    user_systemctl enable --now picframe-lights.service

    check_user_service picframe-api.service
    check_user_service picframe-lights.service

    # Wait for API to be healthy before continuing
    log "  Waiting for API health check..."
    for i in $(seq 1 20); do
        curl -sf http://localhost:8000/health >/dev/null 2>&1 && { log "  ✓ API health OK"; break; }
        sleep 1
    done

    save_step 10
fi

# ── Phase 10: Provisioned state + Koofr setup + install_setup.sh ─────────────
if [[ "$LAST" -lt 11 ]]; then
    check_internet
    log "--- Phase 10: Provisioning + Koofr + WiFi recovery ---"

    # Mark frame as provisioned before watchdog starts (prevents AP portal on boot)
    if ping -c 1 -W 2 8.8.8.8 &>/dev/null; then
        log "  Marking frame as provisioned..."
        sudo "$PROJECT_DIR/venv/bin/python3" - <<PYEOF
import sys
sys.path.insert(0, '${PROJECT_DIR}/scripts/setup')
from state_manager import state_manager
state_manager.set('provisioned', True)
state_manager.set('needs_setup', False)
state_manager.set('frame_name', '${FRAME_NAME}')
print("  provisioned=true, needs_setup=false")
PYEOF
        log "  ✓ Provisioned"
    else
        log "  WARNING: No internet — frame may enter setup mode on next boot"
    fi

    # Configure Koofr via the dashboard API endpoint (validates credentials live)
    if [[ -n "$KOOFR_EMAIL" && -n "$KOOFR_PASS" ]]; then
        log "  Configuring Koofr photo sync..."
        # Ensure API is healthy
        for i in $(seq 1 20); do
            curl -sf http://localhost:8000/health >/dev/null 2>&1 && break
            sleep 1
        done
        # Build JSON safely via python (avoids quoting issues with special chars in password)
        KOOFR_JSON=$(python3 -c \
            "import sys,json; print(json.dumps({'koofr_user': sys.argv[1], 'koofr_pass': sys.argv[2]}))" \
            "$KOOFR_EMAIL" "$KOOFR_PASS")
        KOOFR_RESULT=$(curl -sf -X POST http://localhost:8000/dashboard/koofr-setup \
            -H "Content-Type: application/json" \
            -d "$KOOFR_JSON" 2>/dev/null || echo '{"success":false,"error":"curl failed"}')
        if python3 -c "import sys,json; d=json.loads(sys.argv[1]); sys.exit(0 if d.get('success') else 1)" \
                "$KOOFR_RESULT" 2>/dev/null; then
            log "  ✓ Koofr configured and validated"
        else
            KOOFR_ERR=$(python3 -c \
                "import sys,json; d=json.loads(sys.argv[1]); print(d.get('error','unknown'))" \
                "$KOOFR_RESULT" 2>/dev/null || echo "unknown error")
            log "  WARNING: Koofr setup failed: $KOOFR_ERR"
            log "  Configure Koofr later at: http://$FRAME_NAME.local:8000"
        fi
    else
        log "  Koofr credentials not provided — configure via dashboard"
    fi

    # WiFi recovery installer (hostapd, dnsmasq, watchdog, picframe-config)
    log "  Running WiFi recovery installer (install_setup.sh)..."
    SUDO_USER="$ACTUAL_USER" bash "$PROJECT_DIR/scripts/setup/install_setup.sh"

    save_step 11
fi

# ── Phase 11: Final verify + summary ──────────────────────────────────────────
log "--- Phase 11: Final verification ---"

log "  Cleaning up install artifacts..."
remove_resume_service
rm -f "$STATE_ENV"
rm -f "$PROGRESS_FILE"
rm -f "$PERSISTENT_SCRIPT"
log "  ✓ Artifacts cleaned up"

log "  Run verify anytime: sudo bash $PROJECT_DIR/scripts/setup/verify_install.sh"

{
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ============================================="
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] === PICFRAME INSTALLATION COMPLETE ==="
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ============================================="
    echo "[$(date +'%Y-%m-%d %H:%M:%S')]   Frame name : $FRAME_NAME"
    echo "[$(date +'%Y-%m-%d %H:%M:%S')]   Branch     : $BRANCH"
    echo "[$(date +'%Y-%m-%d %H:%M:%S')]   Funnel URL : $FUNNEL_URL"
    echo "[$(date +'%Y-%m-%d %H:%M:%S')]   Dashboard  : http://$FRAME_NAME.local:8000"
    echo "[$(date +'%Y-%m-%d %H:%M:%S')]   Log file   : $LOG_FILE"
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ============================================="
} | tee -a "$LOG_FILE"
echo ""

# Apply picframe display defaults last — after everything else has settled — so
# nothing started later in the install can overwrite these values.
PCONF="$ACTUAL_HOME/picframe_data/config/configuration.yaml"
if [[ -f "$PCONF" ]]; then
    if apply_picframe_defaults "$PCONF" 2>&1 | tee -a "$LOG_FILE"; then
        ACTUAL_UID=$(id -u "$ACTUAL_USER")
        sudo -u "$ACTUAL_USER" XDG_RUNTIME_DIR="/run/user/$ACTUAL_UID" \
            systemctl --user restart picframe.service
        log "  ✓ picframe.service restarted with updated defaults"
    fi
fi

log "=== Install script exited cleanly ==="

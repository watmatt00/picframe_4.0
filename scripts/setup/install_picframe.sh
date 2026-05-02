#!/bin/bash
set -euo pipefail

# PicFrame Pi3D display engine installer
# Derived from thedigitalpictureframe.com's tested 2025 installer.
# Supports any username (not hardcoded to "pi").
# Optional services: --with-samba, --with-mqtt

# ── Guard ─────────────────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    echo "ERROR: Run with sudo: sudo bash $0" >&2; exit 1
fi

# Parse flags first — --user= is needed before the guard when resume service
# runs as root directly (SUDO_USER is not set by systemd).
ACTUAL_USER=${SUDO_USER:-}
WITH_SAMBA=false
WITH_MQTT=false
for arg in "$@"; do
    case $arg in
        --with-samba) WITH_SAMBA=true ;;
        --with-mqtt)  WITH_MQTT=true ;;
        --user=*)     ACTUAL_USER="${arg#--user=}" ;;
    esac
done
ORIG_ARGS="$*"

if [[ -z "$ACTUAL_USER" || "$ACTUAL_USER" == "root" ]]; then
    echo "ERROR: Run via sudo from a normal user account, not directly as root." >&2
    exit 1
fi
ACTUAL_HOME=$(getent passwd "$ACTUAL_USER" | cut -d: -f6)

# ── Self-persist for reboot resume ───────────────────────────────────────────
# Save to a stable path so the resume systemd service can re-exec after reboots.
PERSISTENT_SCRIPT="$ACTUAL_HOME/install_picframe_resume.sh"
CURRENT_PATH="$(realpath "$0" 2>/dev/null || echo "$0")"
if [[ "$CURRENT_PATH" != "$PERSISTENT_SCRIPT" ]]; then
    echo "Saving installer to $PERSISTENT_SCRIPT for reboot resume..."
    curl -fsSL "https://raw.githubusercontent.com/watmatt00/picframe_4.0/dev/scripts/setup/install_picframe.sh" \
        -o "$PERSISTENT_SCRIPT"
    chown "$ACTUAL_USER:$ACTUAL_USER" "$PERSISTENT_SCRIPT"
    chmod +x "$PERSISTENT_SCRIPT"
    exec bash "$PERSISTENT_SCRIPT" $ORIG_ARGS
fi

# ── Helpers ───────────────────────────────────────────────────────────────────
PROGRESS_FILE="$ACTUAL_HOME/install_progress.txt"
LOG_FILE="$ACTUAL_HOME/install_log.txt"
RESUME_SERVICE="picframe-install"

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

save_step() {
    echo "$1" > "$PROGRESS_FILE"
    chown "$ACTUAL_USER:$ACTUAL_USER" "$PROGRESS_FILE"
}

last_step() {
    [[ -f "$PROGRESS_FILE" ]] && cat "$PROGRESS_FILE" || echo "0"
}

as_user() {
    sudo -u "$ACTUAL_USER" "$@"
}

check_user_service() {
    local service="$1"
    local uid; uid=$(id -u "$ACTUAL_USER")
    local xdg="/run/user/$uid"
    log "Waiting for $service to start..."
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

check_internet() {
    log "Checking internet connection..."
    while ! ping -c 1 -W 2 8.8.8.8 &>/dev/null; do
        log "No connection, retrying in 5s..."
        sleep 5
    done
    log "Internet OK."
}

add_resume_service() {
    cat > "/etc/systemd/system/$RESUME_SERVICE.service" <<EOF
[Unit]
Description=Resume picframe install after reboot

[Service]
ExecStart=/bin/bash $PERSISTENT_SCRIPT --user=$ACTUAL_USER $ORIG_ARGS
Type=oneshot
RemainAfterExit=true

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable "$RESUME_SERVICE"
}

remove_resume_service() {
    systemctl disable "$RESUME_SERVICE" 2>/dev/null || true
    rm -f "/etc/systemd/system/$RESUME_SERVICE.service"
    systemctl daemon-reload
}

reboot_and_resume() {
    add_resume_service
    save_step "$1"
    log "Rebooting (will resume at step $1)..."
    reboot; exit 0
}

# ── Main ──────────────────────────────────────────────────────────────────────
LAST=$(last_step)
log "=== picframe install | user=$ACTUAL_USER last_step=$LAST samba=$WITH_SAMBA mqtt=$WITH_MQTT ==="

# Check 1: Python 3.11+
if python3 -c "import sys; sys.exit(0 if (sys.version_info.major, sys.version_info.minor) >= (3, 11) else 1)" 2>/dev/null; then
    PYTHON_VER=$(python3 -c "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}.{v.micro}')")
    log "  ✓ Python $PYTHON_VER"
else
    PYTHON_VER=$(python3 --version 2>&1 || echo "unknown")
    log "ERROR: Python 3.11+ required, found $PYTHON_VER — run: sudo apt upgrade python3"
    exit 1
fi

# Step 1: OS update
if [[ "$LAST" -lt 1 ]]; then
    check_internet
    log "Step 1: Updating OS..."
    apt-get update && apt-get upgrade -y
    reboot_and_resume 1
fi

# Step 2: Console mode (no desktop environment needed)
if [[ "$LAST" -lt 2 ]]; then
    log "Step 2: Setting boot to console mode..."
    raspi-config nonint do_boot_behaviour B2
    reboot_and_resume 2
fi

# Step 3: Samba (optional — pass --with-samba to enable)
if [[ "$LAST" -lt 3 ]]; then
    if $WITH_SAMBA; then
        check_internet
        log "Step 3: Installing Samba..."
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
        log "Samba configured (share: \\\\$(hostname)\\$ACTUAL_USER, password: $ACTUAL_USER)."
    else
        log "Step 3: Samba skipped (pass --with-samba to enable)."
    fi
    save_step 3
fi

# Step 4: Core packages — labwc (Wayland compositor), SDL2, VLC, FFmpeg
if [[ "$LAST" -lt 4 ]]; then
    check_internet
    log "Step 4: Installing core packages..."
    apt-get install -y git libsdl2-dev xwayland labwc wlr-randr vlc ffmpeg \
        python3-gi python3-gi-cairo gir1.2-gtk-3.0
    if $WITH_MQTT; then
        apt-get install -y mosquitto mosquitto-clients
        log "Mosquitto installed."
    fi
    as_user mkdir -p \
        "$ACTUAL_HOME/Pictures" \
        "$ACTUAL_HOME/picframe_data/deleted_pictures"
    log "Directories created."
    reboot_and_resume 4
fi

# Step 5: Install picframe via pip into a dedicated venv
if [[ "$LAST" -lt 5 ]]; then
    check_internet
    log "Step 5: Creating venv and installing picframe..."
    as_user python3 -m venv "$ACTUAL_HOME/venv_picframe"
    as_user "$ACTUAL_HOME/venv_picframe/bin/pip" install --upgrade pip
    as_user "$ACTUAL_HOME/venv_picframe/bin/pip" install picframe
    log "Running picframe -i to initialize config and data directories..."
    if printf '\n\n\n' | as_user "$ACTUAL_HOME/venv_picframe/bin/picframe" -i "$ACTUAL_HOME/" \
            2>&1 | tee -a "$LOG_FILE"; then
        log "Picframe initialized."
        # Apply required defaults to configuration.yaml
        PCONF="$ACTUAL_HOME/picframe_data/config/configuration.yaml"
        as_user python3 - "$PCONF" <<'PYEOF'
import sys, yaml
p = sys.argv[1]
with open(p) as f:
    cfg = yaml.safe_load(f) or {}
cfg.setdefault("model", {})
cfg["model"]["show_text_tm"] = 0
cfg["model"]["time_delay"] = 20
cfg["model"]["recent_n"] = 7
cfg["model"]["reshuffle_num"] = 1
cfg.setdefault("http", {})["use_http"] = True
with open(p, "w") as f:
    yaml.safe_dump(cfg, f, default_flow_style=False)
print(f"Applied defaults to {p}")
PYEOF
        log "Picframe configuration defaults applied."
        save_step 5
    else
        log "ERROR: picframe init failed. Check $LOG_FILE"
        exit 1
    fi
fi

# Step 6: Mosquitto anonymous config (optional — pass --with-mqtt to enable)
if [[ "$LAST" -lt 6 ]]; then
    if $WITH_MQTT; then
        log "Step 6: Configuring Mosquitto for anonymous local access..."
        grep -qF "allow_anonymous true" /etc/mosquitto/mosquitto.conf || \
            printf 'allow_anonymous true\nlistener 1883 0.0.0.0\n' >> /etc/mosquitto/mosquitto.conf
        systemctl restart mosquitto
        log "Mosquitto configured."
    else
        log "Step 6: MQTT config skipped (pass --with-mqtt to enable)."
    fi
    save_step 6
fi

# Step 7: Create start_picframe.sh launcher
if [[ "$LAST" -lt 7 ]]; then
    log "Step 7: Creating start_picframe.sh..."
    cat > "$ACTUAL_HOME/start_picframe.sh" <<EOF
#!/bin/bash
source $ACTUAL_HOME/venv_picframe/bin/activate
export SDL_VIDEODRIVER=x11
picframe &
EOF
    chmod +x "$ACTUAL_HOME/start_picframe.sh"
    chown "$ACTUAL_USER:$ACTUAL_USER" "$ACTUAL_HOME/start_picframe.sh"
    save_step 7
fi

# Step 8: labwc Wayland compositor + systemd user service
if [[ "$LAST" -lt 8 ]]; then
    log "Step 8: Configuring labwc and picframe.service..."

    as_user mkdir -p \
        "$ACTUAL_HOME/.config/labwc" \
        "$ACTUAL_HOME/.config/systemd/user/default.target.wants"

    # labwc autostart — runs start_picframe.sh when the compositor starts
    cat > "$ACTUAL_HOME/.config/labwc/autostart" <<EOF
$ACTUAL_HOME/start_picframe.sh
EOF
    chown "$ACTUAL_USER:$ACTUAL_USER" "$ACTUAL_HOME/.config/labwc/autostart"

    # labwc rc.xml — disable window decorations (fullscreen frameless display)
    cat > "$ACTUAL_HOME/.config/labwc/rc.xml" <<EOF
<windowRules>
    <windowRule identifier="*" serverDecoration="no" />
</windowRules>
EOF
    chown "$ACTUAL_USER:$ACTUAL_USER" "$ACTUAL_HOME/.config/labwc/rc.xml"

    # systemd user service — labwc is the entry point; it launches picframe via autostart
    SERVICE_FILE="$ACTUAL_HOME/.config/systemd/user/picframe.service"
    cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=PictureFrame on Pi

[Service]
ExecStart=/usr/bin/labwc
Restart=always

[Install]
WantedBy=default.target
EOF
    chown "$ACTUAL_USER:$ACTUAL_USER" "$SERVICE_FILE"

    # Enable by creating the WantedBy symlink directly (avoids needing a live D-Bus session)
    WANTS_DIR="$ACTUAL_HOME/.config/systemd/user/default.target.wants"
    as_user ln -sf "$SERVICE_FILE" "$WANTS_DIR/picframe.service"

    # Enable linger so user services start at boot without an interactive login
    loginctl enable-linger "$ACTUAL_USER"

    log "picframe.service enabled."
    reboot_and_resume 8
fi

# ── Complete ──────────────────────────────────────────────────────────────────
remove_resume_service
rm -f "$PROGRESS_FILE"

# Wait for picframe to start first so it can do its initial config write,
# then apply our defaults on top and restart to pick them up.
log "=== Installation complete! ==="
check_user_service picframe.service

PCONF="$ACTUAL_HOME/picframe_data/config/configuration.yaml"
if [[ -f "$PCONF" ]]; then
    if as_user python3 -c "
import sys, yaml
p='$PCONF'
with open(p) as f:
    cfg = yaml.safe_load(f) or {}
cfg.setdefault('model', {})
cfg['model']['show_text_tm'] = 0
cfg['model']['time_delay'] = 20
cfg['model'].setdefault('recent_n', 7)
cfg['model'].setdefault('reshuffle_num', 1)
cfg.setdefault('http', {})['use_http'] = True
with open(p, 'w') as f:
    yaml.safe_dump(cfg, f, default_flow_style=False)
print('Config defaults applied.')
" 2>&1; then
        log "Picframe config defaults confirmed."
        ACTUAL_UID=$(id -u "$ACTUAL_USER")
        sudo -u "$ACTUAL_USER" XDG_RUNTIME_DIR="/run/user/$ACTUAL_UID" systemctl --user restart picframe.service
        log "picframe.service restarted with new defaults."
    else
        log "WARNING: Could not apply picframe config defaults — check $PCONF manually."
        log "  Required: model.show_text_tm=0, model.time_delay=20, http.use_http=true"
    fi
fi

log "Full log: $LOG_FILE"

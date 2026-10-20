#!/bin/bash
# Undo `install.sh --from-v4`: stop WanderWall v5 and bring PicFrame v4 back.
#
#   sudo bash ~/wanderwall_frame/scripts/setup/rollback_v4.sh
#
# Restores the v4 unit files, tools and configs that the reinstall moved to
# ~/picframe_v4_backup. v4 data in ~/.picframe was never touched. v5 files
# (~/wanderwall_frame, ~/.wanderwall, /var/lib/wanderwall) are left in place.
set -euo pipefail

LOG()  { echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"; }
ERR()  { echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $*" >&2; }

if [[ $EUID -ne 0 ]]; then
    ERR "Run with sudo: sudo bash $0"; exit 1
fi
ACTUAL_USER=${SUDO_USER:-}
if [[ -z "$ACTUAL_USER" || "$ACTUAL_USER" == "root" ]]; then
    ERR "Run via sudo from the frame user (e.g. pi), not directly as root"; exit 1
fi
ACTUAL_HOME=$(getent passwd "$ACTUAL_USER" | cut -d: -f6)
V4_BACKUP="$ACTUAL_HOME/picframe_v4_backup"
USER_UNIT_DIR="$ACTUAL_HOME/.config/systemd/user"

[[ -d "$V4_BACKUP/user-units" ]] || { ERR "No v4 backup at $V4_BACKUP"; exit 1; }
[[ -d "$ACTUAL_HOME/picframe_4.0" ]] || { ERR "v4 repo $ACTUAL_HOME/picframe_4.0 is missing"; exit 1; }

user_systemctl() {
    sudo -u "$ACTUAL_USER" XDG_RUNTIME_DIR="/run/user/$(id -u "$ACTUAL_USER")" systemctl --user "$@"
}

# ── Step 1: stop v5 ───────────────────────────────────────────────────────────
for unit in "$USER_UNIT_DIR"/wanderwall-*.service "$USER_UNIT_DIR"/wanderwall-*.timer; do
    [[ -f "$unit" ]] || continue
    user_systemctl disable --now "$(basename "$unit")" 2>/dev/null || true
    rm -f "$unit"
    LOG "Removed v5 $(basename "$unit")"
done
for unit in /etc/systemd/system/wanderwall-*.service; do
    [[ -f "$unit" ]] || continue
    systemctl disable --now "$(basename "$unit")" 2>/dev/null || true
    rm -f "$unit"
    LOG "Removed v5 $(basename "$unit")"
done
rm -f /etc/polkit-1/rules.d/50-wanderwall.rules /usr/local/bin/wanderwall-config /etc/hostapd/wanderwall-hostapd.conf

# ── Step 2: restore v4 files ──────────────────────────────────────────────────
for f in "$V4_BACKUP"/user-units/*; do
    [[ -f "$f" ]] || continue
    install -m 644 -o "$ACTUAL_USER" -g "$ACTUAL_USER" "$f" "$USER_UNIT_DIR/$(basename "$f")"
    LOG "Restored $(basename "$f")"
done
for f in "$V4_BACKUP"/system/*; do
    [[ -f "$f" ]] || continue
    name="$(basename "$f")"
    case "$name" in
        picframe-*.service*)  dest="/etc/systemd/system/$name" ;;
        50-picframe.rules)    dest="/etc/polkit-1/rules.d/$name" ;;
        picframe-config)      dest="/usr/local/bin/$name" ;;
        picframe-hostapd.conf) dest="/etc/hostapd/$name" ;;
        *) LOG "Skipping unknown backup file $name"; continue ;;
    esac
    cp -p "$f" "$dest"
    LOG "Restored $dest"
done
[[ -f /etc/issue.wanderwall-backup ]] && mv /etc/issue.wanderwall-backup /etc/issue.picframe-backup
if nmcli -t -f NAME con show 2>/dev/null | grep -qx 'wanderwall-wifi'; then
    nmcli con modify wanderwall-wifi connection.id picframe-wifi
    LOG "WiFi profile renamed wanderwall-wifi → picframe-wifi"
fi

# ── Step 3: start v4 ──────────────────────────────────────────────────────────
systemctl daemon-reload
user_systemctl daemon-reload
for unit in "$USER_UNIT_DIR"/picframe-*.service "$USER_UNIT_DIR"/picframe-*.timer; do
    [[ -f "$unit" ]] || continue
    name="$(basename "$unit")"
    # Services started by a timer are enabled through the timer
    if [[ "$name" == *.service && -f "${unit%.service}.timer" ]]; then
        continue
    fi
    user_systemctl enable --now "$name"
    LOG "Enabled and started $name"
done
if [[ -f /etc/systemd/system/picframe-watchdog.service ]]; then
    systemctl enable --now picframe-watchdog.service
    LOG "Enabled and started picframe-watchdog.service"
fi

if user_systemctl is-active --quiet picframe-api.service; then
    LOG "Rollback complete: picframe-api.service is running"
else
    ERR "picframe-api.service is not running: journalctl --user -u picframe-api.service -n 50"
    exit 1
fi

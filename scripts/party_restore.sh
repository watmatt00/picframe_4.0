#!/usr/bin/env bash
# Restores tkframe to its pre-party configuration from backups.
# Run this after the party to return tkframe to normal dev use.
#
# Usage (run on tkframe):
#   bash scripts/party_restore.sh

set -euo pipefail
source "$(dirname "$0")/party_lib.sh"

_step() { echo ""; echo "── $* ──"; }
_done() { echo "  ✓ $*"; }
_warn() { echo "  WARN: $*"; }

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║              PARTY RESTORE                          ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "  Restores tkframe to its pre-party configuration from backup files."
echo ""

# Check all backups exist before doing anything
MISSING=0
[[ -f "${PI3D_CONFIG}.party_backup" ]]  || { echo "  MISSING: ${PI3D_CONFIG}.party_backup";  MISSING=1; }
[[ -f "${APP_CONFIG}.party_backup" ]]   || { echo "  MISSING: ${APP_CONFIG}.party_backup";   MISSING=1; }
[[ -f "${SOURCES_YAML}.party_backup" ]] || { echo "  MISSING: ${SOURCES_YAML}.party_backup"; MISSING=1; }
if [[ "$MISSING" -eq 1 ]]; then
    echo ""
    echo "  ERROR: One or more backup files are missing — cannot restore."
    echo "         If backups were lost, do a full SD rebuild per docs/PI_SETUP.md"
    echo ""
    exit 1
fi

# Detect watchdog without running the full preflight
if systemctl list-unit-files picframe-watchdog.service 2>/dev/null | grep -q 'picframe-watchdog'; then
    WATCHDOG_INSTALLED=true
else
    WATCHDOG_INSTALLED=false
fi

echo "  Actions:"
echo "    - Restore Pi3D config, app config, sources.yaml from *.party_backup"
if [[ "$WATCHDOG_INSTALLED" == "true" ]]; then
echo "    - Re-enable Phase 6 watchdog"
fi
echo "    - Re-enable sync timer"
echo "    - Restart display service"
echo ""

read -r -p "  Proceed with restore? [y/N] " _answer
if [[ "${_answer,,}" != "y" ]]; then
    echo "  Aborted."
    exit 0
fi
echo ""

# ── Restore config files ──────────────────────────────────────────────────────
_step "Restoring config files from backups"
cp "${PI3D_CONFIG}.party_backup"  "$PI3D_CONFIG"  && _done "Pi3D config restored"
cp "${APP_CONFIG}.party_backup"   "$APP_CONFIG"   && _done "App config restored"
cp "${SOURCES_YAML}.party_backup" "$SOURCES_YAML" && _done "sources.yaml restored"

# ── Re-enable watchdog ────────────────────────────────────────────────────────
if [[ "$WATCHDOG_INSTALLED" == "true" ]]; then
    _step "Re-enabling Phase 6 watchdog"
    sudo systemctl enable picframe-watchdog.service
    sudo systemctl start picframe-watchdog.service
    sleep 2
    if systemctl is-active --quiet picframe-watchdog.service 2>/dev/null; then
        _done "Watchdog re-enabled and running"
    else
        _warn "Watchdog may not have started — check: sudo systemctl status picframe-watchdog"
    fi
fi

# ── Re-enable sync timer ──────────────────────────────────────────────────────
_step "Re-enabling sync timer"
systemctl --user start picframe-sync.timer 2>/dev/null || true
sleep 1
if systemctl --user is-active --quiet picframe-sync.timer 2>/dev/null; then
    _done "picframe-sync.timer running"
else
    _warn "Sync timer may not have started — check: systemctl --user status picframe-sync.timer"
fi

# ── Restart display service ───────────────────────────────────────────────────
_step "Restarting display service"
systemctl --user restart picframe.service
sleep 5
if systemctl --user is-active --quiet picframe.service 2>/dev/null; then
    _done "picframe.service running"
else
    _warn "picframe.service may not be active — check: systemctl --user status picframe"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║              RESTORE COMPLETE                       ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "  Backup files kept — delete manually when you're sure things are good:"
echo "    rm ${PI3D_CONFIG}.party_backup"
echo "    rm ${APP_CONFIG}.party_backup"
echo "    rm ${SOURCES_YAML}.party_backup"
echo ""
echo "  Optional: remove party photos (saves ~${REMOTE_BYTES_HUMAN:-several GB} disk space):"
printf "    rm -rf %s\n" "$LOCAL_DIR"
echo ""

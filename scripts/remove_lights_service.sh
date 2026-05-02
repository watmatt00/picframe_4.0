#!/bin/bash
# Removes the picframe-lights service. Use to simulate a pre-lights install
# state before testing the upgrade path (git pull + update_app.sh).
set -euo pipefail

UNIT="picframe-lights.service"
UNIT_FILE="$HOME/.config/systemd/user/$UNIT"

LOG() { echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"; }

if systemctl --user is-active --quiet "$UNIT" 2>/dev/null; then
    systemctl --user stop "$UNIT"
    LOG "Stopped $UNIT"
fi

if systemctl --user is-enabled --quiet "$UNIT" 2>/dev/null; then
    systemctl --user disable "$UNIT"
    LOG "Disabled $UNIT"
fi

if [[ -f "$UNIT_FILE" ]]; then
    rm "$UNIT_FILE"
    LOG "Removed $UNIT_FILE"
fi

systemctl --user daemon-reload
LOG "daemon-reload complete"

# ── Verification ───────────────────────────────────────────────────────────────
PASS=true
ERR() { echo "[$(date +'%Y-%m-%d %H:%M:%S')] FAIL: $*" >&2; PASS=false; }

systemctl --user is-active --quiet "$UNIT" 2>/dev/null \
    && ERR "Service is still active" \
    || LOG "  [OK] Service is not active"

systemctl --user is-enabled --quiet "$UNIT" 2>/dev/null \
    && ERR "Service is still enabled" \
    || LOG "  [OK] Service is not enabled"

[[ -f "$UNIT_FILE" ]] \
    && ERR "Unit file still exists: $UNIT_FILE" \
    || LOG "  [OK] Unit file removed"

[[ -L "$HOME/.config/systemd/user/default.target.wants/$UNIT" ]] \
    && ERR "Symlink still present in default.target.wants/" \
    || LOG "  [OK] No symlink in default.target.wants/"

if $PASS; then
    LOG "picframe-lights fully removed. Run 'git pull && bash scripts/update_app.sh' to reinstall."
else
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: Removal incomplete — see above." >&2
    exit 1
fi

#!/usr/bin/env bash
# Configures tkframe as a standalone party slideshow kiosk.
# Runs the full preflight suite first — aborts if anything fails.
# Prompts for confirmation before making any changes.
#
# Usage (run on tkframe):
#   bash scripts/party_setup.sh

set -euo pipefail
SCRIPT_DIR="$(dirname "$0")"
source "$SCRIPT_DIR/party_lib.sh"

_step() { echo ""; echo "── $* ──"; }
_done() { echo "  ✓ $*"; }
_fail() { echo ""; echo "  ERROR: $*"; echo ""; exit 1; }

# ── Preflight (includes confirmation prompt) ──────────────────────────────────
run_preflight

# ── Backup ────────────────────────────────────────────────────────────────────
_step "Backing up config files"
cp "$PI3D_CONFIG"  "${PI3D_CONFIG}.party_backup"  && _done "Pi3D config  → ${PI3D_CONFIG}.party_backup"
cp "$APP_CONFIG"   "${APP_CONFIG}.party_backup"   && _done "App config   → ${APP_CONFIG}.party_backup"
cp "$SOURCES_YAML" "${SOURCES_YAML}.party_backup" && _done "sources.yaml → ${SOURCES_YAML}.party_backup"

# ── Sync photos ───────────────────────────────────────────────────────────────
_step "Syncing photos from Koofr"
echo "  ${KOOFR_REMOTE}${KOOFR_FOLDER} → $LOCAL_DIR"
echo ""
mkdir -p "$LOCAL_DIR"
rclone sync "${KOOFR_REMOTE}${KOOFR_FOLDER}" "$LOCAL_DIR" --progress

LOCAL_COUNT=$(find "$LOCAL_DIR" -type f | wc -l)
if [[ "$LOCAL_COUNT" -ne "$REMOTE_COUNT" ]]; then
    _fail "File count mismatch after sync (local=$LOCAL_COUNT remote=$REMOTE_COUNT)"
fi
_done "Synced $LOCAL_COUNT files to $LOCAL_DIR"

# ── Add source to sources.yaml ────────────────────────────────────────────────
_step "Updating sources.yaml"
SRC_RESULT=$(python3 - "$SOURCES_YAML" "$SOURCE_ID" "$SOURCE_NAME" "$LOCAL_DIR" <<'PYEOF'
import sys, yaml, os

path, sid, sname, lpath = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
with open(path) as f:
    data = yaml.safe_load(f) or {}
sources = data.get('sources', [])
if any(s.get('id') == sid for s in sources):
    print('ALREADY_EXISTS')
    sys.exit(0)
sources.append({
    'id': sid,
    'name': sname,
    'local_path': lpath,
    'rclone_remote': None,
    'enabled': True,
})
data['sources'] = sources
tmp = path + '.tmp'
with open(tmp, 'w') as f:
    yaml.safe_dump(data, f, default_flow_style=False)
yaml.safe_load(open(tmp))  # verify parseable before replacing
os.replace(tmp, path)
print('ADDED')
PYEOF
)
_done "sources.yaml: $SRC_RESULT"

# ── Update Pi3D config ────────────────────────────────────────────────────────
_step "Updating Pi3D config"
python3 - "$PI3D_CONFIG" "$LOCAL_FOLDER" "$ROTATION_SECONDS" <<'PYEOF'
import sys, yaml, os

path, subdir, delay = sys.argv[1], sys.argv[2], int(sys.argv[3])
with open(path) as f:
    cfg = yaml.safe_load(f) or {}
if 'model' not in cfg:
    cfg['model'] = {}
cfg['model']['pic_dir'] = os.path.expanduser('~/Pictures')
cfg['model']['subdirectory'] = subdir
cfg['model']['time_delay'] = delay
cfg['model']['shuffle'] = True
tmp = path + '.tmp'
with open(tmp, 'w') as f:
    yaml.safe_dump(cfg, f, default_flow_style=False)
yaml.safe_load(open(tmp))  # verify parseable
os.replace(tmp, path)
PYEOF

VERIFY_SUBDIR=$(python3 -c "import yaml; print(yaml.safe_load(open('$PI3D_CONFIG')).get('model', {}).get('subdirectory', ''))")
VERIFY_DELAY=$(python3 -c "import yaml; print(yaml.safe_load(open('$PI3D_CONFIG')).get('model', {}).get('time_delay', ''))")
[[ "$VERIFY_SUBDIR" == "$LOCAL_FOLDER" ]]    || _fail "Pi3D subdirectory mismatch (got '$VERIFY_SUBDIR')"
[[ "$VERIFY_DELAY" == "$ROTATION_SECONDS" ]] || _fail "Pi3D time_delay mismatch (got '$VERIFY_DELAY')"
_done "Pi3D config updated: subdirectory=$LOCAL_FOLDER time_delay=$ROTATION_SECONDS shuffle=true"

# ── Update app config ─────────────────────────────────────────────────────────
_step "Updating app config"
python3 - "$APP_CONFIG" "$SOURCE_ID" "$ROTATION_SECONDS" <<'PYEOF'
import sys, yaml, os

path, src_id, delay = sys.argv[1], sys.argv[2], int(sys.argv[3])
with open(path) as f:
    cfg = yaml.safe_load(f) or {}
if 'display' not in cfg:
    cfg['display'] = {}
cfg['display']['current_source'] = src_id
cfg['display']['rotation_interval'] = delay
tmp = path + '.tmp'
with open(tmp, 'w') as f:
    yaml.safe_dump(cfg, f, default_flow_style=False)
yaml.safe_load(open(tmp))  # verify parseable
os.replace(tmp, path)
PYEOF

VERIFY_SRC=$(python3 -c "import yaml; print(yaml.safe_load(open('$APP_CONFIG')).get('display', {}).get('current_source', ''))")
VERIFY_ROT=$(python3 -c "import yaml; print(yaml.safe_load(open('$APP_CONFIG')).get('display', {}).get('rotation_interval', ''))")
[[ "$VERIFY_SRC" == "$SOURCE_ID" ]]        || _fail "App current_source mismatch (got '$VERIFY_SRC')"
[[ "$VERIFY_ROT" == "$ROTATION_SECONDS" ]] || _fail "App rotation_interval mismatch (got '$VERIFY_ROT')"
_done "App config updated: current_source=$SOURCE_ID rotation_interval=$ROTATION_SECONDS"

# ── Disable watchdog ──────────────────────────────────────────────────────────
if [[ "$WATCHDOG_INSTALLED" == "true" ]]; then
    _step "Disabling Phase 6 watchdog"
    sudo systemctl stop picframe-watchdog.service
    sudo systemctl disable picframe-watchdog.service
    sudo picframe-config --clear-setup
    if systemctl is-active --quiet picframe-watchdog.service 2>/dev/null; then
        _fail "Watchdog still active after stop"
    fi
    _done "Watchdog stopped, disabled, needs_setup cleared"
else
    echo ""
    echo "  [SKIP] Watchdog not installed"
fi

# ── Stop sync timer ───────────────────────────────────────────────────────────
_step "Stopping sync timer"
systemctl --user stop picframe-sync.timer 2>/dev/null || true
if systemctl --user is-active --quiet picframe-sync.timer 2>/dev/null; then
    _fail "Sync timer still active after stop"
fi
_done "picframe-sync.timer stopped"

# ── Restart display service ───────────────────────────────────────────────────
_step "Restarting picframe display service"
systemctl --user restart picframe.service
sleep 5
if ! systemctl --user is-active --quiet picframe.service 2>/dev/null; then
    _fail "picframe.service failed to start after restart"
fi
_done "picframe.service is active"

# ── Final verification ────────────────────────────────────────────────────────
_step "Final verification"

V_SUBDIR=$(python3 -c "import yaml; print(yaml.safe_load(open('$PI3D_CONFIG')).get('model', {}).get('subdirectory', ''))")
V_DELAY=$(python3 -c "import yaml; print(yaml.safe_load(open('$PI3D_CONFIG')).get('model', {}).get('time_delay', ''))")
V_SOURCE=$(python3 -c "import yaml; print(yaml.safe_load(open('$APP_CONFIG')).get('display', {}).get('current_source', ''))")
V_ROTATION=$(python3 -c "import yaml; print(yaml.safe_load(open('$APP_CONFIG')).get('display', {}).get('rotation_interval', ''))")
V_COUNT=$(find "$LOCAL_DIR" -type f | wc -l)
V_SERVICE=$(systemctl --user is-active picframe.service 2>/dev/null || echo "unknown")

printf "  Pi3D subdirectory:   %s\n" "$V_SUBDIR"
printf "  Pi3D time_delay:     %s\n" "$V_DELAY"
printf "  App current_source:  %s\n" "$V_SOURCE"
printf "  App rotation:        %s\n" "$V_ROTATION"
printf "  Local photos:        %s files\n" "$V_COUNT"
printf "  picframe.service:    %s\n" "$V_SERVICE"

FINAL_FAIL=0
[[ "$V_SUBDIR"   == "$LOCAL_FOLDER" ]]    || { echo "  FAIL: Pi3D subdirectory wrong";    FINAL_FAIL=1; }
[[ "$V_DELAY"    == "$ROTATION_SECONDS" ]] || { echo "  FAIL: Pi3D time_delay wrong";      FINAL_FAIL=1; }
[[ "$V_SOURCE"   == "$SOURCE_ID" ]]        || { echo "  FAIL: App current_source wrong";   FINAL_FAIL=1; }
[[ "$V_COUNT"    -gt 0 ]]                  || { echo "  FAIL: No local photos found";       FINAL_FAIL=1; }
[[ "$V_SERVICE"  == "active" ]]            || { echo "  FAIL: picframe.service not active"; FINAL_FAIL=1; }
[[ "$FINAL_FAIL" -eq 0 ]]                  || _fail "Final verification failed — see above"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║            PARTY SETUP COMPLETE ✓                   ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
printf "  Photos:      %s files in %s\n" "$V_COUNT" "$LOCAL_DIR"
printf "  Rotation:    %s seconds per photo\n" "$ROTATION_SECONDS"
if [[ "$WATCHDOG_INSTALLED" == "true" ]]; then
printf "  Watchdog:    DISABLED\n"
fi
printf "  Sync timer:  STOPPED\n"
echo ""
echo "  Backups saved as *.party_backup"
echo ""
echo "  NEXT STEP:"
echo "    sudo reboot"
echo "    (verify slideshow appears on the monitor after ~60 seconds)"
echo ""
echo "  Before the party — top up photos:"
echo "    bash scripts/party_final_sync.sh"
echo ""
echo "  After the party — restore tkframe:"
echo "    bash scripts/party_restore.sh"
echo "    (or full SD rebuild per docs/PI_SETUP.md)"
echo ""

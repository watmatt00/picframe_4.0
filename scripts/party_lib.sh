#!/usr/bin/env bash
# Party slideshow shared library — source this, never run directly.
#
# Provides config variables, preflight check functions, and run_preflight().
# Both party_preflight.sh and party_setup.sh source this file so that
# preflight logic has exactly one copy.

# ── Configuration (edit here) ─────────────────────────────────────────────────
ROTATION_SECONDS=10
KOOFR_FOLDER="KFR_mo_grad"
LOCAL_FOLDER="kfr_mo_grad"
SOURCE_ID="kfr_mo_grad"
SOURCE_NAME="KFR Mo Grad"

PI3D_CONFIG="$HOME/picframe_data/config/configuration.yaml"
APP_CONFIG="$HOME/.picframe/config.yaml"
SOURCES_YAML="$HOME/.picframe/sources.yaml"
LOCAL_DIR="$HOME/Pictures/$LOCAL_FOLDER"

# ── State accumulated by check functions ──────────────────────────────────────
KOOFR_REMOTE=""
REMOTE_COUNT=0
REMOTE_BYTES=0
REMOTE_BYTES_HUMAN="?"
FREE_BYTES=0
FREE_HUMAN="?"
WATCHDOG_INSTALLED=false
ORIG_PIC_DIR=""
ORIG_SUBDIRECTORY=""
ORIG_TIME_DELAY=""
ORIG_CURRENT_SOURCE=""
PASS_COUNT=0
FAIL_COUNT=0

# ── Output helpers ────────────────────────────────────────────────────────────
_ok()   { echo "  [PASS] $*"; PASS_COUNT=$(( PASS_COUNT + 1 )); }
_fail() { echo "  [FAIL] $*"; FAIL_COUNT=$(( FAIL_COUNT + 1 )); }
_info() { echo "  [INFO] $*"; }
_skip() { echo "  [SKIP] $*"; }

# ── Individual check functions ────────────────────────────────────────────────

check_hostname() {
    local h; h=$(hostname 2>/dev/null || echo "unknown")
    if [[ "$h" == "tkframe" ]]; then
        _ok "Hostname is tkframe"
    else
        _fail "Hostname is '$h' — this script must run on tkframe, not on $h"
    fi
}

check_service_picframe() {
    if systemctl --user is-active --quiet picframe.service 2>/dev/null; then
        _ok "picframe.service is active"
    else
        local state; state=$(systemctl --user is-active picframe.service 2>/dev/null || echo "unknown")
        _fail "picframe.service is not active (state: $state)"
    fi
}

check_service_api() {
    if systemctl --user is-active --quiet picframe-api.service 2>/dev/null; then
        _ok "picframe-api.service is active"
    else
        local state; state=$(systemctl --user is-active picframe-api.service 2>/dev/null || echo "unknown")
        _fail "picframe-api.service is not active (state: $state)"
    fi
}

check_pi3d_config() {
    if [[ -f "$PI3D_CONFIG" ]]; then
        _ok "Pi3D config exists"
        ORIG_PIC_DIR=$(python3 -c "
import yaml
try:
    print(yaml.safe_load(open('$PI3D_CONFIG')).get('model', {}).get('pic_dir', ''))
except Exception:
    print('')
" 2>/dev/null || echo "")
        ORIG_SUBDIRECTORY=$(python3 -c "
import yaml
try:
    print(yaml.safe_load(open('$PI3D_CONFIG')).get('model', {}).get('subdirectory', ''))
except Exception:
    print('')
" 2>/dev/null || echo "")
        ORIG_TIME_DELAY=$(python3 -c "
import yaml
try:
    print(yaml.safe_load(open('$PI3D_CONFIG')).get('model', {}).get('time_delay', ''))
except Exception:
    print('')
" 2>/dev/null || echo "")
    else
        _fail "Pi3D config not found: $PI3D_CONFIG"
    fi
}

check_app_config() {
    if [[ -f "$APP_CONFIG" ]]; then
        _ok "App config exists"
        ORIG_CURRENT_SOURCE=$(python3 -c "
import yaml
try:
    print(yaml.safe_load(open('$APP_CONFIG')).get('display', {}).get('current_source', ''))
except Exception:
    print('')
" 2>/dev/null || echo "")
    else
        _fail "App config not found: $APP_CONFIG"
    fi
}

check_sources_yaml() {
    if [[ -f "$SOURCES_YAML" ]]; then
        _ok "sources.yaml exists"
    else
        _fail "sources.yaml not found: $SOURCES_YAML"
    fi
}

check_rclone() {
    if command -v rclone &>/dev/null; then
        local ver; ver=$(rclone version 2>/dev/null | head -1 || echo "unknown version")
        _ok "rclone installed ($ver)"
    else
        _fail "rclone not found — install rclone first"
    fi
}

check_koofr_remote() {
    KOOFR_REMOTE=$(rclone listremotes 2>/dev/null | grep -i koofr | head -1 || echo "")
    if [[ -n "$KOOFR_REMOTE" ]]; then
        _ok "Koofr remote found: ${KOOFR_REMOTE}"
    else
        _fail "No Koofr rclone remote configured (run: rclone config)"
    fi
}

check_koofr_accessible() {
    if [[ -z "$KOOFR_REMOTE" ]]; then
        _skip "Koofr accessible — no remote to test"
        return
    fi
    if rclone lsd "${KOOFR_REMOTE}" --max-depth 1 --timeout 30s &>/dev/null 2>&1; then
        _ok "Koofr remote is reachable"
    else
        _fail "Cannot reach Koofr remote ${KOOFR_REMOTE} (check network / credentials)"
    fi
}

check_koofr_folder() {
    if [[ -z "$KOOFR_REMOTE" ]]; then
        _skip "Koofr folder — no remote to test"
        return
    fi
    if rclone lsd "${KOOFR_REMOTE}" --timeout 30s 2>/dev/null | grep -qF "$KOOFR_FOLDER"; then
        _ok "Koofr folder exists: ${KOOFR_REMOTE}${KOOFR_FOLDER}"
    else
        _fail "Koofr folder not found: ${KOOFR_REMOTE}${KOOFR_FOLDER}"
    fi
}

check_koofr_files() {
    if [[ -z "$KOOFR_REMOTE" ]]; then
        _skip "Koofr file count — no remote to test"
        return
    fi
    local json
    json=$(rclone size "${KOOFR_REMOTE}${KOOFR_FOLDER}" --json --timeout 60s 2>/dev/null || echo "")
    if [[ -n "$json" ]]; then
        REMOTE_COUNT=$(echo "$json" | python3 -c "import sys,json; print(json.load(sys.stdin)['count'])" 2>/dev/null || echo "0")
        REMOTE_BYTES=$(echo "$json" | python3 -c "import sys,json; print(json.load(sys.stdin)['bytes'])" 2>/dev/null || echo "0")
        REMOTE_BYTES_HUMAN=$(python3 -c "
b = $REMOTE_BYTES
if b >= 1073741824:
    print(f'{b/1073741824:.1f} GB')
elif b >= 1048576:
    print(f'{b/1048576:.0f} MB')
else:
    print(f'{b} bytes')
" 2>/dev/null || echo "${REMOTE_BYTES} bytes")
    fi
    if [[ "$REMOTE_COUNT" -gt 0 ]]; then
        _ok "$REMOTE_COUNT photos in ${KOOFR_REMOTE}${KOOFR_FOLDER} (${REMOTE_BYTES_HUMAN})"
    else
        _fail "No files found in ${KOOFR_REMOTE}${KOOFR_FOLDER}"
    fi
}

check_disk_space() {
    FREE_BYTES=$(df --output=avail -B1 "$HOME" 2>/dev/null | tail -1 | tr -d ' ' || echo "0")
    FREE_HUMAN=$(python3 -c "
b = $FREE_BYTES
if b >= 1073741824:
    print(f'{b/1073741824:.1f} GB')
elif b >= 1048576:
    print(f'{b/1048576:.0f} MB')
else:
    print(f'{b} bytes')
" 2>/dev/null || echo "?")

    # Need remote bytes + 10% headroom + 100 MB buffer
    local needed=$(( REMOTE_BYTES + REMOTE_BYTES / 10 + 104857600 ))
    if [[ "$FREE_BYTES" -gt "$needed" ]]; then
        _ok "Disk space OK: ${FREE_HUMAN} free (photos need ~${REMOTE_BYTES_HUMAN})"
    else
        _fail "Insufficient disk: ${FREE_HUMAN} free, need ~${REMOTE_BYTES_HUMAN} + headroom"
    fi
}

check_watchdog() {
    if systemctl list-unit-files picframe-watchdog.service 2>/dev/null | grep -q 'picframe-watchdog'; then
        WATCHDOG_INSTALLED=true
        local state; state=$(systemctl is-active picframe-watchdog.service 2>/dev/null || echo "inactive")
        _info "Phase 6 watchdog INSTALLED (currently $state) — will be disabled"
    else
        WATCHDOG_INSTALLED=false
        _info "Phase 6 watchdog not installed — skipping disable step"
    fi
}

check_watchdog_tools() {
    [[ "$WATCHDOG_INSTALLED" != "true" ]] && return
    if command -v picframe-config &>/dev/null; then
        _ok "picframe-config command found"
    else
        _fail "picframe-config not found — cannot clear needs_setup flag"
    fi
    if sudo test -r /var/lib/picframe/state.yaml 2>/dev/null; then
        _ok "state.yaml readable via sudo"
    else
        _fail "Cannot read /var/lib/picframe/state.yaml with sudo"
    fi
}

# ── run_preflight ─────────────────────────────────────────────────────────────
# Usage: run_preflight [--report-only]
#   --report-only  Print summary and exit 0 (no prompt). Used by party_preflight.sh.
#   (no flag)      Print summary, prompt "Proceed? [y/N]", exit on "n". Used by party_setup.sh.
run_preflight() {
    local report_only=false
    [[ "${1:-}" == "--report-only" ]] && report_only=true

    # Reset counters and state
    PASS_COUNT=0
    FAIL_COUNT=0
    KOOFR_REMOTE=""
    REMOTE_COUNT=0
    REMOTE_BYTES=0
    REMOTE_BYTES_HUMAN="?"
    FREE_BYTES=0
    FREE_HUMAN="?"
    WATCHDOG_INSTALLED=false
    ORIG_PIC_DIR=""
    ORIG_SUBDIRECTORY=""
    ORIG_TIME_DELAY=""
    ORIG_CURRENT_SOURCE=""

    echo ""
    echo "╔══════════════════════════════════════════════════════╗"
    echo "║         PARTY SETUP — PREFLIGHT CHECKS              ║"
    echo "╚══════════════════════════════════════════════════════╝"
    echo ""

    check_hostname
    check_service_picframe
    check_service_api
    check_pi3d_config
    check_app_config
    check_sources_yaml
    check_rclone
    check_koofr_remote
    check_koofr_accessible
    check_koofr_folder
    check_koofr_files
    check_disk_space
    check_watchdog
    check_watchdog_tools

    echo ""
    echo "  ────────────────────────────────────────────────────"
    printf "  Checks: %d passed, %d failed\n" "$PASS_COUNT" "$FAIL_COUNT"
    echo "  ────────────────────────────────────────────────────"

    if [[ "$FAIL_COUNT" -gt 0 ]]; then
        echo ""
        echo "  PREFLIGHT FAILED — fix the issues above before running party_setup.sh"
        echo ""
        exit 1
    fi

    echo ""
    echo "  === ALL CHECKS PASSED ==="
    echo ""
    printf "  Koofr remote:    %s\n"  "$KOOFR_REMOTE"
    printf "  Photos:          %s files (%s)\n" "$REMOTE_COUNT" "$REMOTE_BYTES_HUMAN"
    printf "  Free space:      %s available\n"  "$FREE_HUMAN"
    printf "  Rotation:        %s seconds/photo\n" "$ROTATION_SECONDS"
    if [[ "$WATCHDOG_INSTALLED" == "true" ]]; then
        printf "  Watchdog:        INSTALLED (will be disabled)\n"
    else
        printf "  Watchdog:        not installed\n"
    fi
    echo ""
    echo "  Current config (will be overwritten — backups saved first):"
    printf "    pic_dir:        %s\n"  "${ORIG_PIC_DIR:-(empty)}"
    printf "    subdirectory:   %s\n"  "${ORIG_SUBDIRECTORY:-(empty)}"
    printf "    time_delay:     %s\n"  "${ORIG_TIME_DELAY:-(empty)}"
    printf "    current_source: %s\n"  "${ORIG_CURRENT_SOURCE:-(empty)}"
    echo ""

    if [[ "$report_only" == "true" ]]; then
        echo "  Preflight passed. Run  bash scripts/party_setup.sh  to apply changes."
        echo ""
        exit 0
    fi

    read -r -p "  Proceed with setup? [y/N] " _answer
    if [[ "${_answer,,}" != "y" ]]; then
        echo "  Aborted."
        exit 0
    fi
    echo ""
}

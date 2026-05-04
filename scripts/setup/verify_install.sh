#!/bin/bash
# PicFrame post-install verification — run standalone anytime:
#   sudo bash scripts/setup/verify_install.sh [--funnel-url=https://...]

set -uo pipefail

FUNNEL_URL=""
for arg in "$@"; do
    case $arg in
        --funnel-url=*) FUNNEL_URL="${arg#--funnel-url=}" ;;
    esac
done

# Derive the frame user — script may be called as root (via sudo) or as user
FRAME_USER="${SUDO_USER:-$USER}"
FRAME_HOME=$(getent passwd "$FRAME_USER" | cut -d: -f6)
PROJECT_DIR="$FRAME_HOME/picframe_4.0"

# Read Funnel URL from config.yaml if not passed as arg
if [[ -z "$FUNNEL_URL" ]] && [[ -f "$FRAME_HOME/.picframe/config.yaml" ]]; then
    FUNNEL_URL=$(python3 -c "
import yaml
with open('$FRAME_HOME/.picframe/config.yaml') as f:
    c = yaml.safe_load(f) or {}
print(c.get('frame', {}).get('funnel_url', ''))
" 2>/dev/null || true)
fi

PASS=0
FAIL=0

ok()   { echo "  ✓ $1"; ((PASS++)); }
fail() { echo "  ✗ $1  →  $2"; ((FAIL++)); }

check_user_svc() {
    local svc="$1" uid; uid=$(id -u "$FRAME_USER")
    if timeout 5 sudo -u "$FRAME_USER" XDG_RUNTIME_DIR="/run/user/$uid" \
            systemctl --user is-active --quiet "$svc" 2>/dev/null; then
        ok "$svc active"
    else
        fail "$svc active" "sudo -u $FRAME_USER systemctl --user start $svc"
    fi
}

echo ""
echo "=== PicFrame Install Verification ==="

# 1. Python 3.11+
if python3 -c "import sys; sys.exit(0 if (sys.version_info.major, sys.version_info.minor) >= (3, 11) else 1)" 2>/dev/null; then
    VER=$(python3 -c "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}.{v.micro}')")
    ok "Python $VER"
else
    fail "Python 3.11+" "sudo apt upgrade python3"
fi

# 2. picframe.service active (user service)
check_user_svc picframe.service

# 3. picframe-api.service active (user service)
check_user_svc picframe-api.service

# 4. picframe-lights.service active (user service)
check_user_svc picframe-lights.service

# 5. picframe-sync.timer active (user service)
check_user_svc picframe-sync.timer

# 6. picframe-watchdog active (system service)
if timeout 5 systemctl is-active --quiet picframe-watchdog 2>/dev/null; then
    ok "picframe-watchdog active"
else
    fail "picframe-watchdog active" "sudo systemctl start picframe-watchdog"
fi

# 7. rclone installed
if command -v rclone &>/dev/null; then
    VER=$(rclone version 2>/dev/null | head -1 | awk '{print $2}')
    ok "rclone $VER"
else
    fail "rclone installed" "curl https://rclone.org/install.sh | sudo bash"
fi

# 8. Tailscale connected
if timeout 10 tailscale status &>/dev/null; then
    ok "Tailscale connected"
else
    fail "Tailscale connected" "sudo tailscale up"
fi

# 9. venv exists
if [[ -d "$PROJECT_DIR/venv" ]]; then
    ok "venv exists"
else
    fail "venv exists" "python3 -m venv $PROJECT_DIR/venv && $PROJECT_DIR/venv/bin/pip install -e $PROJECT_DIR"
fi

# 10. config.yaml exists
if [[ -f "$FRAME_HOME/.picframe/config.yaml" ]]; then
    ok "config.yaml exists"
else
    fail "config.yaml exists" "re-run setup_api.sh Step 4"
fi

# 11. API health (local)
if curl -sf --connect-timeout 5 http://localhost:8000/health >/dev/null 2>&1; then
    ok "API health (local)"
else
    fail "API health (local)" "systemctl --user restart picframe-api.service"
fi

# 12. API health (Funnel public path)
if [[ -z "$FUNNEL_URL" ]]; then
    fail "API health (Funnel public)" "Funnel URL unknown — re-run with --funnel-url=https://..."
else
    hostname=$(echo "$FUNNEL_URL" | sed 's|https://||' | sed 's|/.*||')
    public_ip=$(curl -sf --connect-timeout 5 \
        "https://cloudflare-dns.com/dns-query?name=${hostname}&type=A" \
        -H "accept: application/dns-json" \
        | python3 -c "import json,sys; d=json.load(sys.stdin); print(next((a['data'] for a in d.get('Answer',[]) if a['type']==1),''))" 2>/dev/null || true)
    if [[ -z "$public_ip" ]]; then
        fail "API health (Funnel public)" "Funnel DNS not resolving — visit https://login.tailscale.com/admin/machines"
    elif curl -sf --connect-timeout 10 --resolve "$hostname:443:$public_ip" "https://$hostname/health" >/dev/null 2>&1; then
        ok "API health (Funnel public → $public_ip)"
    else
        fail "API health (Funnel public)" "sudo tailscale funnel --bg 8000  |  check https://login.tailscale.com/admin/machines"
    fi
fi

# 13. picframe-config --show
if timeout 5 picframe-config --show >/dev/null 2>&1; then
    ok "picframe-config --show"
else
    fail "picframe-config --show" "sudo bash scripts/setup/install_setup.sh"
fi

echo ""
if [[ $FAIL -eq 0 ]]; then
    echo "All $PASS checks passed."
else
    echo "$FAIL check(s) failed, $PASS passed."
    echo "Re-run anytime: sudo bash $PROJECT_DIR/scripts/setup/verify_install.sh"
fi

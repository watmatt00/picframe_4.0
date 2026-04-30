#!/bin/bash
# test_lights.sh — Interactive indicator light tester.
# Overrides are in-memory only; cleared on API restart or by pressing x.
#
# Usage: ./scripts/test_lights.sh [host]
#   host defaults to 192.168.102.210:8000

set -euo pipefail

HOST="${1:-192.168.102.210:8000}"
URL="http://${HOST}/dashboard/test-lights"

post() {
    curl -sf -X POST "$URL" \
        -H "Content-Type: application/json" \
        -d "$1" > /dev/null
}

echo "PicFrame Light Tester  (host: ${HOST})"
echo "  1  →  Amber + Green   (no sync, wifi up)"
echo "  2  →  Amber + Red     (no sync, wifi down)"
echo "  x  →  Reset           (restore real behavior)"
echo "  q  →  Quit"
echo ""

while true; do
    read -rp "> " key
    case "$key" in
        1)
            post '{"sync_status": "error", "wifi_connected": true}'
            echo "State 1 set — amber + green"
            ;;
        2)
            post '{"sync_status": "error", "wifi_connected": false}'
            echo "State 2 set — amber + red"
            ;;
        x)
            post '{"sync_status": null, "wifi_connected": null}'
            echo "Reset — real values restored"
            ;;
        q)
            echo "Quit"
            exit 0
            ;;
        *)
            echo "  1 / 2 / x / q"
            ;;
    esac
done

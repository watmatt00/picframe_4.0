#!/bin/bash
# test_lights.sh — Force indicator light states for manual testing.
# Overrides are in-memory only; cleared on API restart or by running 'reset'.
#
# Usage: ./scripts/test_lights.sh <command> [host]
#   Commands:
#     amber       — amber sync light ON (simulates out-of-sync)
#     no-amber    — amber sync light OFF (simulates in-sync)
#     wifi-red    — wifi light RED (simulates disconnected)
#     wifi-green  — wifi light GREEN (simulates connected)
#     reset       — clear all overrides, restore real behavior
#   Host defaults to tkframe LAN IP (192.168.102.210:8000)
#
# Examples:
#   ./scripts/test_lights.sh amber
#   ./scripts/test_lights.sh wifi-red 192.168.102.210:8000

set -euo pipefail

CMD="${1:-}"
HOST="${2:-192.168.102.210:8000}"
URL="http://${HOST}/dashboard/test-lights"

usage() {
    echo "Usage: $0 <amber|no-amber|wifi-red|wifi-green|reset> [host]"
    exit 1
}

case "$CMD" in
    amber)
        echo "Setting sync light → AMBER"
        curl -sf -X POST "$URL" -H "Content-Type: application/json" \
            -d '{"sync_status": "error"}' | python3 -m json.tool
        ;;
    no-amber)
        echo "Setting sync light → OFF"
        curl -sf -X POST "$URL" -H "Content-Type: application/json" \
            -d '{"sync_status": "match"}' | python3 -m json.tool
        ;;
    wifi-red)
        echo "Setting wifi light → RED"
        curl -sf -X POST "$URL" -H "Content-Type: application/json" \
            -d '{"wifi_connected": false}' | python3 -m json.tool
        ;;
    wifi-green)
        echo "Setting wifi light → GREEN"
        curl -sf -X POST "$URL" -H "Content-Type: application/json" \
            -d '{"wifi_connected": true}' | python3 -m json.tool
        ;;
    reset)
        echo "Clearing all light overrides"
        curl -sf -X POST "$URL" -H "Content-Type: application/json" \
            -d '{"sync_status": null, "wifi_connected": null}' | python3 -m json.tool
        ;;
    *)
        usage
        ;;
esac

echo ""
echo "Dashboard auto-refreshes every 15s — or hit Refresh to see the change immediately."

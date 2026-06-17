#!/usr/bin/env bash
# Pulls the latest photos from Koofr into the local party folder.
# Safe to run any number of times between party_setup.sh and the party.
# Makes NO config changes and does NOT restart any service.
# Pi3D picks up new files on its next shuffle pass automatically.
#
# Usage (run on tkframe):
#   bash scripts/party_final_sync.sh

set -euo pipefail
source "$(dirname "$0")/party_lib.sh"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║            PARTY FINAL SYNC                         ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

KOOFR_REMOTE=$(rclone listremotes 2>/dev/null | grep -i koofr | head -1 || echo "")
if [[ -z "$KOOFR_REMOTE" ]]; then
    echo "ERROR: No Koofr rclone remote found"
    exit 1
fi

if [[ ! -d "$LOCAL_DIR" ]]; then
    echo "ERROR: $LOCAL_DIR not found"
    echo "       Run  bash scripts/party_setup.sh  first"
    exit 1
fi

BEFORE=$(find "$LOCAL_DIR" -type f | wc -l)
printf "  Before:  %s local files\n" "$BEFORE"
printf "  Syncing: %s%s → %s\n" "$KOOFR_REMOTE" "$KOOFR_FOLDER" "$LOCAL_DIR"
echo ""

rclone sync "${KOOFR_REMOTE}${KOOFR_FOLDER}" "$LOCAL_DIR" --progress

AFTER=$(find "$LOCAL_DIR" -type f | wc -l)
ADDED=$(( AFTER - BEFORE ))

echo ""
echo "=== SYNC COMPLETE ==="
printf "  Files now:  %s\n" "$AFTER"
printf "  Added:      %s new file(s)\n" "$ADDED"
echo ""
echo "  No config changed. Display service not restarted."
echo "  Pi3D picks up new files on its next shuffle pass."
echo ""

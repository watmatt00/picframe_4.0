#!/usr/bin/env bash
# Installs the party-scripts pre-push guard into .git/hooks/pre-push.
# Run this ONCE on the dev machine (fuckms) after pulling this branch.
# The hook blocks git push to main when scripts/party_* files are present.
#
# Usage (run from repo root or scripts/ dir):
#   bash scripts/install_dev_hooks.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
HOOK_SRC="$SCRIPT_DIR/pre-push.hook"
HOOK_DEST="$REPO_ROOT/.git/hooks/pre-push"

if [[ ! -f "$HOOK_SRC" ]]; then
    echo "ERROR: Hook source not found: $HOOK_SRC"
    exit 1
fi

if [[ -f "$HOOK_DEST" ]]; then
    echo "Existing pre-push hook found — backing up to ${HOOK_DEST}.bak"
    cp "$HOOK_DEST" "${HOOK_DEST}.bak"
fi

cp "$HOOK_SRC" "$HOOK_DEST"
chmod +x "$HOOK_DEST"

echo ""
echo "Pre-push hook installed: $HOOK_DEST"
echo ""
echo "Effect: pushing scripts/party_*.sh files to main is now blocked."
echo "        This only affects your local repo — it's not enforced on the remote."
echo ""

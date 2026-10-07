#!/bin/bash
# Install the restricted read-only "claude-inspect" SSH key on a PicFrame Pi.
#
# Run on the Pi as the frame user (not root), after pulling the repo:
#
#   bash ~/picframe_4.0/scripts/setup/install_inspect_key.sh
#       Installs the command filter to ~/.local/bin/picframe-inspect and adds the
#       claude-inspect key to ~/.ssh/authorized_keys, forced through that filter.
#       Idempotent; re-run it to pick up a changed filter.
#
#   bash ~/picframe_4.0/scripts/setup/install_inspect_key.sh --remove-dev-keys
#       Also removes the unrestricted dev PC keys. Run this only after you have
#       confirmed password login works (ssh tkframe-pw). Afterwards the only key
#       that opens this Pi is the read-only claude-inspect key.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
FILTER_SRC="$PROJECT_DIR/scripts/pi/picframe-inspect"
PUBKEY_FILE="$SCRIPT_DIR/claude_inspect.pub"
FILTER_DEST="$HOME/.local/bin/picframe-inspect"
SSH_DIR="$HOME/.ssh"
AUTH_KEYS="$SSH_DIR/authorized_keys"
LOCK_FILE="$SSH_DIR/.authorized_keys.lock"

# Unrestricted keys from the dev PC (fuckms), matched by fingerprint
DEV_KEY_FINGERPRINTS=(
    "SHA256:51jje46xCzfoESVyntbz1qbDlQCo51M0ggKOTeYkOVA"  # watmatt00@gmail.com (ed25519)
    "SHA256:nE2f8AaWlE5GkxPMwf18GaUPpfbLiqFR+qmnYXzC5hY"  # matt@fuckms (rsa)
)

LOG()  { echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"; }
ERR()  { echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $*" >&2; }

REMOVE_DEV_KEYS=false
for arg in "$@"; do
    case "$arg" in
        --remove-dev-keys) REMOVE_DEV_KEYS=true ;;
        *) ERR "Unknown argument: $arg"; exit 1 ;;
    esac
done

if [[ "$(id -u)" -eq 0 ]]; then
    ERR "Run as the frame user (e.g. pi), not root"
    exit 1
fi
for f in "$FILTER_SRC" "$PUBKEY_FILE"; do
    [[ -f "$f" ]] || { ERR "Missing $f — pull the repo first"; exit 1; }
done

# Removing the dev keys leaves password login as the only way in for you
if $REMOVE_DEV_KEYS && grep -qsEi '^\s*PasswordAuthentication\s+no' /etc/ssh/sshd_config /etc/ssh/sshd_config.d/*.conf; then
    ERR "PasswordAuthentication is disabled in sshd config — removing the dev keys would lock you out. Aborting."
    exit 1
fi

# Fingerprint of one authorized_keys line ("" if it isn't a key)
fingerprint() {
    local tmp
    tmp="$(mktemp)"
    printf '%s\n' "$1" > "$tmp"
    ssh-keygen -lf "$tmp" 2>/dev/null | awk '{print $2}' || true
    rm -f "$tmp"
}

# ── Step 1: install the command filter ─────────────────────────────────────────
mkdir -p "$(dirname "$FILTER_DEST")"
install -m 755 "$FILTER_SRC" "$FILTER_DEST"
LOG "Command filter installed: $FILTER_DEST"

# ── Step 2: rewrite authorized_keys atomically under a lock ────────────────────
mkdir -p "$SSH_DIR"
chmod 700 "$SSH_DIR"
touch "$AUTH_KEYS"

PUBKEY="$(awk '{print $1" "$2" "$3}' "$PUBKEY_FILE")"
INSPECT_FP="$(fingerprint "$PUBKEY")"
INSPECT_LINE="restrict,command=\"$FILTER_DEST\" $PUBKEY"

exec 9>"$LOCK_FILE"
flock -w 10 9 || { ERR "Could not lock $AUTH_KEYS"; exit 1; }

TMP_KEYS="$(mktemp "$SSH_DIR/authorized_keys.XXXXXX")"
trap 'rm -f "$TMP_KEYS"' EXIT
removed=0
while IFS= read -r line || [[ -n "$line" ]]; do
    fp="$(fingerprint "$line")"
    # Drop any existing claude-inspect line; it is re-added below in canonical form
    [[ -n "$fp" && "$fp" == "$INSPECT_FP" ]] && continue
    if $REMOVE_DEV_KEYS && [[ -n "$fp" ]]; then
        skip=false
        for dev_fp in "${DEV_KEY_FINGERPRINTS[@]}"; do
            [[ "$fp" == "$dev_fp" ]] && skip=true
        done
        if $skip; then
            removed=$((removed + 1))
            continue
        fi
    fi
    printf '%s\n' "$line" >> "$TMP_KEYS"
done < "$AUTH_KEYS"
printf '%s\n' "$INSPECT_LINE" >> "$TMP_KEYS"

chmod 600 "$TMP_KEYS"
mv "$TMP_KEYS" "$AUTH_KEYS"
trap - EXIT
LOG "claude-inspect key installed (read-only, forced through $FILTER_DEST)"
if $REMOVE_DEV_KEYS; then
    LOG "Removed $removed unrestricted dev key(s). Log in with your password from now on."
fi

# ── Step 3: show the result ────────────────────────────────────────────────────
LOG "Keys now authorized for $(whoami)@$(hostname):"
while IFS= read -r line || [[ -n "$line" ]]; do
    fp="$(fingerprint "$line")"
    [[ -z "$fp" ]] && continue
    if [[ "$line" == restrict,command=* ]]; then
        echo "  $fp  $(awk '{print $NF}' <<< "$line")  (read-only)"
    else
        echo "  $fp  $(awk '{print $NF}' <<< "$line")  (FULL ACCESS)"
    fi
done < "$AUTH_KEYS"
LOG "install_inspect_key.sh completed successfully"
exit 0

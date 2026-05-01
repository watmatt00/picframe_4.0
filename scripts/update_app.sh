#!/bin/bash
# Idempotent post-pull updater. Run after every git pull to apply service file
# changes, new apt packages, and enable new services. Safe to run multiple times.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"

LOG()  { echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"; }
WARN() { echo "[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $*" >&2; }

LOG "update_app.sh starting (project: $PROJECT_DIR)"

# ── Step 1: APT packages ───────────────────────────────────────────────────────
# Add packages here as new features require them.
APT_PACKAGES=(
    python3-gi
    python3-gi-cairo
    gir1.2-gtk-3.0
)

MISSING=()
for pkg in "${APT_PACKAGES[@]}"; do
    dpkg -l "$pkg" 2>/dev/null | grep -q '^ii' || MISSING+=("$pkg")
done

if [[ ${#MISSING[@]} -gt 0 ]]; then
    LOG "Missing packages: ${MISSING[*]} — attempting install..."
    if sudo -n apt-get install -y "${MISSING[@]}" 2>/dev/null; then
        LOG "  Packages installed."
    else
        WARN "Could not install packages (no passwordless sudo). Run manually:"
        WARN "  sudo apt-get install -y ${MISSING[*]}"
    fi
else
    LOG "APT packages: all present."
fi

# ── Step 2: Systemd user service/timer files ───────────────────────────────────
mkdir -p "$SYSTEMD_USER_DIR"
RELOAD_NEEDED=false
CHANGED_SERVICES=()

for src in "$PROJECT_DIR/systemd/"*.service "$PROJECT_DIR/systemd/"*.timer; do
    [[ -f "$src" ]] || continue
    name="$(basename "$src")"
    dest="$SYSTEMD_USER_DIR/$name"
    if ! diff -q "$src" "$dest" > /dev/null 2>&1; then
        cp "$src" "$dest"
        LOG "  Updated: $name"
        RELOAD_NEEDED=true
        # Track base service name (strip .service/.timer) for restart logic
        base="${name%.service}"
        base="${base%.timer}"
        CHANGED_SERVICES+=("$base")
    fi
done

if $RELOAD_NEEDED; then
    systemctl --user daemon-reload
    LOG "systemd user daemon reloaded."
else
    LOG "Systemd service files: no changes."
fi

# ── Step 3: Enable managed services/timers ─────────────────────────────────────
# Add new managed services here as they are introduced.
MANAGED_SERVICES=(picframe-api picframe-lights)
MANAGED_TIMERS=(picframe-sync)

for svc in "${MANAGED_SERVICES[@]}"; do
    unit="$svc.service"
    [[ -f "$SYSTEMD_USER_DIR/$unit" ]] || continue
    if ! systemctl --user is-enabled --quiet "$unit" 2>/dev/null; then
        [[ "$unit" == "picframe-api.service" ]] && continue  # caller handles API start
        systemctl --user enable --now "$unit"
        LOG "  Enabled and started: $unit"
    fi
done

for tmr in "${MANAGED_TIMERS[@]}"; do
    unit="$tmr.timer"
    [[ -f "$SYSTEMD_USER_DIR/$unit" ]] || continue
    if ! systemctl --user is-enabled --quiet "$unit" 2>/dev/null; then
        systemctl --user enable "$unit"
        LOG "  Enabled: $unit"
    fi
done

# ── Step 4: Restart changed services ──────────────────────────────────────────
# picframe-api is excluded — the caller (API update flow) handles that restart.
for base in "${CHANGED_SERVICES[@]}"; do
    [[ "$base" == "picframe-api" ]] && continue
    unit="$base.service"
    if systemctl --user is-active --quiet "$unit" 2>/dev/null; then
        systemctl --user restart "$unit"
        LOG "  Restarted: $unit"
    fi
done

# ── Step 5: picframe config.yaml migrations ───────────────────────────────────
# Idempotent patches to ~/picframe_data/config/configuration.yaml.
PCONF="$HOME/picframe_data/config/configuration.yaml"
if [[ -f "$PCONF" ]]; then
    python3 - "$PCONF" <<'PYEOF'
import sys, yaml
p = sys.argv[1]
with open(p) as f:
    cfg = yaml.safe_load(f) or {}
changed = False
# Enable Pi3D HTTP API — required for current-image preview and source switching
if not cfg.get("http", {}).get("use_http", False):
    cfg.setdefault("http", {})["use_http"] = True
    changed = True
if changed:
    with open(p, "w") as f:
        yaml.safe_dump(cfg, f, default_flow_style=False)
    print(f"Config migrations applied to {p}")
else:
    print(f"Config migrations: no changes needed.")
PYEOF
    # Restart picframe if config changed (python3 above exits 0 regardless)
    if grep -q "use_http: true" "$PCONF" 2>/dev/null; then
        if systemctl --user is-active --quiet picframe.service 2>/dev/null; then
            systemctl --user restart picframe.service
            LOG "  Restarted picframe.service after config migration."
        fi
    fi
else
    LOG "picframe config not found at $PCONF — skipping migrations."
fi

LOG "update_app.sh complete."

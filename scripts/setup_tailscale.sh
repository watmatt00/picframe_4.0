#!/bin/bash
# PicFrame 4.0 - Tailscale Funnel Setup
# Sets up Tailscale and enables Funnel for remote access

set -euo pipefail

echo "==================================="
echo "Tailscale Funnel Setup"
echo "==================================="

# Check if Tailscale is installed
if ! command -v tailscale &> /dev/null; then
    echo "Tailscale not found. Installing..."
    curl -fsSL https://tailscale.com/install.sh | sh
fi

# Check Tailscale status
echo ""
echo "Checking Tailscale status..."
if ! tailscale status &> /dev/null; then
    echo "Tailscale not connected. Starting authentication..."
    sudo tailscale up
fi

# Get current hostname
HOSTNAME=$(tailscale status --json | python3 -c "import sys, json; print(json.load(sys.stdin)['Self']['DNSName'].rstrip('.'))")
echo "Tailscale hostname: $HOSTNAME"

# Enable HTTPS
echo ""
echo "Enabling HTTPS certificates..."
sudo tailscale set --https

# Set up Funnel
echo ""
echo "Setting up Funnel..."
echo "Note: Funnel must be enabled in the Tailscale admin console first."
echo "Visit: https://login.tailscale.com/admin/dns"
echo ""
read -p "Have you enabled Funnel in the admin console? [y/N] " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Please enable Funnel first, then run this script again."
    exit 1
fi

# Configure Funnel to forward to local API
echo ""
echo "Configuring Funnel to forward port 443 to localhost:8000..."
sudo tailscale funnel 443 / http://localhost:8000

# Show status
echo ""
echo "==================================="
echo "Funnel Status"
echo "==================================="
tailscale funnel status

echo ""
echo "Setup complete!"
echo ""
echo "Your frame is now accessible at:"
echo "  https://$HOSTNAME"
echo ""
echo "This URL will be embedded in pairing QR codes."

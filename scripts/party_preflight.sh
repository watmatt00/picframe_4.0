#!/usr/bin/env bash
# Runs all party setup preflight checks and reports pass/fail.
# Safe to run at any time — makes NO changes to the system.
#
# Usage:
#   bash scripts/party_preflight.sh

set -euo pipefail
source "$(dirname "$0")/party_lib.sh"
run_preflight --report-only

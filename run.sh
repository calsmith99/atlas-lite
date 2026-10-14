#!/bin/bash
# Start the dashboard. ATLAS_VAULT, ATLAS_PORT etc. are described at the top of server.py and in README.md.
set -euo pipefail
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { echo "Run ./setup.sh first."; exit 1; }
export ATLAS_PORT="${ATLAS_PORT:-11700}"
if [ "${ATLAS_OPEN:-}" = 1 ]; then
  ( sleep 2; open "http://localhost:$ATLAS_PORT" 2>/dev/null || xdg-open "http://localhost:$ATLAS_PORT" ) >/dev/null 2>&1 &
fi
exec .venv/bin/python server.py

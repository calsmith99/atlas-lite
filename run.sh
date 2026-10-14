#!/bin/bash
# Start the dashboard. ATLAS_VAULT, ATLAS_PORT etc. are described at the top of server.py and in README.md.
set -euo pipefail
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { echo "Run ./setup.sh first."; exit 1; }
# The server builds/refreshes the code graph itself at start (cached; Graphify is re-run only when a repo's output is
# missing or over a day old). Skip cleanly when no repos are set or Graphify was not installed.
if [ -n "${ATLAS_CODE_REPOS:-}" ] && [ ! -x .venv-graphify/bin/graphify ]; then
  echo "ATLAS_CODE_REPOS is set but Graphify is not installed; run ./setup.sh. Starting without the code globe."
  unset ATLAS_CODE_REPOS
fi
export ATLAS_PORT="${ATLAS_PORT:-11700}"
if [ "${ATLAS_OPEN:-}" = 1 ]; then
  ( sleep 2; open "http://localhost:$ATLAS_PORT" 2>/dev/null || xdg-open "http://localhost:$ATLAS_PORT" ) >/dev/null 2>&1 &
fi
exec .venv/bin/python server.py

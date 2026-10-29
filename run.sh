#!/bin/bash
# Start Atlas Lite and open it in your browser. Needs only Python 3 and either Claude Code or Codex on your PATH.
cd "$(dirname "$0")" || exit 1
ATLAS_OPEN="${ATLAS_OPEN:-1}" exec python3 atlas.py

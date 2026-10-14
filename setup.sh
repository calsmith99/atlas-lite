#!/bin/bash
# One-off setup. Creates a Python venv here and, if it doesn't exist, the notes vault from vault-template/.
# Never overwrites an existing vault and never touches ~/.claude: per-session instructions and settings are
# passed to Claude Code on its command line by the dashboard (prompts/session.md and settings.json).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
VAULT="${ATLAS_VAULT:-$HOME/Atlas Vault}"

command -v claude >/dev/null || echo "Note: 'claude' (Claude Code) is not on your PATH yet. Install it before starting a session."

if [ ! -x "$HERE/.venv/bin/python" ]; then
  python3 -m venv "$HERE/.venv"
fi
"$HERE/.venv/bin/pip" install --quiet -r "$HERE/requirements.txt"
echo "Python environment ready in $HERE/.venv"

if [ -e "$VAULT" ]; then
  echo "Vault already exists at $VAULT, leaving it alone."
else
  mkdir -p "$(dirname "$VAULT")"
  cp -R "$HERE/vault-template" "$VAULT"
  echo "Created an empty vault at $VAULT; the first session asks what you use Atlas for and sets up its structure. In Obsidian use 'Open folder as vault' on it."
fi

#!/bin/bash
# One-off setup. Creates a Python venv here (plus .venv-graphify for the code globe) and, if it doesn't exist, the notes vault from vault-template/.
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

# Separate venv for Graphify (AST-only code graph, no LLM or API key). Pinned; kept apart from .venv.
if [ ! -x "$HERE/.venv-graphify/bin/python" ]; then
  python3 -m venv "$HERE/.venv-graphify"
fi
if "$HERE/.venv-graphify/bin/pip" install --quiet "graphifyy==0.9.90"; then
  echo "Graphify ready in $HERE/.venv-graphify"
else
  echo "Warning: could not install graphifyy; the code globe will be unavailable until you re-run ./setup.sh." >&2
fi

if [ -e "$VAULT" ]; then
  echo "Vault already exists at $VAULT, leaving it alone."
else
  mkdir -p "$(dirname "$VAULT")"
  cp -R "$HERE/vault-template" "$VAULT"
  echo "Created an empty vault at $VAULT; the first session asks what you use Atlas for and sets up its structure. In Obsidian use 'Open folder as vault' on it."
fi

# Code globe: which repos to show (saved in atlas.local.json, gitignored; Atlas can change it later on request).
CONF="$HERE/atlas.local.json"
if [ -e "$CONF" ]; then
  echo "Repo list already saved in $CONF, leaving it alone."
else
  printf "Folder that holds your repos (Enter to skip): "
  DIR=""
  read -r DIR || true
  case "$DIR" in "~"*) DIR="$HOME${DIR#\~}" ;; esac
  if [ -n "$DIR" ] && [ -d "$DIR" ]; then
    DIR="$(cd "$DIR" && pwd)"
    json=""; n=0
    for d in "$DIR"/*/; do
      d="${d%/}"
      if [ -e "$d/.git" ]; then
        esc="$(printf '%s' "$d" | sed 's/\\/\\\\/g; s/"/\\"/g')"
        json="$json${json:+, }\"$esc\""
        n=$((n + 1))
      fi
    done
    if [ "$n" -gt 0 ]; then
      printf '{"repos": [%s]}\n' "$json" > "$CONF"
      echo "Saved $n repos to $CONF (edit it, or ask Atlas, to change the list)."
    else
      echo "No git repos found directly inside $DIR; nothing saved."
    fi
  elif [ -n "$DIR" ]; then
    echo "No such folder: $DIR; skipping."
  fi
fi

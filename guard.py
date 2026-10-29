#!/usr/bin/env python3
"""Claude Code PreToolUse hook: notes are written through the vault tools, not Write or Edit.

    python3 guard.py <vault>

Passed to Claude on the command line for each turn (never installed in ~/.claude). Reads the hook JSON on stdin and exits 2
with a reason, which Claude shows to the model, when a Write, Edit or NotebookEdit would touch a Markdown note in the vault.
"""
import json
import sys
from pathlib import Path

vault = Path(sys.argv[1]).resolve()
try:
    data = json.load(sys.stdin)
    target = (data.get("tool_input") or {}).get("file_path") or (data.get("tool_input") or {}).get("notebook_path") or ""
    p = Path(target).expanduser()
    p = (Path(data.get("cwd") or ".") / p) if not p.is_absolute() else p
    p = p.resolve()
except Exception:
    sys.exit(0)
if vault in p.parents and p.suffix == ".md" and p.name not in ("CLAUDE.md", "AGENTS.md") and p.relative_to(vault).parts[0] != ".claude":
    print("Notes in this vault are written with the vault tools, which check the rules: use mcp__vault__new_note to get the "
          "template, mcp__vault__write_note to create a note, mcp__vault__edit_note to change one, mcp__vault__append_log for "
          "the diary. Do not use Write or Edit on a note.", file=sys.stderr)
    sys.exit(2)
sys.exit(0)

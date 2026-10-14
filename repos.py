"""The saved list of code repos for the code globe and for Claude's --add-dir.

Stored in `atlas.local.json` in the install folder (gitignored): {"repos": ["/abs/path", ...]}.
`ATLAS_CODE_REPOS` (colon-separated) overrides the file when set. Read fresh each call, so edits apply without a restart.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

CONFIG = Path(os.environ.get("ATLAS_CONFIG", Path(__file__).resolve().parent / "atlas.local.json")).expanduser()


def load_repos() -> list[str]:
    env = os.environ.get("ATLAS_CODE_REPOS", "")
    if env.strip():
        raw = [p for p in env.split(":") if p]
    else:
        try:
            raw = json.loads(CONFIG.read_text()).get("repos", [])
        except (OSError, ValueError, AttributeError):
            raw = []
    out = []
    for p in raw if isinstance(raw, list) else []:
        if isinstance(p, str) and p.strip():
            q = str(Path(p).expanduser())
            if Path(q).is_dir() and q not in out:
                out.append(q)
    return out

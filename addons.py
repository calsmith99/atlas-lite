"""Add-ons: folders under addons/ that extend the dashboard. See addons/README.md for the convention.

addons/<name>/addon.json   {"title": "...", "panel": "panel.js", "routes": "routes.py", "skill": "SKILL.md"}
  panel   an ES module served at /addons/<name>/panel.js exporting `mount(el, api)`; the page gives it a panel
  routes  a Python file with `setup(app, ctx)` that may add aiohttp routes (under /api/addons/<name>/)
  skill   markdown appended to every dashboard-driven session's system prompt
Every part is optional; a folder with no addon.json is ignored.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


class Addons:
    def __init__(self, root: Path):
        self.dir = root / "addons"
        self.found: dict[str, dict] = {}
        for d in sorted(self.dir.iterdir() if self.dir.is_dir() else []):
            f = d / "addon.json"
            if not f.is_file():
                continue
            try:
                m = json.loads(f.read_text())
            except ValueError as e:
                print(f"add-on {d.name}: bad addon.json ({e})", flush=True)
                continue
            m["name"] = d.name
            m.setdefault("title", d.name)
            self.found[d.name] = m

    def listing(self) -> list[dict]:
        return [{"name": n, "title": m["title"], "panel": f"/addons/{n}/{m['panel']}" if m.get("panel") else None}
                for n, m in self.found.items()]

    def prompts(self) -> str:
        out = []
        for n, m in self.found.items():
            p = self.dir / n / m["skill"] if m.get("skill") else None
            if p and p.is_file():
                out.append(p.read_text().strip())
        return "\n\n".join(out)

    def setup(self, app, ctx: dict):
        for n, m in self.found.items():
            if not m.get("routes"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(f"atlas_addon_{n}", self.dir / n / m["routes"])
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                mod.setup(app, ctx)
            except Exception as e:  # noqa: BLE001
                print(f"add-on {n}: routes failed to load ({e})", flush=True)

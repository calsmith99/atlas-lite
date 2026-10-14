# Add-ons

An add-on is a folder here that extends the dashboard without touching its core. Nothing ships in this folder
except this file. Every part is optional; a folder without an `addon.json` is ignored.

```
addons/
  my-addon/
    addon.json     {"title": "My add-on", "panel": "panel.js", "routes": "routes.py", "skill": "SKILL.md"}
    panel.js       a UI panel
    routes.py      backend routes
    SKILL.md       instructions for Claude
```

**Panel** (`panel`): an ES module served at `/addons/my-addon/panel.js` that exports `mount(el, api)`. `el` is an
empty panel in the bottom-right corner; render into it. `api` offers `api.on("reply" | "delta", fn)` to watch
Claude's replies, `api.send(text)` to write to the shown session, `api.session()` for its id, and
`api.touch(noteIds)` to light notes on the globe.

**Routes** (`routes`): a Python file with `setup(app, ctx)`, called once at startup. `app` is the aiohttp
application; add routes under `/api/addons/my-addon/`. `ctx` has `vault` (Path), `broadcast(msg)` (push a JSON
message to every open page), `sessions` and `root`.

**Skill** (`skill`): markdown appended to the system prompt of every session the dashboard drives (through
`--append-system-prompt`). Nothing is installed into `~/.claude`, so it applies to dashboard sessions only.

Restart the server after adding or changing an add-on.

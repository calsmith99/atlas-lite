# Atlas baseline

A small dashboard for working with Claude Code: type to a session and watch the reply stream in, switch between
sessions from a row of medallions under the conversation, and watch a globe of your notes light up as sessions
read and edit them. It drives the real `claude` CLI headless, so every session stays an ordinary Claude Code
session you can `claude --resume <id>` in a terminal.

## Install (macOS and Linux)

Needs Python 3.10+ and [Claude Code](https://claude.com/claude-code) on your PATH, already logged in.

```sh
./setup.sh      # creates .venv, .venv-graphify (graphifyy 0.9.90) and, if absent, an empty vault from vault-template/
./run.sh        # http://localhost:11700
```

Setup never writes to `~/.claude` and never overwrites an existing vault. Per-session instructions
(`prompts/session.md`) and settings (`settings.json`) go on each `claude` command line. Opening the page
needs internet once for fonts, three.js and marked from CDNs.

Configuration is by environment variable: `ATLAS_VAULT` (default `~/Atlas Vault`), `ATLAS_PORT` (11700),
`ATLAS_RECENT_HOURS` (6), `ATLAS_PERMISSION_MODE` (`acceptEdits`; a headless turn cannot ask, so tools beyond
that mode are refused), `ATLAS_DEFAULT_CWD`, `ATLAS_MODEL`, `ATLAS_CLAUDE` (path to the binary),
`ATLAS_CODE_GRAPH`, `ATLAS_CODE_REPOS`, `ATLAS_CODE_CACHE`, `ATLAS_VOICE`. The server listens on 127.0.0.1 only and rejects cross-site requests.

## Using it

- **Selector** (under the conversation): one medallion per session from the last few hours. A working session
  is lit gold with a turning arc. Click one to show it.
- **New session**: the `+` medallion; give a working folder and press Begin, then type.
- **Older session**: the `+` medallion also lists older ones; click to pick one up and continue it.
- **Type** in the box and press Enter. Text streams in as Claude writes it. One driver at a time: while the
  dashboard runs a turn the box is locked, and a session another process just wrote to is refused.
- **Globe**: your vault, one star per note. Any note a session reads or edits (from any terminal too) lights up.
  The flip button at top right turns the globe to the next graph source.

## Layout

| Path | What |
| ---- | ---- |
| `server.py` | web server, WebSocket, config |
| `sessions.py` | follows `~/.claude/projects/*/*.jsonl`, turns lines into entries and note touches |
| `driver.py` | runs one headless `claude -p` turn per message (`--session-id` / `--resume`) |
| `graphs.py` | graph sources for the globe: notes (always), optional JSON file (`ATLAS_CODE_GRAPH`) |
| `addons.py`, `addons/` | add-on loader and [convention](addons/README.md) |
| `voice/` | optional [voice hook](voice/README.md) |
| `dashboard/` | the page |
| `vault-template/` | neutral starting vault copied by `setup.sh`: general rules only, no folders. The first session asks what you use Atlas for and designs the structure into its `CLAUDE.md` |

## Graph sources

`graphs.py` defines `GraphSource` (`id`, `label`, `load() -> {"nodes": [...], "links": [...]}`). Point
`ATLAS_CODE_GRAPH` at a JSON file of that shape (or a Graphify `graph.json`, which is mapped automatically; see [docs/graphify-test.md](docs/graphify-test.md)) and a second globe
appears behind the flip button. Nodes need `id` and may carry `name`, `folder`, `blurb`; links are
`{"source": id, "target": id}`.

`ATLAS_CODE_REPOS=/path/a:/path/b ./run.sh` (setup installs Graphify; with the variable unset the code globe is simply skipped; the first start builds the graph, later starts reuse it for a day) builds one combined code globe (repo = constellation, file = star, click a file for its functions) with `scripts/build_code_graph.py`; see [docs/graphify-test.md](docs/graphify-test.md).

`?graph=<id>` on the page URL opens a given graph first (e.g. `/?graph=code`).

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

`setup.sh` also asks once for the folder that holds your repos (Enter to skip) and saves the git repos directly inside it to `atlas.local.json` (gitignored; `{"repos": ["/abs/path"]}`). Edit that file, or ask Atlas, to add or remove repos: the server notices within seconds and rebuilds the code globe in the background, and each repo is given to Claude sessions with `--add-dir`. No environment variables are needed; `ATLAS_CODE_REPOS=/a:/b` still overrides the file if set.

Setup never writes to `~/.claude` and never overwrites an existing vault. Per-session instructions
(`prompts/session.md`) and settings (`settings.json`) go on each `claude` command line. Opening the page
needs internet once for fonts, three.js and marked from CDNs.

Configuration is by environment variable: `ATLAS_VAULT` (default `~/Atlas Vault`), `ATLAS_PORT` (11700),
`ATLAS_RECENT_HOURS` (6), `ATLAS_PERMISSION_MODE` (`acceptEdits`; tools needing approval show a permission card), `ATLAS_DEFAULT_CWD`, `ATLAS_MODEL`, `ATLAS_CLAUDE` (path to the binary),
`ATLAS_CODE_GRAPH`, `ATLAS_CODE_CACHE`, `ATLAS_VOICE` (optional; `ATLAS_CODE_REPOS` overrides the saved repo list). The server listens on 127.0.0.1 only and rejects cross-site requests.

## Using it

- **Selector** (under the conversation): one medallion per session from the last few hours. A working session
  is lit gold with a turning arc. Click one to show it.
- **New session**: the `+` medallion; give a working folder and press Begin, then type.
- **Older session**: the `+` medallion also lists older ones; click to pick one up and continue it.
- **Type** in the box and press Enter. Text streams in as Claude writes it. While it is working, the box stays
  available and Send becomes **Send correction**: this interrupts the turn, waits for it to stop, then sends your
  correction in the same session. **Stop** interrupts without a follow-up. Completed actions are not rolled back.
  If Claude does not acknowledge interruption within five seconds, Atlas terminates its process group and resumes
  the correction in a fresh process using the same saved session.
- **Paste images** directly into the chat box. Thumbnails let you remove them before sending; images can be sent
  alone, with text, or as a mid-task correction. Draft images remain attached if sending fails and stay with their
  selected session when you switch conversations. Up to four PNG/JPEG/GIF/WebP images, 4 MB each and 12 MB total;
  image content goes to Claude as native image blocks and appears in saved conversation history.
- **Permissions and questions** appear in the shared middle frame. Review the exact tool input before choosing
  **Allow once** or **Deny**. Structured questions support choices and free text. They wait for your answer with no
  timeout and reappear after a page reload. Stopping cancels outstanding requests, so stale buttons cannot approve
  a later turn. The configured permission mode still governs actions already allowed by Claude.
- **Status** at top right separates manual listening/input state from Claude's work, including connection loss.
  **Usage** shows actual reported five-hour/weekly limits, reset times, token counts and session cost. Windows
  Claude has not reported say so; there is no credential scraping or invented quota.
- **Copy code** opens a central popup for fenced code blocks. New replies open it automatically; older replies have
  a Copy code button. **Preview file** and local file links open text, Markdown, PNG/JPEG/GIF/WebP images and PDFs
  in that same frame. Files are restricted to the selected session's working folder, configured repos and vault;
  text previews are limited to 1 MB, other previews to 32 MB. Markdown is sanitized; raw HTML/SVG is shown as text.
- **Session lifetime**: each dashboard-driven Claude process stays open while Atlas runs, including between turns.
  Stop Atlas before resuming that same session in a terminal. A session recently written by another process is
  refused; that short guard is not a cross-application ownership lock. Several independent sessions can run at once.
- **Globe**: your vault, one star per note. Any note a session reads or edits (from any terminal too) lights up.
  The flip button at top right turns the globe to the next graph source.

## Layout

| Path | What |
| ---- | ---- |
| `server.py` | web server, WebSocket, config |
| `sessions.py` | follows `~/.claude/projects/*/*.jsonl`, turns lines into entries and note touches |
| `driver.py` | keeps Claude stream sessions open; bridges permissions, questions, stop and corrections |
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

The repos in `atlas.local.json` (or `ATLAS_CODE_REPOS=/path/a:/path/b`; with neither, the code globe is skipped; the first build runs in the background, later ones reuse per-repo output for a day; reload the page to see a new globe) build one combined code globe (repo = constellation, file = star, click a file for its functions) with `scripts/build_code_graph.py`; see [docs/graphify-test.md](docs/graphify-test.md).

`?graph=<id>` on the page URL opens a given graph first (e.g. `/?graph=code`).

## Checks

Run `.venv/bin/python -m unittest discover -s tests -v` for subprocess and HTTP checks. They use a local fake
Claude stream peer; they do not spend model tokens or execute tools. For the optional browser smoke check,
install Playwright in a test environment, install its Chromium browser, then run `python tests/ui_smoke.py`.
The browser uses fixture traffic and checks stop/correction requests, questions, permission restoration, copy
popups, sanitized previews and desktop/mobile layouts. Set `ATLAS_TEST_SCREENSHOT` to save a screenshot.
Linux validation does not replace a check on the work Mac's installed Claude version.

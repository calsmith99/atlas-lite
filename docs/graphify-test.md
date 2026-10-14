# Graphify test on Pokemon-Ranch

- **Tool:** Graphify (PyPI package `graphifyy`, double y; command `graphify`; MIT). Version 0.9.90, installed in `.venv-graphify/` (gitignored). `graphify install` was not run, so nothing was written to `~/.claude` or any global config.
- **Input:** a copy of `/mnt/nas/projects/Pokemon-Ranch` at `/tmp/pr-copy` (no `.git`, `node_modules`, `.venv`); the live repo was only read.
- **Command:** `.venv-graphify/bin/graphify extract /tmp/pr-copy --code-only --out /tmp/pr-out`. `--code-only` is tree-sitter AST only, with no LLM and no API key. Docs, images and SQL (needs `graphifyy[sql]`) are skipped.
- **Result:** 392 code files, 2944 nodes, 7676 edges (7673 after undirected de-duplication), 129 communities, 5.6 s wall time. Output `/tmp/pr-out/graphify-out/graph.json` (3.1 MB). Community names are placeholders ("Community N"); naming them needs an LLM (`graphify label`), not done.
- **Wiring:** `ATLAS_CODE_GRAPH=/tmp/pr-out/graphify-out/graph.json`. `graphs.py` `JsonFileSource` detects Graphify output and maps nodes to `{id, name=label, folder=first two path folders, tags=[community-N], blurb=file + line}` and edges to undirected unique links. Colour group is the folder (new hash-based palette fallback in `dashboard/app.js`). `/?graph=code` opens the code globe first (test aid). Screenshot: `/tmp/code-globe.png`.
- **Limits:** the "touch" glow for session activity only applies to the notes graph. Non-code files are not in a `--code-only` graph.

## Combined multi-repo globe

`scripts/build_code_graph.py REPO...` (or `ATLAS_CODE_REPOS=a:b:c`) runs `graphify extract <repo> --code-only --out <cache>/<repo>` per repo (cache `ATLAS_CODE_CACHE`, default `.code-cache/`, gitignored; re-run after 1 day or with `--force`) and merges to `<cache>/code-graph.json`: one star per source file (id `repo:path`, `folder` = repo, `symbols` = its functions/classes with line), links between files weighted by the number of function-level links, concept/rationale nodes dropped. `"group": "folder"` makes the front end lay out each repo as its own constellation (no Louvain). Clicking a file star pins a tooltip listing its symbols; click empty sky to close. With `ATLAS_CODE_REPOS` set and no `ATLAS_CODE_GRAPH`, `server.py` builds the graph at startup.

Test with Pokemon-Ranch, Spellcrafter, AlbumCharts, RS-Update-Locked: 360 + 19 + 128 + 128 = 635 file stars, 1301 links, about 14 s cold. Graphify output goes to the cache dir, never into the repos.

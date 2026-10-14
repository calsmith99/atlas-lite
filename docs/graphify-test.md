# Graphify test on Pokemon-Ranch

- **Tool:** Graphify (PyPI package `graphifyy`, double y; command `graphify`; MIT). Version 0.9.90, installed in `.venv-graphify/` (gitignored). `graphify install` was not run, so nothing was written to `~/.claude` or any global config.
- **Input:** a copy of `/mnt/nas/projects/Pokemon-Ranch` at `/tmp/pr-copy` (no `.git`, `node_modules`, `.venv`); the live repo was only read.
- **Command:** `.venv-graphify/bin/graphify extract /tmp/pr-copy --code-only --out /tmp/pr-out`. `--code-only` is tree-sitter AST only, with no LLM and no API key. Docs, images and SQL (needs `graphifyy[sql]`) are skipped.
- **Result:** 392 code files, 2944 nodes, 7676 edges (7673 after undirected de-duplication), 129 communities, 5.6 s wall time. Output `/tmp/pr-out/graphify-out/graph.json` (3.1 MB). Community names are placeholders ("Community N"); naming them needs an LLM (`graphify label`), not done.
- **Wiring:** `ATLAS_CODE_GRAPH=/tmp/pr-out/graphify-out/graph.json`. `graphs.py` `JsonFileSource` detects Graphify output and maps nodes to `{id, name=label, folder=first two path folders, tags=[community-N], blurb=file + line}` and edges to undirected unique links. Colour group is the folder (new hash-based palette fallback in `dashboard/app.js`). `/?graph=code` opens the code globe first (test aid). Screenshot: `/tmp/code-globe.png`.
- **Limits:** the "touch" glow for session activity only applies to the notes graph. Non-code files are not in a `--code-only` graph.

## Scaling to many repos

Run `graphify extract <repo> --code-only --out <dir>/<repo>` per repo (seconds each, cacheable, incremental via `graphify update`), then `graphify merge-graphs a.json b.json --out merged.json` for one cross-repo graph, and point `ATLAS_CODE_GRAPH` at the merged file. Re-run on a timer or `graphify watch`. A few tens of thousands of nodes is the likely limit for the globe's rendering.

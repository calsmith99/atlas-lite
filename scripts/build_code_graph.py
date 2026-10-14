#!/usr/bin/env python3
"""Build the combined code graph for the Atlas "code" globe.

Usage: scripts/build_code_graph.py [--cache DIR] [--out FILE] [--force] REPO [REPO ...]
With no REPO args, repos come from ATLAS_CODE_REPOS (colon-separated paths).

Runs Graphify (AST-only, no LLM) per repo into <cache>/<repo>/ (never inside the repo), then merges to one
file-level graph: a node per source file (folder/group = repo name, `symbols` = its functions/classes), and one
link per pair of files with `weight` = number of function-level links between them. Concept/rationale nodes are dropped.
Graphify is re-run for a repo only when --force is given or its output is missing/older than 1 day.
"""
import argparse, json, os, subprocess, sys, time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
GRAPHIFY = HERE / ".venv-graphify" / "bin" / "graphify"


def run_graphify(repo: Path, cache: Path, force: bool) -> Path:
    out = cache / repo.name
    gj = out / "graphify-out" / "graph.json"
    if force or not gj.is_file() or time.time() - gj.stat().st_mtime > 86400:
        out.mkdir(parents=True, exist_ok=True)
        subprocess.run([str(GRAPHIFY), "extract", str(repo), "--code-only", "--out", str(out)],
                       check=True, stdout=subprocess.DEVNULL)
    return gj


def merge(repos: list[Path], cache: Path, force: bool) -> dict:
    nodes, weights = {}, defaultdict(int)
    for repo in repos:
        name = repo.name
        g = json.loads(run_graphify(repo, cache, force).read_text())
        to_file = {}   # graphify node id -> file node id
        for n in g["nodes"]:
            sf = n.get("source_file")
            if n.get("file_type") != "code" or not sf or isinstance(sf, list):
                continue
            fid = f"{name}:{sf}"
            to_file[n["id"]] = fid
            f = nodes.setdefault(fid, {"id": fid, "name": sf.split("/")[-1], "folder": name, "path": sf, "symbols": []})
            if n.get("label") != f["name"]:   # the file's own node is labelled with its filename
                f["symbols"].append({"label": n.get("label", n["id"]), "loc": n.get("source_location", "")})
        for e in g["links"]:
            a, b = to_file.get(e["source"]), to_file.get(e["target"])
            if a and b and a != b:
                weights[tuple(sorted((a, b)))] += 1
    for f in nodes.values():
        f["symbols"].sort(key=lambda s: int(s["loc"][1:]) if s["loc"][1:].isdigit() else 0)
        f["blurb"] = f"{f['folder']}/{f['path']} - {len(f['symbols'])} symbols"
    return {"nodes": list(nodes.values()), "group": "folder", "vault": "Code",
            "links": [{"source": a, "target": b, "weight": w} for (a, b), w in sorted(weights.items())]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repos", nargs="*")
    ap.add_argument("--cache", default=os.environ.get("ATLAS_CODE_CACHE", str(HERE / ".code-cache")))
    ap.add_argument("--out")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    paths = a.repos or [p for p in os.environ.get("ATLAS_CODE_REPOS", "").split(":") if p]
    if not paths:
        sys.exit("no repos: pass paths or set ATLAS_CODE_REPOS")
    cache = Path(a.cache).expanduser()
    out = Path(a.out) if a.out else cache / "code-graph.json"
    graph = merge([Path(p).expanduser().resolve() for p in paths], cache, a.force)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(graph))
    per = defaultdict(int)
    for n in graph["nodes"]:
        per[n["folder"]] += 1
    print(out, dict(per), len(graph["nodes"]), "files", len(graph["links"]), "links")


if __name__ == "__main__":
    main()

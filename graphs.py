"""Graph sources for the globe slot.

The globe shows one graph at a time and the page can flip between sources. A source is anything with
`id`, `label`, and `load() -> {"nodes": [...], "links": [...]}`. Nodes need `id`, `name`; they may carry
`folder` (colour group), `tags`, `blurb`. Links are `{"source": id, "target": id}`.

Registered here: the notes vault (always) and an optional code graph read from a JSON file in the same shape
(`ATLAS_CODE_GRAPH=/path/graph.json`), which is where Graphify output will plug in later. Add a source by
subclassing GraphSource and adding it in `build_sources()`.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

SKIP_DIRS = {".git", ".obsidian", ".trash", ".claude"}
LINK_RE = re.compile(r"\[\[([^\]|#^]+)(?:[#^][^\]|]*)?(?:\|[^\]]*)?\]\]")


class GraphSource:
    id = "base"
    label = "Graph"

    def load(self) -> dict:
        raise NotImplementedError

    def info(self) -> dict:
        return {"id": self.id, "label": self.label}


class NotesSource(GraphSource):
    """The vault: one star per note, one link per wikilink."""
    id, label = "notes", "Notes"

    def __init__(self, vault: Path):
        self.vault = vault
        self.stamp = None
        self.graph = {"nodes": [], "links": []}
        self.by_name: dict[str, str] = {}   # lower-case basename or alias -> node id

    def _files(self):
        for root, dirs, files in os.walk(self.vault):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            for f in files:
                if f.endswith(".md") and f != "CLAUDE.md":
                    yield Path(root) / f

    def load(self) -> dict:
        files = sorted(self._files())
        stamp = tuple((str(p), p.stat().st_mtime) for p in files)
        if stamp == self.stamp:
            return self.graph
        nodes, texts, by_name = [], {}, {}
        for p in files:
            rel = p.relative_to(self.vault)
            nid = str(rel.with_suffix(""))
            text = p.read_text(errors="replace")
            texts[nid] = text
            fm = re.match(r"^---\n(.*?)\n---", text, re.S)
            tags = re.search(r"^tags:\s*\[(.*?)\]", fm.group(1), re.M) if fm else None
            aliases = re.search(r"^aliases:\s*\[(.*?)\]", fm.group(1), re.M) if fm else None
            opener = re.search(r"^_(.+?)_\s*$", text, re.M)
            nodes.append({"id": nid, "name": p.stem, "folder": rel.parts[0] if len(rel.parts) > 1 else "",
                          "tags": [t.strip() for t in tags.group(1).split(",") if t.strip()] if tags else [],
                          "blurb": opener.group(1)[:200] if opener else ""})
            by_name[p.stem.lower()] = nid
            for a in (aliases.group(1).split(",") if aliases else []):
                by_name.setdefault(a.strip().strip("'\"").lower(), nid)
        links = set()
        for nid, text in texts.items():
            for m in LINK_RE.finditer(text):
                target = by_name.get(m.group(1).strip().split("/")[-1].lower())
                if target and target != nid:
                    links.add(tuple(sorted((nid, target))))
        self.stamp, self.by_name = stamp, by_name
        self.graph = {"nodes": nodes, "links": [{"source": a, "target": b} for a, b in sorted(links)],
                      "vault": self.vault.name}
        return self.graph

    def note_for_path(self, path: str) -> str | None:
        try:
            rel = Path(path).expanduser().resolve().relative_to(self.vault.resolve())
        except (ValueError, OSError):
            return None
        return str(rel.with_suffix("")) if rel.suffix == ".md" else None

    def notes_in(self, text: str) -> list[str]:
        """Notes named as `<Name>.md` anywhere in a shell command."""
        found = []
        for m in re.finditer(r"([^/\"'`]+?)\.md\b", text):
            nid = self.by_name.get(m.group(1).strip().lower())
            if nid and nid not in found:
                found.append(nid)
        return found


class JsonFileSource(GraphSource):
    """A graph precomputed into a JSON file (`{"nodes": [...], "links": [...]}`), e.g. a code graph."""

    def __init__(self, id: str, label: str, path: Path):
        self.id, self.label, self.path = id, label, path

    def load(self) -> dict:
        g = json.loads(self.path.read_text())
        g.setdefault("nodes", [])
        g.setdefault("links", [])
        for n in g["nodes"]:
            n.setdefault("name", str(n["id"]).split("/")[-1])
            n.setdefault("folder", "")
        g.setdefault("vault", self.label)
        return g


def build_sources(vault: Path) -> dict[str, GraphSource]:
    sources: dict[str, GraphSource] = {"notes": NotesSource(vault)}
    code = os.environ.get("ATLAS_CODE_GRAPH")
    if code and Path(code).expanduser().is_file():
        sources["code"] = JsonFileSource("code", "Code", Path(code).expanduser())
    return sources

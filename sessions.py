"""Claude Code sessions as the dashboard sees them.

Claude Code appends every turn to ~/.claude/projects/<cwd-slug>/<session-id>.jsonl as it happens. Whoever is
driving a session (a terminal, the Desktop app, or this dashboard's driver), that file is the single source of
truth: we follow it, turn its lines into page entries, and note which vault notes each tool call touched.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path

from graphs import NotesSource

_TAG = re.compile(r"^\s*\((?:spoken|typed|sent) via [^)]*\)\s*", re.I)


def first_line(text: str) -> str:
    """A message's first line for a title, minus a leading '(spoken via Atlas)' style tag."""
    return _TAG.sub("", text.strip()).splitlines()[0][:80] if text.strip() else ""

PROJECTS = Path.home() / ".claude/projects"
HISTORY = 300          # transcript entries kept per session
RESULT_CHARS = 600     # tool output kept per result
WORKING_SECS = 90      # an unfinished turn that wrote within this is "working"
WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
WRITE_CMD = re.compile(r"git (add|commit)|sed -i|>\s*\S+\.md|\.write\(")


def tool_summary(inp: dict) -> str:
    for key in ("description", "command", "file_path", "pattern", "query", "question", "skill", "text", "prompt"):
        if inp.get(key):
            return str(inp[key]).splitlines()[0][:200]
    return ""


def result_text(content) -> str:
    if isinstance(content, list):
        content = "\n".join(b.get("text", "") for b in content if b.get("type") == "text")
    return str(content or "")


def entries(e: dict, notes: NotesSource) -> list[dict]:
    """A transcript line as page entries: user / claude / tool / result."""
    if e.get("isSidechain") or e.get("isMeta"):
        return []
    typ, msg = e.get("type"), e.get("message") or {}
    content, ts = msg.get("content"), e.get("timestamp")
    out = []
    if typ == "user":
        if isinstance(content, str):
            if content.lstrip().startswith("<"):  # system reminders, command wrappers
                return []
            return [{"kind": "user", "text": content, "ts": ts}]
        image_blocks = [b.get("source") for b in content or [] if b.get("type") == "image" and isinstance(b.get("source"), dict)]
        user_text = "\n".join(b.get("text", "") for b in content or [] if b.get("type") == "text" and not b.get("text", "").lstrip().startswith("<"))
        if image_blocks:
            # Do not interpret image contents or put base64 in titles/tool summaries.
            from messages import image_source
            images = []
            for source in image_blocks[:4]:
                try:
                    images.append(image_source(source)[0])
                except ValueError:
                    continue
            out.append({"kind":"user", "text":user_text, "images":images, "ts":ts})
        for b in content or []:
            if b.get("type") == "tool_result":
                text = result_text(b.get("content")).strip()
                out.append({"kind": "result", "id": b.get("tool_use_id"), "error": bool(b.get("is_error")),
                            "text": text[:RESULT_CHARS], "lines": text.count("\n") + 1 if text else 0, "ts": ts})
            elif not image_blocks and b.get("type") == "text" and not b.get("text", "").lstrip().startswith("<"):
                out.append({"kind": "user", "text": b["text"], "ts": ts})
    elif typ == "assistant":
        for b in content or []:
            if b.get("type") == "text" and b.get("text", "").strip():
                out.append({"kind": "claude", "text": b["text"].strip(), "ts": ts})
            elif b.get("type") == "tool_use":
                name, inp = b.get("name", ""), b.get("input") or {}
                touched, act = [], "read"
                if inp.get("file_path") and (nid := notes.note_for_path(inp["file_path"])):
                    touched, act = [nid], "edit" if name in WRITE_TOOLS else "read"
                elif name == "Bash" and inp.get("command"):
                    touched = notes.notes_in(inp["command"])
                    if WRITE_CMD.search(inp["command"]):
                        act = "edit"
                out.append({"kind": "tool", "id": b.get("id"), "tool": name.removeprefix("mcp__"),
                            "summary": tool_summary(inp), "notes": touched, "act": act, "ts": ts})
    return out


class Session:
    def __init__(self, path: Path, notes: NotesSource, broadcast):
        self.path, self.id = path, path.stem
        self.notes, self.broadcast = notes, broadcast
        self.history: list[dict] = []
        self.title = self.first = ""
        self.custom = False
        self.cwd = ""
        self.last = path.stat().st_mtime
        self.open = False          # the last entry leaves the turn unfinished (a user message or a tool call)
        self.driving = False       # the dashboard's own driver is running a turn on it
        self.managed = False       # its persistent driver owns idle/working state

    def meta(self) -> dict:
        working = self.driving or (not self.managed and self.open and time.time() - self.last < WORKING_SECS)
        return {"id": self.id, "title": self.title or self.first or self.id[:8], "cwd": self.cwd,
                "last": self.last, "working": working, "driving": self.driving}

    def add(self, line: str, live: bool):
        try:
            e = json.loads(line)
        except ValueError:
            return
        changed = False
        if e.get("type") in ("custom-title", "ai-title"):
            title = e.get("customTitle") or e.get("aiTitle") or ""
            if title and (e["type"] == "custom-title" or not self.custom):   # a name you gave it beats Claude's
                self.title, changed = title, True
                self.custom = self.custom or e["type"] == "custom-title"
        if e.get("cwd") and e["cwd"] != self.cwd:
            self.cwd, changed = e["cwd"], True
        new = entries(e, self.notes)
        for ent in new:
            if ent["kind"] == "user" and not self.first:
                self.first, changed = first_line(ent["text"]) or "Image conversation", True
        if new:
            self.open = new[-1]["kind"] in ("user", "tool", "result")
            self.history = (self.history + new)[-HISTORY:]
        if live:
            self.last = time.time()
            for ent in new:
                self.broadcast({"t": "entry", "session": self.id, "entry": ent})
            if new or changed:
                self.broadcast({"t": "session", "session": self.meta()})


class Sessions:
    def __init__(self, notes_of, broadcast, recent_hours: float):
        self.notes_of = notes_of           # callable returning the notes source (kept late-bound)
        self.broadcast = broadcast
        self.recent_hours = recent_hours
        self.all: dict[str, Session] = {}
        self.pending: dict[str, dict] = {}  # started here, no log file yet

    def _cutoff(self) -> float:
        return time.time() - self.recent_hours * 3600

    def recent(self) -> list[dict]:
        cutoff = self._cutoff()
        out = [s.meta() for s in self.all.values() if s.last >= cutoff or s.driving]
        out += [m for i, m in self.pending.items() if i not in self.all]
        return sorted(out, key=lambda m: -m["last"])

    def touches(self) -> list[dict]:
        cutoff = self._cutoff()
        return [{"notes": e["notes"], "act": e["act"], "ts": e["ts"]}
                for s in self.all.values() if s.last >= cutoff
                for e in s.history if e["kind"] == "tool" and e["notes"]]

    def find_path(self, sid: str) -> Path | None:
        for p in PROJECTS.glob(f"*/{sid}.jsonl"):
            return p
        return None

    def add_pending(self, sid: str, cwd: str) -> dict:
        m = {"id": sid, "title": "New session", "cwd": cwd, "last": time.time(), "working": False,
             "driving": False, "pending": True}
        self.pending[sid] = m
        self.broadcast({"t": "session", "session": m})
        return m

    def adopt(self, sid: str) -> Session | None:
        """Start following a session regardless of age (picked from the older list)."""
        if sid in self.all:
            return self.all[sid]
        path = self.find_path(sid)
        if not path:
            return None
        return self._follow(path)

    def _follow(self, path: Path) -> Session:
        s = self.all[path.stem] = Session(path, self.notes_of(), self.broadcast)
        pending = self.pending.pop(path.stem, None)
        if pending:
            s.driving = pending.get("driving", False)
            s.managed = pending.get("managed", False)
        asyncio.create_task(self.follow(s))
        return s

    def older(self, limit: int = 40) -> list[dict]:
        """Sessions past the recent window, newest first, for picking one up."""
        cutoff, found = self._cutoff(), []
        for p in PROJECTS.glob("*/*.jsonl"):
            try:
                m = p.stat().st_mtime
            except OSError:
                continue
            if m < cutoff and p.stem not in self.all:
                found.append((m, p))
        out = []
        for m, p in sorted(found, reverse=True)[:limit]:
            title = cwd = ""
            try:
                with p.open(errors="replace") as f:
                    for _, line in zip(range(60), f):
                        try:
                            e = json.loads(line)
                        except ValueError:
                            continue
                        cwd = cwd or e.get("cwd", "")
                        if e.get("type") == "user" and not title:
                            c = (e.get("message") or {}).get("content")
                            if isinstance(c, str) and not c.lstrip().startswith("<"):
                                title = first_line(c)
                        if title and cwd:
                            break
            except OSError:
                continue
            out.append({"id": p.stem, "title": title or p.stem[:8], "cwd": cwd, "last": m})
        return out

    async def run(self):
        while True:
            self.notes_of().load()
            cutoff = self._cutoff()
            for path in PROJECTS.glob("*/*.jsonl"):   # subagent logs sit a level deeper and are skipped
                try:
                    if path.stem in self.all:
                        continue
                    if path.stat().st_mtime < cutoff and path.stem not in self.pending:
                        continue
                except OSError:
                    continue
                self._follow(path)
            await asyncio.sleep(2)

    async def follow(self, s: Session):
        with s.path.open(errors="replace") as f:
            buf = ""
            for line in f:       # replay what's already there without broadcasting it as live
                buf += line
                if not buf.endswith("\n"):
                    break
                s.add(buf, live=False)
                buf = ""
            self.broadcast({"t": "session", "session": s.meta()})
            was_working = s.meta()["working"]
            while True:
                chunk = f.readline()
                if chunk:
                    buf += chunk
                    if buf.endswith("\n"):
                        s.add(buf, live=True)
                        buf = ""
                    continue
                working = s.meta()["working"]
                if working != was_working:                     # stopped writing mid-turn: shows as idle
                    self.broadcast({"t": "session", "session": s.meta()})
                was_working = working
                await asyncio.sleep(0.25 if time.time() - s.last < 600 else 2)

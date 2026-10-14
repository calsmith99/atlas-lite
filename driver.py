"""Drive Claude Code headless, one process per turn.

A turn is `claude -p --input-format stream-json --output-format stream-json` fed one user message. The session
is created with `--session-id <uuid>` and continued with `--resume <uuid>`; resuming appends to the same
~/.claude/projects/.../<uuid>.jsonl, so the session stays an ordinary one you can `claude --resume` from a
terminal. Nothing is forked, and nothing is written outside the repo: instructions and settings go on the
command line. Only one turn runs per session at a time, and a session another process is writing to is refused.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
import uuid
from pathlib import Path

from repos import CONFIG, load_repos

CONFLICT_SECS = 8      # a log written this recently, by someone else, means a terminal is driving it


class Driver:
    def __init__(self, root: Path, vault: Path, sessions, broadcast, addon_prompts):
        self.root, self.vault = root, vault
        self.sessions, self.broadcast = sessions, broadcast
        self.addon_prompts = addon_prompts          # callable -> text from add-on skills
        self.claude = os.environ.get("ATLAS_CLAUDE") or shutil.which("claude") or "claude"
        self.mode = os.environ.get("ATLAS_PERMISSION_MODE", "acceptEdits")
        self.model = os.environ.get("ATLAS_MODEL", "")
        self.running: dict[str, asyncio.subprocess.Process] = {}

    def prompt(self) -> str:
        base = (self.root / "prompts/session.md").read_text().replace("{vault}", str(self.vault)).replace("{config}", str(CONFIG))
        extra = self.addon_prompts()
        return base + ("\n\n" + extra if extra else "")

    def command(self, sid: str, new: bool) -> list[str]:
        cmd = [self.claude, "-p", "--input-format", "stream-json", "--output-format", "stream-json",
               "--verbose", "--include-partial-messages", "--permission-mode", self.mode,
               "--settings", str(self.root / "settings.json"), "--add-dir", str(self.vault),
               *[a for r in load_repos() for a in ("--add-dir", r)],
               "--allowedTools", f"Read(/{CONFIG})", f"Edit(/{CONFIG})", f"Write(/{CONFIG})",
               "--append-system-prompt", self.prompt(), "--session-id" if new else "--resume", sid]
        if self.model:
            cmd += ["--model", self.model]
        return cmd

    def start(self, cwd: str | None) -> str:
        """Register a new session (its log appears on the first turn)."""
        cwd = str(Path(cwd or os.environ.get("ATLAS_DEFAULT_CWD") or Path.home()).expanduser())
        if not Path(cwd).is_dir():
            raise ValueError(f"No such folder: {cwd}")
        sid = str(uuid.uuid4())
        self.sessions.add_pending(sid, cwd)
        return sid

    async def send(self, sid: str, text: str) -> None:
        if sid in self.running:
            raise RuntimeError("This session is already working on a turn.")
        pend = self.sessions.pending.get(sid)
        s = self.sessions.adopt(sid) if not pend else None
        if pend:
            new, cwd = self.sessions.find_path(sid) is None, pend["cwd"]
        elif s:
            new, cwd = False, s.cwd or str(Path.home())
            if time.time() - s.path.stat().st_mtime < CONFLICT_SECS:
                raise RuntimeError("Something else wrote to this session a moment ago (a terminal?). "
                                   "One driver at a time: try again when it is idle.")
        else:
            raise RuntimeError("Unknown session.")
        if not Path(cwd).is_dir():
            raise RuntimeError(f"The session's folder no longer exists: {cwd}")
        proc = await asyncio.create_subprocess_exec(
            *self.command(sid, new), cwd=cwd, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, limit=8 * 1024 * 1024)
        self.running[sid] = proc
        self._mark(sid, True)
        asyncio.create_task(self._pump(sid, proc, text))

    def _mark(self, sid: str, on: bool):
        s = self.sessions.all.get(sid)
        if s:
            s.driving = on
            self.broadcast({"t": "session", "session": s.meta()})
        elif sid in self.sessions.pending:
            self.sessions.pending[sid]["driving"] = self.sessions.pending[sid]["working"] = on
            self.broadcast({"t": "session", "session": self.sessions.pending[sid]})

    async def _pump(self, sid: str, proc, text: str):
        err = b""
        try:
            line = json.dumps({"type": "user", "message": {"role": "user", "content": text}})
            proc.stdin.write(line.encode() + b"\n")
            await proc.stdin.drain()
            proc.stdin.close()
            stderr = asyncio.create_task(proc.stderr.read())
            async for raw in proc.stdout:
                try:
                    e = json.loads(raw)
                except ValueError:
                    continue
                if e.get("type") == "stream_event":
                    d = (e.get("event") or {}).get("delta") or {}
                    if d.get("type") == "text_delta" and d.get("text"):
                        self.broadcast({"t": "delta", "session": sid, "text": d["text"]})
                elif e.get("type") == "result" and e.get("is_error"):
                    err = str(e.get("result") or "The turn failed.").encode()
            code = await proc.wait()
            err = err or (await stderr if code else b"")
        except Exception as ex:  # noqa: BLE001
            err = str(ex).encode()
            proc.kill()
        finally:
            self.running.pop(sid, None)
            self.sessions.pending.pop(sid, None) if self.sessions.find_path(sid) else None
            self._mark(sid, False)
            self.broadcast({"t": "turn_end", "session": sid, "error": err.decode(errors="replace").strip()[-400:]})

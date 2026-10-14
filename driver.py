"""Persistent Claude stream sessions, interactive permissions and safe interruption.

Claude's own JSONL remains the transcript. An idle process stays open until Atlas exits;
external sessions are adopted only when idle. Corrections interrupt the active turn and
are sent after its result, never as a second concurrent turn.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import time
import uuid
from pathlib import Path

from repos import CONFIG, load_repos

CONFLICT_SECS = 8


class Driver:
    def __init__(self, root: Path, vault: Path, sessions, broadcast, addon_prompts):
        self.root, self.vault = root, vault
        self.sessions, self.broadcast = sessions, broadcast
        self.addon_prompts = addon_prompts
        self.claude = os.environ.get("ATLAS_CLAUDE") or shutil.which("claude") or "claude"
        self.mode = os.environ.get("ATLAS_PERMISSION_MODE", "acceptEdits")
        self.model = os.environ.get("ATLAS_MODEL", "")
        self.running = {}                 # includes idle, persistent processes
        self.busy = set()
        self.status = {}
        self.permissions = {}             # sid -> request_id -> control request
        self.usage = {}
        self.usage_windows = {}
        self.followups = {}
        self.interrupting = set()
        self.serial = {}
        self.locks = {}
        self.tasks = set()
        self.closing = False
        self.resume_after_stop = set()
        self.controls = {}
        self.initializing = {}

    def _task(self, coro):
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    def prompt(self) -> str:
        base = (self.root / "prompts/session.md").read_text().replace("{vault}", str(self.vault)).replace("{config}", str(CONFIG))
        extra = self.addon_prompts()
        return base + ("\n\n" + extra if extra else "")

    def command(self, sid: str, new: bool) -> list[str]:
        cmd = [self.claude, "-p", "--input-format", "stream-json", "--output-format", "stream-json",
               "--verbose", "--include-partial-messages", "--permission-mode", self.mode,
               "--permission-prompt-tool", "stdio", "--settings", str(self.root / "settings.json"),
               "--add-dir", str(self.vault), *[a for r in load_repos() for a in ("--add-dir", r)],
               "--allowedTools", f"Read(/{CONFIG})", f"Edit(/{CONFIG})", f"Write(/{CONFIG})",
               "--append-system-prompt", self.prompt(), "--session-id" if new else "--resume", sid]
        if self.model:
            cmd += ["--model", self.model]
        return cmd

    def start(self, cwd: str | None) -> str:
        cwd = str(Path(cwd or os.environ.get("ATLAS_DEFAULT_CWD") or Path.home()).expanduser())
        if not Path(cwd).is_dir():
            raise ValueError(f"No such folder: {cwd}")
        sid = str(uuid.uuid4())
        self.sessions.add_pending(sid, cwd)
        return sid

    def snapshot(self):
        return {"status": self.status, "permissions": [p for ps in self.permissions.values() for p in ps.values()],
                "usage": self.usage, "usageWindows": self.usage_windows}

    def _status(self, sid, stage, text):
        self.status[sid] = {"stage": stage, "text": text}
        self.broadcast({"t": "status", "session": sid, **self.status[sid]})

    async def _write(self, sid, obj):
        proc = self.running.get(sid)
        if not proc or proc.returncode is not None:
            raise RuntimeError("Claude is no longer connected. Send your message again to resume.")
        proc.stdin.write((json.dumps(obj) + "\n").encode())
        await proc.stdin.drain()

    async def send(self, sid: str, text: str):
        async with self.locks.setdefault(sid, asyncio.Lock()):
            if sid in self.busy:
                raise RuntimeError("Use Send correction to interrupt the current turn.")
            if sid not in self.running:
                pend = self.sessions.pending.get(sid)
                s = self.sessions.adopt(sid) if not pend else None
                if pend:
                    new, cwd = self.sessions.find_path(sid) is None, pend["cwd"]
                elif s:
                    new, cwd = False, s.cwd or str(Path.home())
                    if sid not in self.resume_after_stop and time.time() - s.path.stat().st_mtime < CONFLICT_SECS:
                        raise RuntimeError("Another process just wrote to this session. Wait until it is idle.")
                else:
                    raise RuntimeError("Unknown session.")
                if not Path(cwd).is_dir():
                    raise RuntimeError(f"The session's folder no longer exists: {cwd}")
                proc = await asyncio.create_subprocess_exec(
                    *self.command(sid, new), cwd=cwd, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE, limit=8 * 1024 * 1024, start_new_session=True)
                self.running[sid] = proc
                self._task(self._pump(sid, proc))
                rid = "init-" + uuid.uuid4().hex
                ready = asyncio.get_running_loop().create_future()
                self.controls[rid] = ready
                self.initializing[sid] = ready
                try:
                    await self._write(sid, {"type": "control_request", "request_id": rid,
                                            "request": {"subtype": "initialize", "hooks": None}})
                    await asyncio.wait_for(ready, 60)
                except (TimeoutError, OSError, RuntimeError) as ex:
                    await self._terminate(proc)
                    raise RuntimeError("Claude could not initialize its interactive session: " + str(ex))
                finally:
                    self.controls.pop(rid, None)
                    self.initializing.pop(sid, None)
            self.resume_after_stop.discard(sid)
            await self._begin(sid, text)

    async def _begin(self, sid, text):
        self.serial[sid] = self.serial.get(sid, 0) + 1
        self.busy.add(sid)
        self._mark(sid, True)
        self._status(sid, "working", "Working on your message")
        try:
            await self._write(sid, {"type": "user", "message": {"role": "user", "content": text}})
        except (OSError, RuntimeError):
            self.busy.discard(sid)
            self._mark(sid, False)
            raise RuntimeError("Claude disconnected before receiving the message. Please send it again.")

    async def interrupt(self, sid, correction=""):
        async with self.locks.setdefault(sid, asyncio.Lock()):
            if sid not in self.busy:
                if correction:
                    raise RuntimeError("The turn has finished. Send this as a new message.")
                return
            if correction:
                self.followups.setdefault(sid, []).append(correction)
            else:
                self.followups.pop(sid, None)
            if sid in self.interrupting:
                return
            self.interrupting.add(sid)
            self._status(sid, "stopping", "Stopping before your correction" if correction else "Stopping the current turn")
            # Cancel pending questions before interrupting, so an old Allow cannot approve a new turn.
            proc = self.running.get(sid)
            if proc:
                self._task(self._stop_fallback(sid, proc, self.serial.get(sid)))
            try:
                for rid in list(self.permissions.get(sid, {})):
                    await self.answer(sid, rid, False, message="The user stopped or corrected this turn.")
                await self._write(sid, {"type": "control_request", "request_id": "stop-" + uuid.uuid4().hex,
                                        "request": {"subtype": "interrupt"}})
            except (RuntimeError, OSError):
                if proc:
                    await self._terminate(proc)

    async def _stop_fallback(self, sid, proc, serial):
        await asyncio.sleep(5)
        if sid in self.interrupting and self.running.get(sid) is proc and self.serial.get(sid) == serial:
            await self._terminate(proc)

    async def _terminate(self, proc):
        if proc.returncode is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            await asyncio.wait_for(proc.wait(), 2)
        except asyncio.TimeoutError:
            os.killpg(proc.pid, signal.SIGKILL)
            await proc.wait()
        except ProcessLookupError:
            pass

    async def answer(self, sid, rid, allow, answers=None, message=""):
        p = self.permissions.get(sid, {}).get(rid)
        if not p:
            raise RuntimeError("This question is no longer waiting for an answer.")
        inp = p["input"]
        if allow and p["tool"] == "AskUserQuestion":
            questions = inp.get("questions", [])
            if not isinstance(answers, dict) or any(not isinstance(answers.get(q["question"]), str) or not answers[q["question"]].strip() for q in questions):
                raise RuntimeError("Answer each question before continuing.")
            inp = {**inp, "answers": answers}
        response = {"behavior": "allow", "updatedInput": inp} if allow else {
            "behavior": "deny", "message": message or "The user declined. Do not retry this action without new instructions."}
        # Claim before yielding: a second click or Stop cannot answer this request twice.
        self.permissions[sid].pop(rid, None)
        self.broadcast({"t": "permission_done", "session": sid, "id": rid})
        self._status(sid, "stopping" if sid in self.interrupting else "working",
                     "Stopping the current turn" if sid in self.interrupting else "Continuing with your answer")
        await self._write(sid, {"type": "control_response", "response": {
            "subtype": "success", "request_id": rid, "response": response}})

    def _mark(self, sid, on):
        s = self.sessions.all.get(sid)
        if s:
            s.driving = on
            s.managed = sid in self.running
            if not on:
                s.open = False
            self.broadcast({"t": "session", "session": s.meta()})
        elif sid in self.sessions.pending:
            self.sessions.pending[sid]["driving"] = self.sessions.pending[sid]["working"] = on
            self.sessions.pending[sid]["managed"] = sid in self.running
            self.broadcast({"t": "session", "session": self.sessions.pending[sid]})

    async def _result(self, sid, e):
        if sid not in self.busy:
            return
        stopped = sid in self.interrupting
        self.interrupting.discard(sid)
        self.busy.discard(sid)
        self._clear_permissions(sid)
        u = e.get("usage") or {}
        previous = self.usage.get(sid, {})
        self.usage[sid] = {"input": u.get("input_tokens", 0), "output": u.get("output_tokens", 0),
            "cached": u.get("cache_read_input_tokens", 0), "cacheCreated": u.get("cache_creation_input_tokens", 0),
            "cost": e.get("total_cost_usd", previous.get("cost")), "at": time.time()}
        self.broadcast({"t": "usage", "session": sid, "usage": self.usage[sid], "windows": self.usage_windows})
        error = "" if stopped else str(e.get("result") or "; ".join(e.get("errors") or []) or "The turn failed.") if e.get("is_error") else ""
        self._mark(sid, False)
        self._status(sid, "error" if error else "idle", error or ("Stopped" if stopped else "Ready for your next message"))
        self.broadcast({"t": "turn_end", "session": sid, "error": error, "stopped": stopped})
        self._continue(sid)

    def _continue(self, sid):
        pending = self.followups.pop(sid, [])
        if pending and not self.closing:
            self._task(self._resume_correction(sid, "\n\n".join(pending)))

    async def _resume_correction(self, sid, text):
        try:
            await self.send(sid, text)
        except (RuntimeError, OSError) as ex:
            self._status(sid, "error", "Correction was not sent: " + str(ex))
            self.broadcast({"t": "turn_end", "session": sid, "error": "Correction was not sent. Your text: " + text + "\n" + str(ex)})

    def _clear_permissions(self, sid):
        for rid in self.permissions.pop(sid, {}):
            self.broadcast({"t": "permission_done", "session": sid, "id": rid})

    async def _event(self, sid, e):
        typ = e.get("type")
        if typ == "control_response":
            response = e.get("response") or {}
            pending = self.controls.get(response.get("request_id"))
            if pending and not pending.done():
                if response.get("subtype") == "error":
                    pending.set_exception(RuntimeError(str(response.get("error"))))
                else:
                    pending.set_result(response.get("response"))
        elif typ == "stream_event":
            d = (e.get("event") or {}).get("delta") or {}
            if d.get("type") == "text_delta" and d.get("text"):
                self.broadcast({"t": "delta", "session": sid, "text": d["text"]})
        elif typ == "assistant":
            for b in (e.get("message") or {}).get("content") or []:
                if b.get("type") == "tool_use":
                    names = {"Read": "Reading project files", "Edit": "Updating project files", "Write": "Writing project files",
                             "Bash": "Running a command", "Grep": "Searching project files", "Glob": "Finding project files",
                             "AskUserQuestion": "Waiting for your answer"}
                    self._status(sid, "working", names.get(b.get("name"), "Working with a tool"))
        elif typ == "control_request":
            req, rid = e.get("request") or {}, e.get("request_id")
            if req.get("subtype") == "can_use_tool" and rid:
                p = {"id": rid, "session": sid, "tool": req.get("tool_name", "Tool"),
                     "description": req.get("description") or "Permission needed to continue", "input": req.get("input") or {}}
                self.permissions.setdefault(sid, {})[rid] = p
                self.broadcast({"t": "permission", **p})
                self._status(sid, "asking", "Waiting for your answer")
            elif rid:
                await self._write(sid, {"type": "control_response", "response": {
                    "subtype": "error", "request_id": rid, "error": "Unsupported control request"}})
        elif typ == "control_cancel_request":
            rid = e.get("request_id")
            self.permissions.get(sid, {}).pop(rid, None)
            self.broadcast({"t": "permission_done", "session": sid, "id": rid})
        elif typ == "rate_limit_event":
            info = e.get("rate_limit_info") or {}
            self.usage_windows.update(info.get("unifiedWindows") or {})
            if info.get("rateLimitType"):
                key = info["rateLimitType"]
                self.usage_windows[key] = {**self.usage_windows.get(key, {}), **info}
            self.broadcast({"t": "usage", "session": sid, "usage": self.usage.get(sid, {}), "windows": self.usage_windows})
        elif typ == "result":
            await self._result(sid, e)

    async def _pump(self, sid, proc):
        err = bytearray()
        async def read_err():
            async for chunk in proc.stderr:
                err.extend(chunk)
                del err[:-4000]
        stderr = asyncio.create_task(read_err())
        try:
            async for raw in proc.stdout:
                try:
                    e = json.loads(raw)
                except ValueError:
                    continue
                await self._event(sid, e)
            await proc.wait()
        except Exception as ex:
            err.extend(str(ex).encode())
            await self._terminate(proc)
        finally:
            try:
                await asyncio.wait_for(stderr, 2)
            except (TimeoutError, asyncio.CancelledError):
                stderr.cancel()
            if self.running.get(sid) is proc:
                self.running.pop(sid, None)
            ready = self.initializing.get(sid)
            if ready and not ready.done():
                ready.set_exception(RuntimeError(err.decode(errors="replace").strip()[-400:] or "Claude exited during initialization"))
            stopped = sid in self.interrupting
            self.interrupting.discard(sid)
            was_busy = sid in self.busy
            self.busy.discard(sid)
            self._clear_permissions(sid)
            self._mark(sid, False)
            if was_busy and not self.closing:
                error = "" if stopped else err.decode(errors="replace").strip()[-400:] or "Claude disconnected before completing the turn. Send a message to resume."
                self._status(sid, "idle" if stopped else "error", error or "Stopped")
                self.broadcast({"t": "turn_end", "session": sid, "error": error, "stopped": stopped})
            if stopped:
                self.resume_after_stop.add(sid)
            self._continue(sid)

    async def close(self):
        self.closing = True
        self.followups.clear()
        await asyncio.gather(*(self._terminate(p) for p in list(self.running.values())))
        for task in list(self.tasks):
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

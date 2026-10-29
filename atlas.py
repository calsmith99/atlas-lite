#!/usr/bin/env python3
"""Atlas Lite: a small dashboard that wraps your own Claude Code or Codex.

No dependencies beyond Python 3.9+. It never edits ~/.claude or ~/.codex: each turn runs the CLI you chose, with its
working folder set to your vault. Config and conversation live in ~/.atlas-lite (override with ATLAS_HOME).

Environment (all optional): ATLAS_HOME, ATLAS_PORT, ATLAS_VAULT, ATLAS_PROVIDER (claude|codex).
"""
from __future__ import annotations

import json
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from keeper import Keeper, validate, NOTE_FOLDERS, TYPES

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
WEB = ROOT / "web"
HOME = Path(os.environ.get("ATLAS_HOME", "~/.atlas-lite")).expanduser()
CONFIG = HOME / "config.json"
STATE = HOME / "conversation.json"
CHANGED = HOME / "changed.jsonl"    # every note the keeper writes, one JSON line each
THEME_DIR = HOME / "theme"          # a user's own theme: theme.css plus any images it uses

DEFAULTS = {"name": "Atlas", "provider": "", "vault": "~/Atlas Vault", "port": 11800,
            "permission_mode": "acceptEdits", "model": "", "voice": False, "setup_done": False, "effort": "", "scribe": True, "scribe_model": "", "project_dirs": []}
SKIP_DIRS = {".git", ".obsidian", ".trash", ".claude"}
LINK_RE = re.compile(r"\[\[([^\]|#^]+)(?:[#^][^\]|]*)?(?:\|[^\]]*)?\]\]")
MAX_HISTORY = 200


# ---------------------------------------------------------------- config

def load_config() -> dict:
    HOME.mkdir(parents=True, exist_ok=True)
    cfg = dict(DEFAULTS)
    if CONFIG.exists():
        cfg.update(json.loads(CONFIG.read_text()))
    for key, env in (("vault", "ATLAS_VAULT"), ("provider", "ATLAS_PROVIDER"), ("port", "ATLAS_PORT")):
        if os.environ.get(env):
            cfg[key] = os.environ[env]
    cfg["port"] = int(cfg["port"])
    if not cfg["provider"]:
        cfg["provider"] = next((p for p in ("claude", "codex") if shutil.which(p)), "claude")
    if not CONFIG.exists():
        save_config(cfg)
    return cfg


EFFORTS = ["low", "medium", "high", "xhigh", "max"]


def model_choices(provider: str) -> dict:
    """What the model and effort pickers offer. Claude: its aliases. Codex: the models its own cache lists as visible."""
    if provider == "claude":
        return {"models": [{"id": "", "label": "Default", "efforts": EFFORTS}] +
                          [{"id": m, "label": m.capitalize(), "efforts": EFFORTS} for m in ("opus", "sonnet", "haiku")]}
    try:
        cache = json.loads(Path("~/.codex/models_cache.json").expanduser().read_text())
        models = [{"id": m["slug"], "label": m.get("display_name") or m["slug"],
                   "efforts": [l["effort"] for l in m.get("supported_reasoning_levels", []) if isinstance(l, dict)] or EFFORTS[:4]}
                  for m in cache.get("models", []) if m.get("visibility") == "list"]
    except (OSError, ValueError, TypeError):
        models = []
    return {"models": [{"id": "", "label": "Default", "efforts": EFFORTS[:4]}] + models}


def mode_choices(provider: str) -> list:
    """What the permission picker offers. Codex only has a read-only or workspace-write sandbox."""
    if provider == "claude":
        return [{"id": "manual", "label": "Ask each time"}, {"id": "acceptEdits", "label": "Accept edits"},
                {"id": "auto", "label": "Auto"}, {"id": "plan", "label": "Plan (read-only)"},
                {"id": "bypassPermissions", "label": "Bypass permissions"}]
    return [{"id": "acceptEdits", "label": "Edit files"}, {"id": "plan", "label": "Read-only"}]


def save_config(cfg: dict):
    CONFIG.write_text(json.dumps({k: cfg[k] for k in DEFAULTS}, indent=2) + "\n")


def ensure_vault(vault: Path):
    """Create the vault from vault-template/ if it is missing. Never overwrites, never runs git."""
    if vault.exists():
        return False
    shutil.copytree(ROOT / "vault-template", vault)
    for folder in ("Reference", "Research", "Projects", "Logs", "Extras"):
        (vault / folder).mkdir(exist_ok=True)
    return True


RULES_BEGIN, RULES_END = "<!-- atlas-lite:begin -->", "<!-- atlas-lite:end -->"
RULES_BLOCK = f"""{RULES_BEGIN}
## Notes (managed by Atlas Lite; edit outside this block)

- Start at `Index.md`. Before answering anything about the user's own life, projects or setup, search the vault; state nothing as fact you have not looked up. Read `.claude/skills/vault-reading/SKILL.md` first.
- Keep it live: when something changes or is learned, update the right note in the same turn. Read `.claude/skills/vault-writing/SKILL.md` before writing any note (Codex: the same file).
- Write notes only with the vault tools, which check the rules and say what to fix: `new_note` (template), `write_note`, `edit_note`, `append_log` (the day's diary line). Never create or edit notes with a shell or file editor.
- Every note is linked from `Index.md` or a hub note. If `write_note` says a note is unlinked, add the link with `edit_note` before you finish.
- Never write passwords, keys or tokens into a note; say where they live.
{RULES_END}
"""


def sync_rules(vault: Path):
    """Keep the notes rules in the vault's CLAUDE.md and AGENTS.md current: one marked block, everything else left alone."""
    for name in ("CLAUDE.md", "AGENTS.md"):
        f = vault / name
        text = f.read_text() if f.exists() else ""
        if RULES_BEGIN in text and RULES_END in text:
            a, b = text.index(RULES_BEGIN), text.index(RULES_END) + len(RULES_END)
            new = text[:a] + RULES_BLOCK.strip() + text[b:]
        else:
            new = text.rstrip() + ("\n\n" if text.strip() else "") + RULES_BLOCK
        if new != text:
            f.write_text(new)


def sync_skills(vault: Path):
    """Copy the shipped skills into <vault>/.claude/skills so a session started in the vault finds them by name.
    Only touches the folders it ships (skills/<name>); anything else in .claude is left alone."""
    src = ROOT / "skills"
    if not src.is_dir():
        return
    for skill in src.iterdir():
        if skill.is_dir():
            dest = vault / ".claude" / "skills" / skill.name
            shutil.copytree(skill, dest, dirs_exist_ok=True)


# ---------------------------------------------------------------- notes graph

class Notes:
    def __init__(self, vault: Path):
        self.vault, self.stamp = vault, None
        self.graph = {"nodes": [], "links": []}
        self.by_name: dict[str, str] = {}

    def files(self):
        for root, dirs, files in os.walk(self.vault):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            for f in files:
                if f.endswith(".md") and f not in ("CLAUDE.md", "AGENTS.md"):
                    yield Path(root) / f

    def load(self) -> dict:
        files = sorted(self.files())
        stamp = tuple((str(p), p.stat().st_mtime) for p in files)
        if stamp == self.stamp:
            return self.graph
        nodes, texts, by_name = [], {}, {}
        for p in files:
            rel = p.relative_to(self.vault)
            nid = str(rel.with_suffix(""))
            text = p.read_text(errors="replace")
            texts[nid] = text
            opener = re.search(r"^_(.+?)_\s*$", text, re.M)
            nodes.append({"id": nid, "name": p.stem, "folder": rel.parts[0] if len(rel.parts) > 1 else "",
                          "blurb": opener.group(1)[:200] if opener else ""})
            by_name[p.stem.lower()] = nid
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

    def touched(self, text: str) -> list[str]:
        """Notes a tool call mentions, by `Name.md` anywhere in its input."""
        found = []
        for m in re.finditer(r"([^/\\\"'`]+?)\.md\b", text):
            nid = self.by_name.get(m.group(1).strip().lower())
            if nid and nid not in found:
                found.append(nid)
        return found


# ---------------------------------------------------------------- one conversation

class Hub:
    """Fan-out of events to every open dashboard page (server-sent events)."""

    def __init__(self):
        self.clients: set[queue.Queue] = set()
        self.lock = threading.Lock()

    def add(self):
        q = queue.Queue(maxsize=500)
        with self.lock:
            self.clients.add(q)
        return q

    def remove(self, q):
        with self.lock:
            self.clients.discard(q)

    def send(self, event: dict):
        data = json.dumps(event)
        with self.lock:
            for q in list(self.clients):
                try:
                    q.put_nowait(data)
                except queue.Full:
                    self.clients.discard(q)


READ_ONLY_TOOLS = ["Read", "Grep", "Glob"] + [f"Bash({c}:*)" for c in ("ls", "grep", "cat", "find", "head", "tail", "wc", "rg", "pwd")]

NOTES_POLICY = ("This folder is a notes vault. Before writing or editing a note, read .claude/skills/vault-writing/SKILL.md; before "
                "answering anything about the user's own life, projects or setup, search the vault first. Write notes only with the "
                "vault tools (new_note, write_note, edit_note, append_log), never with a shell or file editor, and link every new "
                "note from Index.md or a hub note.")

SCRIBE_SYSTEM = """You are the vault scribe. A turn of work just finished in the user's notes vault. Decide whether it left anything durable that is not in the vault yet, and if so file it yourself with the vault tools; nobody reviews this and nobody is waiting for a reply.

Durable means: a fact about the user's life, work or setup, a decision and its reason, a change that was made, a plan, a conclusion. Not durable: chatter, one-off lookups, prices, links, a narrative of the session. First look: read .claude/skills/vault-writing/SKILL.md, then search the vault for the owning note. Prefer edit_note on that note; use new_note then write_note only for a genuinely new topic. Anything already filed (see the list of notes changed recently, and check by searching) is not filed again. Every new note is linked from Index.md or a hub note. Write in the user's voice, small notes, never credentials. If a tool rejects a write, fix it and retry once. If nothing qualifies, make no tool calls and reply only NONE; otherwise reply with one line per note written."""

TOOL_LABELS = {"Read": "Reading", "Edit": "Editing", "Write": "Writing", "Bash": "Running a command",
               "Grep": "Searching", "Glob": "Looking for files", "WebSearch": "Searching the web",
               "WebFetch": "Reading a web page"}


class Conversation:
    def __init__(self, cfg: dict, notes: Notes, hub: Hub):
        self.cfg, self.notes, self.hub = cfg, notes, hub
        self.lock = threading.Lock()
        self.proc: subprocess.Popen | None = None
        self.stopped = False
        self.status = {"stage": "idle", "text": "Ready"}
        self.usage: dict = {"provider": cfg["provider"], "windows": [], "tokens": None}
        saved = json.loads(STATE.read_text()) if STATE.exists() else {}
        if "sessions" not in saved:      # older single-conversation file
            saved = {"sessions": {"s1": {"title": "", "session": saved.get("session"), "messages": saved.get("messages", []),
                                         "updated": time.time()}} if saved.get("messages") else {},
                     "current": "s1", "provider": saved.get("provider"), "usage": saved.get("usage")}
        if saved.get("provider") != cfg["provider"]:
            saved = {"sessions": {}, "current": None}
        self.sessions: dict[str, dict] = saved["sessions"]
        self.reply = ""
        self.permissions: dict[str, dict] = {}     # request id -> what Claude wants to do, waiting for Allow or Deny
        self.always: set[str] = set()              # tool names the user allowed for the rest of this run
        self.pending_text = ""
        self.init_id = ""
        self.fresh = True              # no turn since the server started: the orb says Awake, not Ready
        self.turn_start = 0.0
        self.turn_text = ""
        self.turn_acted = False        # did this turn do real work (not only reading)?
        self.repairs = 0
        self.scribe_lock = threading.Lock()
        self.keeper = Keeper(self.notes.vault, CHANGED)
        self.pump_thread: threading.Thread | None = None
        if saved.get("usage", {}).get("provider") == cfg["provider"]:
            self.usage = saved["usage"]
        self.open(saved.get("current") if saved.get("current") in self.sessions else None)

    # -- sessions: self.current is the open one; self.session is its CLI session id, self.messages its transcript
    def open(self, sid: str | None):
        if sid is None:
            sid = "s" + uuid.uuid4().hex[:8]
            self.sessions[sid] = {"title": "", "session": None, "messages": [], "updated": time.time()}
        self.current = sid
        self.entry = self.sessions[sid]
        self.session, self.messages = self.entry["session"], self.entry["messages"]

    def session_list(self) -> list[dict]:
        out = sorted(self.sessions.items(), key=lambda kv: kv[1]["updated"], reverse=True)
        return [{"id": k, "title": v["title"] or "New session", "updated": v["updated"], "n": len(v["messages"])} for k, v in out]

    def switch(self, sid: str | None):
        """Open another session, or a fresh one when sid is None. Waits for a running turn to stop first."""
        if sid is not None and sid not in self.sessions:
            raise RuntimeError("Unknown session.")
        self.stop()
        if self.pump_thread:
            self.pump_thread.join(6)
        with self.lock:
            if sid is None and not self.messages:      # already on an empty one: reuse it
                sid = self.current
            self.entry["session"] = self.session
            self.open(sid)
            # drop empty sessions you have left behind
            for k in [k for k, v in self.sessions.items() if not v["messages"] and k != self.current]:
                del self.sessions[k]
            self.reply = ""
            self.save()
        self.hub.send({"t": "session", "current": self.current, "sessions": self.session_list(),
                       "messages": self.messages})
        self.set_status("idle", "Ready")

    # -- state
    def save(self):
        self.entry["session"] = self.session
        STATE.write_text(json.dumps({"provider": self.cfg["provider"], "current": self.current, "sessions": {
            k: {**v, "messages": v["messages"][-MAX_HISTORY:]} for k, v in self.sessions.items()}, "usage": self.usage}))

    def set_status(self, stage, text):
        if self.status == {"stage": stage, "text": text}:
            return
        self.status = {"stage": stage, "text": text}
        self.hub.send({"t": "status", **self.status})

    def snapshot(self) -> dict:
        return {"name": self.cfg["name"], "provider": self.cfg["provider"], "voice": self.cfg["voice"],
                "model": self.cfg["model"], "effort": self.cfg["effort"], "choices": model_choices(self.cfg["provider"]),
                "mode": self.cfg["permission_mode"], "modes": mode_choices(self.cfg["provider"]),
                "vault": str(self.notes.vault), "status": self.status, "usage": self.usage,
                "messages": self.messages, "reply": self.reply, "current": self.current,
                "fresh": self.fresh, "custom": custom_stamp(), "setup_done": self.cfg["setup_done"], "permissions": [{k: v for k, v in p.items() if k not in ("input", "proc", "_proc")} for p in self.permissions.values()],
                "sessions": self.session_list()}

    # -- commands
    def command(self) -> list[str]:
        c = self.cfg
        if c["provider"] == "claude":
            cmd = [shutil.which("claude") or "claude", "-p", "--output-format", "stream-json", "--verbose",
                   "--include-partial-messages", "--input-format", "stream-json",
                   "--permission-prompt-tool", "stdio", "--permission-mode", c["permission_mode"],
                   "--add-dir", str(self.notes.vault), "--add-dir", str(HOME),
                   *[a for d in self.project_dirs() for a in ("--add-dir", d)],
                   "--mcp-config", json.dumps(self.mcp_config()),
                   "--allowedTools", *["mcp__vault__" + t for t in ("new_note", "write_note", "edit_note", "append_log")],
                   *READ_ONLY_TOOLS,
                   "--settings", json.dumps(self.guard_settings()),
                   "--append-system-prompt", NOTES_POLICY]
            if c["model"]:
                cmd += ["--model", c["model"]]
            if c["effort"]:
                cmd += ["--effort", c["effort"]]
            return cmd + (["--resume", self.session] if self.session else [])
        cmd = [shutil.which("codex") or "codex", "exec"]
        if self.session:
            cmd += ["resume", self.session]
        cmd += ["--json", "--skip-git-repo-check", "-c",
                'sandbox_mode="%s"' % ("read-only" if c["permission_mode"] == "plan" else "workspace-write"),
                "-c", "sandbox_workspace_write.writable_roots=%s" % json.dumps([str(HOME), str(ROOT), *self.project_dirs()]),
                "-c", "sandbox_workspace_write.network_access=true",
                "-c", "mcp_servers.vault.command=%s" % json.dumps(sys.executable),
                "-c", "mcp_servers.vault.args=%s" % json.dumps(self.keeper_args())]
        if c["model"]:
            cmd += ["-c", 'model="%s"' % c["model"]]
        if c["effort"]:
            cmd += ["-c", 'model_reasoning_effort="%s"' % c["effort"]]
        return cmd + ["-"]

    def project_dirs(self) -> list[str]:
        """Folders of the user's own projects that the assistant may read and edit besides the vault."""
        return [d for d in self.cfg.get("project_dirs", []) if Path(d).is_dir()]

    def keeper_args(self) -> list[str]:
        return [str(ROOT / "keeper_mcp.py"), str(self.notes.vault), str(CHANGED)]

    def mcp_config(self) -> dict:
        return {"mcpServers": {"vault": {"command": sys.executable, "args": self.keeper_args()}}}

    def guard_settings(self) -> dict:
        """A PreToolUse hook for this turn only (command-line settings, nothing installed): notes go through the vault tools."""
        cmd = f"{json.dumps(sys.executable)} {json.dumps(str(ROOT / 'guard.py'))} {json.dumps(str(self.notes.vault))}"
        return {"hooks": {"PreToolUse": [{"matcher": "Write|Edit|MultiEdit|NotebookEdit",
                                          "hooks": [{"type": "command", "command": cmd}]}]}}

    def send(self, text: str, visible: bool = True):
        with self.lock:
            if self.proc and self.proc.poll() is None:
                raise RuntimeError("Still working on the last message.")
            if not shutil.which(self.cfg["provider"]):
                raise RuntimeError(f"'{self.cfg['provider']}' is not installed or not on your PATH.")
            self.stopped = False
            self.fresh = False
            self.reply = ""
            self.turn_start, self.turn_acted, self.turn_text = time.time(), False, text
            if visible:
                self.repairs = 0
                self.messages.append({"role": "user", "text": text})
                self.entry["updated"] = time.time()
                if not self.entry["title"]:
                    self.entry["title"] = (text[:40] + "…") if len(text) > 40 else text
                self.save()
                self.hub.send({"t": "user", "text": text})
            self.set_status("working", "Thinking")
            try:
                self.proc = subprocess.Popen(self.command(), cwd=str(self.notes.vault), stdin=subprocess.PIPE,
                                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
                                             env={**os.environ, "ATLAS_HOME": str(HOME), "ATLAS_THEME_DIR": str(THEME_DIR)})
            except OSError as ex:
                if visible:
                    self.messages.pop()
                self.set_status("error", str(ex))
                raise RuntimeError(str(ex))
            proc = self.proc
        if self.cfg["provider"] == "claude":
            # stream-json input: say hello first, send the message when Claude answers (see claude_event)
            self.pending_text = text
            self.init_id = "init-" + uuid.uuid4().hex
            self.write(proc, {"type": "control_request", "request_id": self.init_id,
                              "request": {"subtype": "initialize", "hooks": None}})
        else:
            proc.stdin.write(text.encode())
            proc.stdin.close()
        self.pump_thread = threading.Thread(target=self.pump, args=(proc,), daemon=True)
        self.pump_thread.start()
        self.hub.send({"t": "sessions", "sessions": self.session_list()})

    def write(self, proc, obj):
        try:
            proc.stdin.write((json.dumps(obj) + "\n").encode())
            proc.stdin.flush()
        except (OSError, ValueError):
            pass

    def stop(self):
        proc = self.proc
        if proc and proc.poll() is None:
            self.stopped = True
            for rid in list(self.permissions):
                self.answer(rid, False, message="The user stopped this turn.")
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    # -- reading the CLI's output
    def pump(self, proc: subprocess.Popen):
        err = bytearray()
        def read_err():
            for chunk in iter(lambda: proc.stderr.read1(4096), b""):
                err.extend(chunk)
                del err[:-4000]
        threading.Thread(target=read_err, daemon=True).start()
        error = ""
        for raw in proc.stdout:
            try:
                e = json.loads(raw)
            except ValueError:
                continue
            try:
                error = (self.claude_event if self.cfg["provider"] == "claude" else self.codex_event)(e) or error
            except Exception as ex:  # a malformed event must not end the turn
                print("event error:", ex, file=sys.stderr)
        proc.wait()
        time.sleep(0.1)
        if self.stopped:
            error = ""
        elif not error and proc.returncode:
            error = bytes(err).decode(errors="replace").strip()[-400:] or f"The CLI exited with code {proc.returncode}."
        for rid in list(self.permissions):
            self.permissions.pop(rid, None)
            self.hub.send({"t": "permission_done", "id": rid})
        if self.reply.strip():
            self.messages.append({"role": "assistant", "text": self.reply.strip()})
        self.reply = ""
        self.save()
        self.hub.send({"t": "turn_end", "error": error, "stopped": self.stopped})
        self.set_status("error" if error else "idle", error or ("Stopped" if self.stopped else "Ready"))
        if not error and not self.stopped:
            self.after_turn()

    # -- the vault check after each turn: rules on whatever changed, links on whatever is new, then the scribe
    def audit(self) -> list[str]:
        """Problems with notes written or changed during the turn, by any route (the tools already check their own writes)."""
        problems = []
        v = self.notes.vault
        files = [v / "Index.md"] + [p for f in NOTE_FOLDERS if (v / f).is_dir() for p in (v / f).glob("*.md")]
        orphans = set(self.keeper.orphans())
        for p in files:
            try:
                if p.stat().st_mtime < self.turn_start - 1:
                    continue
                rel = str(p.relative_to(v))
                for why in validate(rel, p.read_text(errors="replace")):
                    problems.append(f"{rel}: {why}")
                if rel in orphans:
                    problems.append(f"{rel}: nothing links to it; link it from Index.md or the hub note it belongs under")
            except OSError:
                continue
        return problems

    def after_turn(self):
        try:
            problems = self.audit()
        except Exception as ex:
            print("audit error:", ex, file=sys.stderr)
            problems = []
        if problems and self.repairs < 1:
            self.repairs += 1
            self.hub.send({"t": "notice", "text": f"Checking the notes: {len(problems)} thing{'s' if len(problems) != 1 else ''} to fix"})
            threading.Thread(target=self.send, args=("The vault check found problems in the notes you just wrote. Fix each with the "
                                                     "vault tools (edit_note, or write_note for a replacement), then reply with one short line:\n- "
                                                     + "\n- ".join(problems[:12]), False), daemon=True).start()
            return
        if self.cfg.get("scribe", True) and self.scribe_worthwhile():
            threading.Thread(target=self.scribe, daemon=True).start()

    def keeper_wrote_note(self) -> bool:
        """Did the assistant itself file a note (not just the diary line) during this turn?"""
        try:
            rows = [json.loads(l) for l in CHANGED.read_text().splitlines()[-40:]]
        except (OSError, ValueError):
            return False
        return any(r.get("ts", 0) >= self.turn_start and r.get("type") != "log" for r in rows)

    def scribe_worthwhile(self) -> bool:
        """The cheap gate before a model call: a real exchange the assistant did not already file."""
        if self.keeper_wrote_note():
            return False
        return self.turn_acted or len(self.turn_text) >= 40

    def scribe(self):
        """Background filing: a second, small run with the vault tools that saves anything durable from the last turn."""
        if not self.scribe_lock.acquire(blocking=False):
            return
        try:
            self.hub.send({"t": "scribe", "text": "Filing notes"})
            user = self.turn_text[:1500]
            said = (self.messages[-1]["text"] if self.messages and self.messages[-1]["role"] == "assistant" else "")[:2500]
            changed = sorted({r["path"] for r in (json.loads(l) for l in CHANGED.read_text().splitlines()[-60:])
                              if r.get("type") != "log"}) if CHANGED.exists() else []
            prompt = (f"Notes changed recently:\n{chr(10).join('- ' + c for c in changed) or 'none'}\n\n"
                      f"The turn that just finished.\nThe user said:\n{user}\n\nThe assistant replied:\n{said}")
            c = self.cfg
            if c["provider"] == "claude":
                cmd = [shutil.which("claude") or "claude", "-p", "--model", c.get("scribe_model") or "haiku", "--permission-mode", "default",
                       "--mcp-config", json.dumps(self.mcp_config()), "--add-dir", str(self.notes.vault),
                       "--allowedTools", *["mcp__vault__" + t for t in ("new_note", "write_note", "edit_note")], *READ_ONLY_TOOLS,
                       "--settings", json.dumps(self.guard_settings()), "--append-system-prompt", SCRIBE_SYSTEM]
            else:
                cmd = [shutil.which("codex") or "codex", "exec", "--ephemeral", "--skip-git-repo-check", "-c", 'sandbox_mode="read-only"',
                       "-c", "mcp_servers.vault.command=%s" % json.dumps(sys.executable),
                       "-c", "mcp_servers.vault.args=%s" % json.dumps(self.keeper_args())]
                if c.get("scribe_model"):
                    cmd += ["-c", 'model="%s"' % c["scribe_model"]]
                cmd += ["-"]
                prompt = SCRIBE_SYSTEM + "\n\n" + prompt
            try:
                out = subprocess.run(cmd, input=prompt.encode(), cwd=str(self.notes.vault), capture_output=True, timeout=240)
                print("scribe:", out.stdout.decode(errors="replace").strip()[-200:], file=sys.stderr)
            except (OSError, subprocess.TimeoutExpired) as ex:
                print("scribe failed:", ex, file=sys.stderr)
        finally:
            self.scribe_lock.release()
            self.hub.send({"t": "scribe", "text": ""})

    def delta(self, text):
        self.reply += text
        self.hub.send({"t": "delta", "text": text})

    def touch(self, e):
        """A note is touched when the assistant reads or writes it: a tool call that names it, in a path, a command or a
        vault tool's `name` or `path`. A note being created is not in the graph yet, so the page holds the touch until it is."""
        found = list(self.notes.touched(json.dumps(e)))

        v = self.notes.vault

        def walk(x):
            if isinstance(x, dict):
                if isinstance(x.get("type"), str) and isinstance(x.get("name"), str) and x["type"] in TYPES:   # write_note
                    found.append(f"{TYPES[x['type']][0]}/{Path(x['name']).stem if x['name'].endswith('.md') else x['name']}")
                for k, val in x.items():
                    if k in ("path", "file_path") and isinstance(val, str) and val.endswith(".md"):
                        try:
                            rel = Path(val).expanduser().resolve().relative_to(v.resolve()) if val.startswith(("/", "~")) else Path(val)
                        except ValueError:
                            continue
                        if rel.parts and not rel.parts[0].startswith("."):
                            found.append(str(rel.with_suffix("")))
                    else:
                        walk(val)
            elif isinstance(x, list):
                for val in x:
                    walk(val)
        walk(e)
        for nid in dict.fromkeys(n for n in found if n):
            self.hub.send({"t": "touch", "note": nid})

    def ask(self, proc, e):
        req, rid = e.get("request") or {}, e.get("request_id")
        if req.get("subtype") != "can_use_tool" or not rid:
            if rid:
                self.write(proc, {"type": "control_response", "response": {"subtype": "error", "request_id": rid,
                                                                           "error": "Unsupported control request"}})
            return
        tool, inp = req.get("tool_name", "Tool"), req.get("input") or {}
        if tool == "AskUserQuestion":
            self.write(proc, {"type": "control_response", "response": {"subtype": "success", "request_id": rid, "response": {
                "behavior": "deny", "message": "Ask the user in your reply text instead; no question screen is available."}}})
            return
        if tool in self.always:
            self.write(proc, {"type": "control_response", "response": {"subtype": "success", "request_id": rid,
                                                                       "response": {"behavior": "allow", "updatedInput": inp}}})
            return
        detail = inp.get("command") or inp.get("file_path") or inp.get("url") or inp.get("pattern") or inp.get("path") or ""
        p = {"id": rid, "tool": tool, "detail": str(detail)[:2000], "description": req.get("description") or "",
             "input": inp, "proc": None}
        self.permissions[rid] = {**p, "_proc": proc}
        self.hub.send({"t": "permission", **{k: v for k, v in p.items() if k not in ("input", "proc")}})
        self.set_status("asking", "Waiting for your answer")

    def answer(self, rid: str, allow: bool, always: bool = False, message: str = ""):
        p = self.permissions.pop(rid, None)
        if not p:
            raise RuntimeError("That question is no longer waiting for an answer.")
        if allow and always:
            self.always.add(p["tool"])
        resp = {"behavior": "allow", "updatedInput": p["input"]} if allow else {
            "behavior": "deny", "message": message or "The user declined. Do not retry this without new instructions."}
        self.write(p["_proc"], {"type": "control_response", "response": {"subtype": "success", "request_id": rid, "response": resp}})
        self.hub.send({"t": "permission_done", "id": rid})
        if not self.permissions:
            self.set_status("working", "Continuing")

    def claude_event(self, e):
        typ = e.get("type")
        if typ == "control_response":
            r = e.get("response") or {}
            if r.get("request_id") == self.init_id and self.pending_text:
                text, self.pending_text = self.pending_text, ""
                self.write(self.proc, {"type": "user", "message": {"role": "user", "content": text}})
        elif typ == "control_request":
            self.ask(self.proc, e)
        elif typ == "control_cancel_request":
            if self.permissions.pop(e.get("request_id"), None):
                self.hub.send({"t": "permission_done", "id": e.get("request_id")})
        if e.get("session_id") and typ == "system":
            self.session = e["session_id"]
        elif typ == "stream_event":
            d = (e.get("event") or {}).get("delta") or {}
            if d.get("type") == "text_delta" and d.get("text"):
                self.set_status("working", "Writing a reply")
                self.delta(d["text"])
        elif typ == "assistant":
            for b in (e.get("message") or {}).get("content") or []:
                if b.get("type") == "tool_use":
                    if b.get("name") not in ("Read", "Grep", "Glob", "WebSearch", "WebFetch", "TodoWrite") and not str(b.get("name")).startswith("mcp__vault__"):
                        self.turn_acted = True
                    self.set_status("working", TOOL_LABELS.get(b.get("name"), "Using a tool"))
                    self.touch(b.get("input") or {})
        elif typ == "rate_limit_event":
            w = (e.get("rate_limit_info") or {}).get("unifiedWindows") or {}
            names = {"five_hour": "5 hours", "seven_day": "7 days"}
            self.usage["windows"] = [{"label": names.get(k, k), "used": round(v.get("utilization", 0) * 100),
                                      "resets": v.get("resetsAt")} for k, v in w.items()]
            self.hub.send({"t": "usage", "usage": self.usage})
        elif typ == "result":
            try:
                self.proc.stdin.close()
            except (OSError, ValueError, AttributeError):
                pass
            u = e.get("usage") or {}
            self.usage["tokens"] = {"input": u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0)
                                    + u.get("cache_creation_input_tokens", 0), "output": u.get("output_tokens", 0)}
            self.hub.send({"t": "usage", "usage": self.usage})
            if e.get("is_error"):
                return str(e.get("result") or "; ".join(e.get("errors") or []) or "The turn failed.")

    def codex_event(self, e):
        typ = e.get("type")
        if typ == "thread.started":
            self.session = e.get("thread_id")
        elif typ in ("item.started", "item.completed"):
            item = e.get("item") or {}
            kind = item.get("type")
            if kind == "agent_message" and typ == "item.completed":
                self.delta(("\n\n" if self.reply else "") + (item.get("text") or ""))
            elif kind == "command_execution":
                self.turn_acted = True
                self.set_status("working", "Running a command")
                self.touch(item)
            elif kind == "file_change":
                self.set_status("working", "Editing files")
                self.touch(item)
            elif kind == "reasoning":
                self.set_status("working", "Thinking")
        elif typ == "turn.completed":
            u = e.get("usage") or {}
            self.usage["tokens"] = {"input": u.get("input_tokens", 0), "output": u.get("output_tokens", 0)}
            self.codex_limits()
            self.hub.send({"t": "usage", "usage": self.usage})
        elif typ in ("turn.failed", "error"):
            m = e.get("message") or (e.get("error") or {}).get("message") or "The turn failed."
            return m if isinstance(m, str) else json.dumps(m)

    def codex_limits(self):
        """Codex does not print limits in its JSON stream; its own rollout file for this thread has them."""
        root = Path("~/.codex/sessions").expanduser()
        try:
            path = next(iter(sorted(root.rglob(f"*{self.session}.jsonl"))), None)
            if not path:
                return
            last = None
            for line in path.read_text(errors="replace").splitlines():
                if '"rate_limits"' in line:
                    last = line
            limits = json.loads(last)["payload"]["rate_limits"] if last else None
        except (OSError, ValueError, KeyError):
            return
        out = []
        for key in ("primary", "secondary"):
            w = (limits or {}).get(key)
            if w:
                m = w.get("window_minutes") or 0
                out.append({"label": f"{m // 1440} days" if m >= 1440 else f"{m // 60} hours",
                            "used": round(w.get("used_percent", 0)), "resets": w.get("resets_at")})
        if out:
            self.usage["windows"] = out


# ---------------------------------------------------------------- http

def custom_stamp() -> float:
    """Modified time of the user's custom.js (0 if none): the page reloads when it changes."""
    try:
        return (THEME_DIR / "custom.js").stat().st_mtime
    except OSError:
        return 0


class App:
    def __init__(self):
        self.cfg = load_config()
        self.vault = Path(self.cfg["vault"]).expanduser()
        self.created_vault = ensure_vault(self.vault)
        sync_skills(self.vault)
        sync_rules(self.vault)
        self.notes = Notes(self.vault)
        self.notes.load()
        (HOME / "install-path").write_text(str(ROOT) + "\n")   # so an assistant can find the default theme and docs
        self.hub = Hub()
        self.conv = Conversation(self.cfg, self.notes, self.hub)

    def theme_stamp(self):
        try:
            return tuple(sorted((p.name, p.stat().st_mtime) for p in THEME_DIR.iterdir()))
        except OSError:
            return ()

    def watch(self):
        last = self.notes.stamp
        theme = self.theme_stamp()
        while True:
            time.sleep(2)
            if self.theme_stamp() != theme:
                theme = self.theme_stamp()
                self.hub.send({"t": "theme", "v": int(time.time()), "custom": custom_stamp()})
            try:
                self.notes.load()
            except OSError:
                continue
            if self.notes.stamp != last:
                last = self.notes.stamp
                self.hub.send({"t": "graph", "graph": self.notes.graph})


APP: App


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    types = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml",
             ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}

    def log_message(self, *a):
        pass

    def json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/state":
            return self.json({**APP.conv.snapshot(), "graph": APP.notes.load()})
        if path == "/api/events":
            return self.events()
        if path == "/api/note":
            nid = parse_qs(urlparse(self.path).query).get("id", [""])[0]
            f = (APP.vault / (nid + ".md")).resolve()
            if APP.vault.resolve() not in f.parents or not f.is_file():
                return self.json({"error": "not found"}, 404)
            text = re.sub(r"\A---\n.*?\n---\n", "", f.read_text(errors="replace"), flags=re.S)
            return self.json({"id": nid, "name": f.stem, "path": str(f), "text": text,
                              "links": [APP.notes.by_name.get(m.group(1).strip().split("/")[-1].lower())
                                        for m in LINK_RE.finditer(text)]})
        if path == "/theme.css":
            # the default theme with the user's on top, so a theme that leaves a variable out falls back to the default
            css = (WEB / "theme-default.css").read_text()
            mine = THEME_DIR / "theme.css"
            if mine.is_file():
                css += "\n/* user theme */\n" + mine.read_text(errors="replace")
            body = css.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/css")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            return self.wfile.write(body)
        if path.startswith("/theme/"):
            f = (THEME_DIR / path[len("/theme/"):]).resolve()
            if THEME_DIR.resolve() not in f.parents:
                return self.json({"error": "not found"}, 404)
        else:
            rel = "index.html" if path == "/" else path.lstrip("/")
            f = (WEB / rel).resolve()
            if WEB.resolve() not in f.parents:
                return self.json({"error": "not found"}, 404)
        if not f.is_file():
            return self.json({"error": "not found"}, 404)
        body = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", self.types.get(f.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def events(self):
        q = APP.hub.add()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            while True:
                try:
                    self.wfile.write(f"data: {q.get(timeout=15)}\n\n".encode())
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
        except (OSError, ValueError):
            pass
        finally:
            APP.hub.remove(q)

    def do_POST(self):
        # Refuse requests that another website made through your browser: the Origin must be this server.
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != self.headers.get("Host"):
            return self.json({"error": "forbidden"}, 403)
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self.json({"error": "bad json"}, 400)
        path, conv = urlparse(self.path).path, APP.conv
        try:
            if path == "/api/send":
                text = str(body.get("text", "")).strip()
                if not text:
                    return self.json({"error": "empty message"}, 400)
                conv.send(text)
            elif path == "/api/answer":
                conv.answer(str(body.get("id", "")), bool(body.get("allow")), bool(body.get("always")))
            elif path == "/api/stop":
                conv.stop()
            elif path == "/api/new":
                conv.switch(None)
            elif path == "/api/session":
                conv.switch(str(body.get("id", "")))
            elif path == "/api/name":
                APP.cfg["name"] = (str(body.get("name", "")).strip() or "Atlas")[:40]
                save_config(APP.cfg)
                APP.hub.send({"t": "name", "name": APP.cfg["name"]})
            elif path == "/api/model":
                ids = {m["id"]: m["efforts"] for m in model_choices(APP.cfg["provider"])["models"]}
                model, effort = str(body.get("model", "")), str(body.get("effort", ""))
                if model not in ids or (effort and effort not in ids[model]):
                    return self.json({"error": "That model or effort is not available."}, 400)
                APP.cfg["model"], APP.cfg["effort"] = model, effort
                save_config(APP.cfg)
                APP.hub.send({"t": "model", "model": model, "effort": effort})
            elif path == "/api/mode":
                mode = str(body.get("mode", ""))
                if mode not in {m["id"] for m in mode_choices(APP.cfg["provider"])}:
                    return self.json({"error": "That mode is not available."}, 400)
                APP.cfg["permission_mode"] = mode
                save_config(APP.cfg)
                APP.hub.send({"t": "mode", "mode": mode})
            elif path == "/api/projects":
                dirs = []
                for raw in body.get("dirs", []):
                    d = Path(str(raw)).expanduser().resolve()
                    if not d.is_dir():
                        return self.json({"error": f"{raw} is not a folder."}, 400)
                    if d == Path.home().resolve() or d == Path(d.anchor):
                        return self.json({"error": "Pick a projects folder, not your whole home folder."}, 400)
                    if str(d) not in dirs:
                        dirs.append(str(d))
                APP.cfg["project_dirs"] = dirs
                save_config(APP.cfg)
            elif path == "/api/voice":
                APP.cfg["voice"] = bool(body.get("on"))
                save_config(APP.cfg)
            else:
                return self.json({"error": "not found"}, 404)
        except RuntimeError as ex:
            return self.json({"error": str(ex)}, 409)
        self.json({"ok": True})


def main():
    global APP
    APP = App()
    threading.Thread(target=APP.watch, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", APP.cfg["port"]), Handler)
    server.daemon_threads = True
    url = f"http://localhost:{APP.cfg['port']}"
    print(f"Atlas Lite on {url}  ({APP.cfg['provider']}, vault {APP.vault}{', created just now' if APP.created_vault else ''})")
    if not shutil.which(APP.cfg["provider"]):
        print(f"Warning: '{APP.cfg['provider']}' is not on your PATH; the dashboard will open but cannot reply.")
    if os.environ.get("ATLAS_OPEN") == "1":
        threading.Timer(1, lambda: subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", url],
                                                  stderr=subprocess.DEVNULL)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        APP.conv.stop()


if __name__ == "__main__":
    main()

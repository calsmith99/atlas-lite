"""Atlas baseline: a dashboard for Claude Code sessions and the notes they touch.

Run with ./run.sh (see README.md). Configuration is by environment variable:
  ATLAS_VAULT            notes folder shown on the globe        (default ~/Atlas Vault)
  ATLAS_PORT             port, bound to 127.0.0.1 only           (default 11700)
  ATLAS_RECENT_HOURS     how far back sessions are followed      (default 6)
  ATLAS_PERMISSION_MODE  Claude permission mode for driven turns (default acceptEdits)
  ATLAS_DEFAULT_CWD      default folder for a new session        (default ~)
  ATLAS_CODE_GRAPH       optional graph JSON for the second globe
  ATLAS_VOICE=1          turn on the voice hook point (voice/README.md)
"""
from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from aiohttp import web

from addons import Addons
from messages import message, REQUEST_LIMIT
from driver import Driver
from graphs import JsonFileSource, build_sources
from repos import load_repos
from sessions import Sessions

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "dashboard"
VAULT = Path(os.environ.get("ATLAS_VAULT", "~/Atlas Vault")).expanduser()
PORT = int(os.environ.get("ATLAS_PORT", "11700"))
VOICE = os.environ.get("ATLAS_VOICE", "") not in ("", "0", "false")

clients: set[web.WebSocketResponse] = set()
sources = build_sources(VAULT)
addons = Addons(ROOT)


def broadcast(msg: dict):
    data = json.dumps(msg)
    for ws in list(clients):
        asyncio.create_task(ws.send_str(data))


sessions = Sessions(lambda: sources["notes"], broadcast, float(os.environ.get("ATLAS_RECENT_HOURS", "6")))
driver = Driver(ROOT, VAULT, sessions, broadcast, addons.prompts)


def same_origin(request) -> bool:
    """Refuse requests another website made through your browser: the Origin must be this server."""
    origin = request.headers.get("Origin")
    return origin is None or urlparse(origin).netloc == request.host


async def ws_handler(request):
    if not same_origin(request):
        raise web.HTTPForbidden()
    ws = web.WebSocketResponse(heartbeat=30, compress=False)
    await ws.prepare(request)
    await ws.send_str(json.dumps({"t": "hello", "sessions": sessions.recent(), "touches": sessions.touches(), "runtime": driver.snapshot()}))
    clients.add(ws)
    try:
        async for _ in ws:
            pass
    finally:
        clients.discard(ws)
    return ws


async def config(request):
    return web.json_response({"vault": VAULT.name, "voice": VOICE and (ROOT / "voice/hook.js").is_file(),
                              "graphs": [s.info() for s in sources.values()], "addons": addons.listing(),
                              "defaultCwd": os.environ.get("ATLAS_DEFAULT_CWD", str(Path.home()))})


async def graph(request):
    src = sources.get(request.match_info["id"])
    if not src:
        raise web.HTTPNotFound()
    try:
        return web.json_response(await asyncio.to_thread(src.load))
    except (OSError, ValueError) as e:
        raise web.HTTPServiceUnavailable(text=str(e))


async def session(request):
    sid = request.match_info["id"]
    s = sessions.all.get(sid)
    if not s:
        if sid in sessions.pending:
            return web.json_response({"session": sessions.pending[sid], "history": [], "runtime": driver.snapshot()})
        raise web.HTTPNotFound()
    return web.json_response({"session": s.meta(), "history": s.history, "runtime": driver.snapshot()})


async def older(request):
    return web.json_response(await asyncio.to_thread(sessions.older))


async def adopt(request):
    if not same_origin(request):
        raise web.HTTPForbidden()
    s = sessions.adopt(request.match_info["id"])
    if not s:
        raise web.HTTPNotFound()
    await asyncio.sleep(0.4)          # let the tailer replay it
    return web.json_response({"session": s.meta()})


async def new_session(request):
    if not same_origin(request):
        raise web.HTTPForbidden()
    body = await request.json() if request.can_read_body else {}
    try:
        sid = driver.start(body.get("cwd"))
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=400)
    return web.json_response({"id": sid})


async def send(request):
    if not same_origin(request):
        raise web.HTTPForbidden()
    try:
        text = message(await request.json())
    except ValueError as e:
        return web.json_response({"error":str(e)}, status=400)
    try:
        await driver.send(request.match_info["id"], text)
    except RuntimeError as e:
        return web.json_response({"error": str(e)}, status=409)
    return web.json_response({"ok": True})


async def interrupt(request):
    if not same_origin(request):
        raise web.HTTPForbidden()
    try:
        correction = message(await request.json() if request.can_read_body else {}, allow_empty=True)
    except ValueError as e:
        return web.json_response({"error":str(e)}, status=400)
    try:
        await driver.interrupt(request.match_info["id"], correction)
    except (RuntimeError, OSError) as e:
        return web.json_response({"error": str(e)}, status=409)
    return web.json_response({"ok": True})


async def answer(request):
    if not same_origin(request):
        raise web.HTTPForbidden()
    body = await request.json()
    if not isinstance(body, dict) or not isinstance(body.get("allow"), bool):
        raise web.HTTPBadRequest(text="An explicit allow or deny answer is required")
    try:
        await driver.answer(request.match_info["id"], request.match_info["rid"], body["allow"], body.get("answers"))
    except (RuntimeError, OSError) as e:
        return web.json_response({"error": str(e)}, status=409)
    return web.json_response({"ok": True})


def preview_path(sid, raw):
    s = sessions.all.get(sid)
    pending = sessions.pending.get(sid)
    cwd = Path(s.cwd if s and s.cwd else pending["cwd"] if pending else VAULT).resolve()
    roots = [VAULT.resolve(), cwd, *[Path(r).resolve() for r in load_repos()]]
    p = Path(raw).expanduser()
    p = (p if p.is_absolute() else cwd / p).resolve()
    if not any(p.is_relative_to(r) for r in roots):
        raise web.HTTPForbidden(text="This file is outside the session's project and vault")
    if not p.is_file():
        raise web.HTTPNotFound(text="File not found")
    if p.stat().st_size > 32 * 1024 * 1024:
        raise web.HTTPRequestEntityTooLarge(max_size=32 * 1024 * 1024, actual_size=p.stat().st_size)
    return p


async def preview(request):
    if not same_origin(request):
        raise web.HTTPForbidden()
    sid, raw = request.match_info["id"], request.query.get("path", "")
    if not raw or (sid not in sessions.all and sid not in sessions.pending):
        raise web.HTTPBadRequest(text="Choose a session and file")
    p = preview_path(sid, raw)
    mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    if request.query.get("raw") == "1":
        if mime not in ("image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf"):
            mime = "application/octet-stream"
        resp = web.FileResponse(p)
        resp.content_type = mime
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Content-Security-Policy"] = "sandbox; default-src 'none'"
        return resp
    if mime in ("image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf"):
        return web.json_response({"name": p.name, "path": str(p), "kind": "pdf" if mime == "application/pdf" else "image"})
    if p.stat().st_size > 1024 * 1024:
        raise web.HTTPBadRequest(text="Text preview is limited to 1 MB")
    try:
        text = p.read_text(encoding="utf-8")
    except UnicodeError:
        raise web.HTTPBadRequest(text="This file type cannot be previewed")
    return web.json_response({"name": p.name, "path": str(p), "kind": "markdown" if p.suffix.lower() == ".md" else "text", "text": text})


async def index(request):
    return web.FileResponse(STATIC / "index.html")


@web.middleware
async def no_cache(request, handler):
    resp = await handler(request)
    resp.headers.setdefault("Cache-Control", "no-cache")
    return resp


CODE_CACHE = Path(os.environ.get("ATLAS_CODE_CACHE", ROOT / ".code-cache")).expanduser()
CODE_POLL = float(os.environ.get("ATLAS_CODE_POLL", "3"))


def build_code(repos: list[str]) -> bool:
    script = ROOT / "scripts" / "build_code_graph.py"
    try:
        subprocess.run([sys.executable, str(script), "--cache", str(CODE_CACHE), *repos], check=True,
                       stdout=subprocess.DEVNULL)
        return True
    except (subprocess.CalledProcessError, OSError) as e:
        print("code graph build failed:", e, flush=True)
        return False


async def watch_code_repos():
    """Rebuild the code graph in a thread whenever the configured repo list changes; requests never wait on it."""
    if os.environ.get("ATLAS_CODE_GRAPH"):
        return
    done = None
    while True:
        repos = load_repos()
        if repos != done:
            if not repos:
                sources.pop("code", None)
                done = repos
            elif await asyncio.to_thread(build_code, repos):
                sources["code"] = JsonFileSource("code", "Code", CODE_CACHE / "code-graph.json")
                done = repos
                print(f"code graph ready: {len(repos)} repos", flush=True)
            else:
                done = repos      # don't retry a failing list until it changes
        await asyncio.sleep(CODE_POLL)


async def cleanup(app):
    for task in app.get("tasks", []):
        task.cancel()
    await asyncio.gather(*app.get("tasks", []), return_exceptions=True)
    await driver.close()


async def start_background(app):
    app["tasks"] = [asyncio.create_task(sessions.run()), asyncio.create_task(watch_code_repos())]


def main():
    if not VAULT.is_dir():
        raise SystemExit(f"No vault at {VAULT}. Run ./setup.sh first, or set ATLAS_VAULT.")
    app = web.Application(middlewares=[no_cache], client_max_size=REQUEST_LIMIT)
    app.router.add_get("/", index)
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/api/config", config)
    app.router.add_get("/api/graph/{id}", graph)
    app.router.add_get("/api/session/{id}", session)
    app.router.add_get("/api/sessions/older", older)
    app.router.add_post("/api/sessions/new", new_session)
    app.router.add_post("/api/session/{id}/adopt", adopt)
    app.router.add_post("/api/session/{id}/send", send)
    app.router.add_post("/api/session/{id}/interrupt", interrupt)
    app.router.add_post("/api/session/{id}/permission/{rid}", answer)
    app.router.add_get("/api/session/{id}/preview", preview)
    app.router.add_static("/static/", STATIC)
    (ROOT / "addons").mkdir(exist_ok=True)
    app.router.add_static("/addons/", ROOT / "addons")
    (ROOT / "voice").mkdir(exist_ok=True)
    app.router.add_static("/voice/", ROOT / "voice")
    addons.setup(app, {"vault": VAULT, "broadcast": broadcast, "sessions": sessions, "root": ROOT})
    app.on_startup.append(start_background)
    app.on_cleanup.append(cleanup)
    web.run_app(app, host="127.0.0.1", port=PORT,
                print=lambda *_: print(f"Atlas baseline on http://localhost:{PORT} · vault {VAULT}", flush=True))


if __name__ == "__main__":
    main()

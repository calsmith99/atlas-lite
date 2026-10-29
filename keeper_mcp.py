#!/usr/bin/env python3
"""The vault keeper as a small MCP server (stdio, no dependencies): new_note, write_note, edit_note, append_log.

    python3 keeper_mcp.py <vault> <changed.jsonl>

Both Claude Code and Codex are started with this server for the turn. A write that breaks a rule comes back as a tool
error naming the rule and the fix, so the assistant corrects it and tries again.
"""
import json
import sys
from pathlib import Path

from keeper import TYPES, Keeper, NoteRejected

TOOLS = {
    "new_note": ("Get the template for a new note. Fill it in, then pass the whole text to write_note. type is reference, research, project, incident or log.",
                 {"type": "string", "title": "string", "tags": "string"}, ["type", "title"]),
    "write_note": ("Create a note. type is reference, research, project, incident or log; name is the file name (no folder). The text must follow the template from new_note.",
                   {"type": "string", "name": "string", "text": "string"}, ["type", "name", "text"]),
    "edit_note": ("Replace one exact occurrence of old with new in an existing note (path like Reference/Name.md). Also use it to add a link to a hub.",
                  {"path": "string", "old": "string", "new": "string"}, ["path", "old", "new"]),
    "append_log": ("Append today's diary line '- HH:MM [Topic] text'. The time is added for you.",
                   {"topic": "string", "text": "string"}, ["topic", "text"]),
}


def call(keeper: Keeper, name: str, a: dict):
    if name == "new_note":
        if a["type"] not in TYPES:
            raise NoteRejected([f"type: {a['type']!r} is not one of {', '.join(TYPES)}"])
        tags = [t.strip() for t in str(a.get("tags", "")).split(",") if t.strip()]
        return keeper.new_note(a["type"], a["title"], tags)
    if name == "write_note":
        return json.dumps(keeper.write_note(a["type"], a["name"], a["text"]))
    if name == "edit_note":
        return json.dumps(keeper.edit_note(a["path"], a["old"], a["new"]))
    if name == "append_log":
        return json.dumps(keeper.append_log(a["topic"], a["text"]))
    raise NoteRejected([f"unknown tool {name}"])


def main():
    keeper = Keeper(Path(sys.argv[1]), Path(sys.argv[2]))
    for line in sys.stdin:
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        mid, method = msg.get("id"), msg.get("method")
        if mid is None:        # notifications need no reply
            continue
        if method == "initialize":
            result = {"protocolVersion": (msg.get("params") or {}).get("protocolVersion", "2024-11-05"),
                      "capabilities": {"tools": {}}, "serverInfo": {"name": "vault", "version": "1.0"}}
        elif method == "tools/list":
            result = {"tools": [{"name": n, "description": d, "inputSchema": {
                "type": "object", "properties": {k: {"type": t} for k, t in props.items()}, "required": req,
                "additionalProperties": False}} for n, (d, props, req) in TOOLS.items()]}
        elif method == "tools/call":
            p = msg.get("params") or {}
            try:
                if p.get("name") not in TOOLS:
                    raise NoteRejected([f"unknown tool {p.get('name')}"])
                args = p.get("arguments") or {}
                miss = [k for k in TOOLS[p["name"]][2] if not isinstance(args.get(k), str)]
                if miss:
                    raise NoteRejected([f"arguments: {', '.join(miss)} must be given as text"])
                result = {"content": [{"type": "text", "text": call(keeper, p["name"], args)}]}
            except NoteRejected as e:
                result = {"content": [{"type": "text", "text": str(e)}], "isError": True}
            except Exception as e:  # never kill the server on one bad call
                result = {"content": [{"type": "text", "text": f"error: {e}"}], "isError": True}
        elif method == "ping":
            result = {}
        else:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "method not found"}}) + "\n")
            sys.stdout.flush()
            continue
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid, "result": result}) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()

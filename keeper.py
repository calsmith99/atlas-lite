"""Vault keeper (ported from Atlas v2): write-time note rules as code, templates per type, the in-turn log line, changed.jsonl.

Every write goes through `write_note`, `edit_note` or `append_log`. A write that breaks a rule raises `NoteRejected`
whose message names each rule and the fix, so the model can act on it. Nothing here calls a model.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

SIZE_CAP = 10 * 1024
FOLDERS = ("Reference", "Research", "Projects", "Logs", "Extras")
NOTE_FOLDERS = FOLDERS[:4]            # Extras holds attachments, not notes
ROOT_NOTES = {"Index.md", "CLAUDE.md", "AGENTS.md"}
FIELDS = ("tags", "status", "updated", "verified")
TEMPLATES = Path(__file__).parent / "templates"

# type -> (folder, required section headings in order). Type lives in tags; the vault bans a `type` field.
TYPES: dict[str, tuple[str, tuple[str, ...]]] = {
    "reference": ("Reference", ("Notes", "Sources")),
    "research": ("Research", ("Question", "Findings", "What would settle it", "Sources")),
    "project": ("Projects", ("Decided", "Open", "Things to deliberately not revisit", "TODO")),
    "incident": ("Logs", ("Event", "Evidence", "Impact", "Causes", "Attempts and decisions", "Outcome", "Sources")),
    "log": ("Logs", ("Worked on",)),
}

CREDENTIALS = [
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"), "an sk- API key"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"), "a GitHub token"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "an AWS access key id"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), "a Slack token"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "a private key block"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{24,}"), "a bearer token"),
    (re.compile(r"(?i)\b(?:password|passwd|secret|api[_-]?key|token)\b\s*[:=]\s*[\"']?(?!\s)(?![\w-]*(?:\.env|<|\{|\$|your|example|xxx))[A-Za-z0-9/+_!@#%^&*.-]{12,}"),
     "a password, secret, key or token assigned a literal value"),
]
LOG_LINE = re.compile(r"^- (?:[01]\d|2[0-3]):[0-5]\d \[[^\]\n]+\] \S.*$")


class NoteRejected(ValueError):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("Note rejected: " + " | ".join(problems))


def split_frontmatter(text: str) -> tuple[dict[str, str] | None, str]:
    m = re.match(r"---\n(.*?)\n---\n?", text, re.S)
    if not m:
        return None, text
    fm: dict[str, str] = {}
    for line in m.group(1).splitlines():
        k, sep, v = line.partition(":")
        if sep:
            fm[k.strip()] = v.split(" #")[0].strip()
    return fm, text[m.end():]


def _wrapped_paragraphs(body: str) -> list[str]:
    """Prose paragraphs of two or more plain lines in a row: a hard-wrapped paragraph. Lists, tables, headings, quotes,
    code, html, callouts and blank-separated lines are not prose paragraphs."""
    out, run, fence = [], [], False

    def flush():
        if len(run) >= 2:
            out.append(run[0][:50])
        run.clear()

    for line in body.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
            flush()
            continue
        plain = (not fence and line.strip() and not re.match(r"\s*([-*+>|#<]|\d+[.)]|\[|!\[|---|===|\$\$|<)", line)
                 and not line.startswith(("  ", "\t")) and not line.rstrip().endswith("  "))
        if plain:
            run.append(line)
        else:
            flush()
    flush()
    return out


def validate(rel: str, text: str, note_type: str | None = None) -> list[str]:
    """Reasons a note at vault-relative path `rel` with this text breaks a rule; empty means it is fine."""
    problems: list[str] = []
    parts = Path(rel).parts
    is_log = len(parts) > 1 and parts[0] == "Logs"
    if not rel.endswith(".md"):
        problems.append("name: a note file ends in .md")
    if len(parts) == 1:
        if rel not in ROOT_NOTES:
            problems.append(f"folder: the vault root holds only Index.md, CLAUDE.md and AGENTS.md; put this in one of {', '.join(NOTE_FOLDERS)}")
    elif parts[0] not in FOLDERS:
        problems.append(f"folder: {parts[0]}/ is not a vault folder; use one of {', '.join(NOTE_FOLDERS)}")
    elif len(parts) > 2:
        problems.append(f"nesting: folders do not nest, so {'/'.join(parts[:-1])}/ is wrong; use {parts[0]}/{parts[-1]}")
    size = len(text.encode())
    if size > SIZE_CAP and not is_log:
        problems.append(f"size: {size} bytes is over the {SIZE_CAP} byte cap; split it by topic into sibling notes behind a short hub")
    fm, body = split_frontmatter(text)
    if rel not in ROOT_NOTES:
        if fm is None:
            problems.append("frontmatter: missing; start with --- then tags, status, updated, verified, then ---")
        else:
            miss = [f for f in ("tags", "status", "updated") if f not in fm]
            if miss:
                problems.append(f"frontmatter: missing {', '.join(miss)}")
            if "type" in fm or "related" in fm or "parent" in fm:
                problems.append("frontmatter: type, related and parent are not allowed; the type goes in tags")
            if fm.get("updated") and not re.fullmatch(r"\d{4}-\d\d-\d\d", fm["updated"]):
                problems.append("frontmatter: updated must be YYYY-MM-DD")
    if re.search(r"(?m)^## Related\s*$", body):
        problems.append("related: remove the '## Related' section; link from the text or a hub note instead")
    wrapped = _wrapped_paragraphs(body)
    if wrapped:
        problems.append(f"wrapping: hard-wrapped paragraph starting {wrapped[0]!r}; write each paragraph on one line "
                        f"({len(wrapped)} found)")
    for rx, what in CREDENTIALS:
        if rx.search(text):
            problems.append(f"credential: looks like {what}; credentials never go in a note, say where they live instead")
            break
    if note_type:
        if note_type not in TYPES:
            problems.append(f"type: {note_type!r} is not one of {', '.join(TYPES)}")
        else:
            folder, sections = TYPES[note_type]
            if parts[0] != folder:
                problems.append(f"type: a {note_type} note lives in {folder}/")
            heads = re.findall(r"(?m)^## (.+?)\s*$", body)
            missing = [s for s in sections if s not in heads]
            if missing:
                problems.append(f"template: a {note_type} note needs sections {', '.join('## ' + s for s in missing)}")
    return problems


def render_template(note_type: str, title: str, tags: list[str], today: str) -> str:
    return (TEMPLATES / f"{note_type}.md").read_text().format(title=title, tags=", ".join(tags), today=today)


@dataclass
class Keeper:
    vault: Path
    changed: Path
    now: Callable[[], datetime] = datetime.now

    def __post_init__(self):
        self.vault = Path(self.vault).resolve()
        self.changed = Path(self.changed)

    def _inside(self, rel: str):
        p = (self.vault / rel).resolve()
        if self.vault not in p.parents:
            raise NoteRejected([f"path: {rel} is outside the vault"])
        return p

    def _record(self, rel: str, text: str, note_type: str | None) -> dict:
        row = {"path": rel, "size": len(text.encode()), "type": note_type, "ts": time.time()}
        self.changed.parent.mkdir(parents=True, exist_ok=True)
        with self.changed.open("a") as f:
            f.write(json.dumps(row) + "\n")
        return row

    def _commit(self, rel: str, text: str, note_type: str | None) -> dict:
        problems = validate(rel, text, note_type)
        if problems:
            raise NoteRejected(problems)
        p = self._inside(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return {**self._record(rel, text, note_type), "unlinked": self.orphan_hint(rel)}

    def new_note(self, note_type: str, title: str, tags: list[str]) -> str:
        """Scaffold text for a new note of a type. It is not written until write_note validates a filled-in copy."""
        return render_template(note_type, title, tags, f"{self.now():%Y-%m-%d}")

    def write_note(self, note_type: str, name: str, text: str) -> dict:
        if note_type not in TYPES:
            raise NoteRejected([f"type: {note_type!r} is not one of {', '.join(TYPES)}"])
        folder = TYPES[note_type][0]
        rel = f"{folder}/{name}" if "/" not in name else name
        if not rel.endswith(".md"):
            rel += ".md"
        if self._inside(rel).exists():
            raise NoteRejected([f"exists: {rel} already exists; use edit_note to change it"])
        return self._commit(rel, text, note_type)

    def edit_note(self, rel: str, old: str, new: str) -> dict:
        p = self._inside(rel)
        if not p.is_file():
            raise NoteRejected([f"missing: {rel} does not exist; use write_note to create it"])
        cur = p.read_text()
        if cur.count(old) != 1:
            raise NoteRejected([f"edit: the old text must appear exactly once in {rel} (found {cur.count(old)})"])
        text = cur.replace(old, new)
        return self._commit(rel, text, None)

    def append_log(self, topic: str, text: str) -> dict:
        """Append `- HH:MM [Topic] text` to today's log, creating the file if absent. No model call."""
        t = self.now()
        line = f"- {t:%H:%M} [{topic.strip()}] {text.strip()}"
        if "\n" in line or not LOG_LINE.match(line):
            raise NoteRejected(["log: the line must be '- HH:MM [Topic] text' on one line with a non-empty topic and text"])
        for rx, what in CREDENTIALS:
            if rx.search(line):
                raise NoteRejected([f"credential: looks like {what}; credentials never go in a note"])
        rel = f"Logs/{t - timedelta(hours=5):%Y-%m-%d}.md"      # the diary day runs to 05:00
        p = self.vault / rel
        if p.exists():
            cur = p.read_text()
            out = cur + ("" if cur.endswith("\n") else "\n") + line + "\n"
        else:
            out = render_template("log", "", [], f"{t:%Y-%m-%d}") + line + "\n"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(out)
        return self._record(rel, out, "log")

    # -- links: every note should be reachable from Index or a hub
    LINK = re.compile(r"\[\[([^\]|#^]+)(?:[#^][^\]|]*)?(?:\|[^\]]*)?\]\]")

    def notes(self) -> list[Path]:
        out = []
        for folder in NOTE_FOLDERS:
            d = self.vault / folder
            if d.is_dir():
                out += [p for p in d.glob("*.md") if folder != "Logs"]       # dated logs are not hubs' children
        return out

    def link_map(self) -> dict[str, set[str]]:
        """note stem (lower case) -> stems of the notes that link to it, from every note, Index and the logs."""
        files = self.notes() + [p for p in self.vault.glob("*.md") if p.name in ROOT_NOTES or p.name == "Index.md"]
        inbound: dict[str, set[str]] = {}
        for p in files:
            try:
                text = p.read_text(errors="replace")
            except OSError:
                continue
            for m in self.LINK.finditer(text):
                target = m.group(1).strip().split("/")[-1].lower()
                if target != p.stem.lower():
                    inbound.setdefault(target, set()).add(p.stem)
        return inbound

    def orphans(self) -> list[str]:
        """Notes (vault-relative) that no other note links to."""
        inbound = self.link_map()
        return sorted(str(p.relative_to(self.vault)) for p in self.notes() if p.stem.lower() not in inbound)

    def orphan_hint(self, rel: str) -> str:
        if Path(rel).parts[0] not in NOTE_FOLDERS or Path(rel).parts[0] == "Logs":
            return ""
        stem = Path(rel).stem.lower()
        return "" if stem in self.link_map() else f"nothing links to [[{Path(rel).stem}]] yet; link it from Index or the hub note it belongs under"

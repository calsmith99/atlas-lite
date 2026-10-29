---
name: vault-writing
description: Read BEFORE creating, editing or reshaping any note in this vault. Decides whether something is worth saving, where it goes, and the exact shape and voice to write it in. Notes are written with the vault tools, which enforce these rules.
---

# Vault writing

## Tools

Write notes only with the vault tools (`mcp__vault__*` in Claude, `vault` tools in Codex). They check every rule below and answer with the rule and fix when one is broken; correct it and try again.

| Tool | Use |
| ---- | ---- |
| `new_note` | Get the template for a type (`reference`, `research`, `project`, `incident`, `log`) with the title and tags filled in. Fill it in, then pass the whole text to `write_note`. |
| `write_note` | Create a note. Fails if it exists; folder comes from the type. |
| `edit_note` | Replace one exact piece of text in an existing note. Also how you add a link to a hub. |
| `append_log` | Add today's diary line `- HH:MM [Topic] text`. One line, plain words, past tense, under 12 words. |

If `write_note` says nothing links to the new note, add the link with `edit_note` before you finish (to `Index.md`, or to the hub note it belongs under).

## Gate: is it worth saving?

Save distilled conclusions: current setup, changes actually made, decisions with their reasons, research conclusions, fixes for recurring problems. Do not save prices, offers, links, one-off lookups or a narrative of the session. Search for an existing note and update it before creating one. When the user states a fact about their life or work, that is worth saving.

## Folders

A closed set; nothing nests. The root holds only `Index.md`, `CLAUDE.md` and `AGENTS.md`.

| Folder | Holds | Temporal? |
| ---- | ---- | ---- |
| `Reference/` | Things that exist: people, places, setups, standing facts, and hub notes | No, current state only |
| `Research/` | Open investigations and per-topic decision logs | Yes, keeps history |
| `Projects/` | One note per project | Yes |
| `Logs/` | Things that happened: the diary, incident reports. Dated | Yes, immutable |
| `Extras/` | Images and attachments | |

A folder exists only for a kind of thing. There are no subject folders: a subject (health, the house, a hobby) is a **hub note** in `Reference/` that links to its notes. A tag spread across several notes means a hub is wanted.

## Links and names

- Structure comes from hub notes and `[[wikilinks]]`. Every note is linked from `Index.md` or from a hub that `Index.md` links to.
- Names are globally unique and self-describing (`[[Home Network]]`, not `[[Network]]`), because a link carries no path.
- Every fact has one owner note; other notes link to it rather than restating it.

## Rules

1. `Reference/` is fact only: what exists and how it is now. Plans, ideas, options and open questions go in their own `Research/` note, linked from the Reference note in one line. Superseded state goes in a `## History` section at the bottom of that note.
2. Never append a session write-up to an existing note. Findings get their own note, linked by one line.
3. Anything with its own setup or procedure gets its own note; the parent lists it in one line.
4. Incidents are `Logs/YYYY-MM-DD <Topic>.md` (type `incident`): what happened, evidence, impact, causes, what was tried and why, outcome. Link it from the affected note under `## Incidents` as a bare link. Keep unknown causes explicit.
5. Credentials never go in a note; say where they live.
6. No `## Related` section (hubs excepted). No manual line wrapping: one paragraph is one line; prefer a table row or one-line bullet.
7. Keep notes small and single-topic (about 2 to 6 KB; the hard cap is 10 KB). Past that, split by topic into sibling notes behind a short hub. Logs may stay whole.
8. One-off to-dos are `- [ ]` checkboxes under `## TODO` in the note that owns them.

## Frontmatter

```yaml
---
tags: [tag, another]
status: active | open | decided | done | archived
updated: YYYY-MM-DD
verified: YYYY-MM-DD    # last checked against reality; leave empty rather than guess
---
```

No `type:`, `related:` or `parent:`; the type goes in tags. A note opens with a one-line italic summary (`_What this note holds._`): it is the link preview, so make it good.

## Voice

Notes are the user's, written in their voice: first person ("I run backups on Sundays") or impersonal ("Decided 2026-09-04"), never by name in the third person. Notes state facts, never instructions to the assistant; assistant behaviour belongs in `CLAUDE.md` or `AGENTS.md`.

## Sources

Claims that need backing go in `## Sources`: a URL, a file path, the command the output came from, or "Decided, YYYY-MM-DD". Never "Source: the assistant".

## Before finishing

Every added line is durable and not duplicated elsewhere, and every new note is linked. Do not commit or push.

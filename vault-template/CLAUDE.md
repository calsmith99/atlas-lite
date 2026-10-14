# Notes vault

My notes: what I find while investigating work, and how the things I work with actually behave. Kept locally and edited in Obsidian. The point is to build up findings so the next investigation starts from what is already known.

**Start at [[Index]].**

- **Check the vault first.** Before investigating a ticket or topic, search here for its key, the feature and the services involved. Past findings beat rediscovering them.
- **Write findings as you go, not at the end.** Several sessions may run at once, and any of them may be closed without a wrap-up. When something is learned (a cause, how a feature really works, a query that answers a question, a dead end), put it in the vault in the same turn.
- **Never put credentials, tokens or customer personal data in a note.** Client names and IDs are fine; email addresses, phone numbers and the like are not. Say where secrets live instead.

## Folders

Closed set, nothing nests.

| Folder | Holds |
| ---- | ---- |
| `Tickets/` | One note per ticket: `<KEY> <short title>.md`, e.g. `ABC-123 Login fails on mobile.md` |
| `Reference/` | Things that exist and stay true: features, services, endpoints, permissions, data tables, clients, people, recurring issues |
| `Logs/` | Dated notes: `YYYY-MM-DD.md` for the day, or `YYYY-MM-DD <Topic>.md` for an incident |

Names are globally unique and self-describing, since a wikilink carries no path. Link liberally with `[[wikilinks]]`; dangling links are fine and mark a note worth writing.

## Note shapes

Every note starts with frontmatter and an italic one-line opener saying what it is (it's the link preview):

```yaml
---
tags: [free-form]
status: open | done | active
updated: YYYY-MM-DD
---
```

- **Ticket note:** opener with the client and the symptom; `## Findings` (bullets, newest last, each a fact not a narrative); `## Cause` once known; `## Fix` or outcome; `## Open` for what's still unknown. Link every feature, service and client it touches.
- **Reference note:** opener; `## Notes` bullets of current truth. When a ticket teaches something durable about a feature or service, it goes here too, with one line in the ticket linking to it. Superseded facts move to a `## History` section at the bottom.
- **Recurring issue:** a `Reference/` note listing the tickets that hit it, so a pattern is visible.

## Voice

First person or impersonal ("Confirmed 2026-10-07"), terse, facts over narrative. Save the conclusion, not the process. No manual line wrapping.

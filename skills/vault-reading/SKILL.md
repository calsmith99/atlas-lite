---
name: vault-reading
description: Read whenever a question asks for information, anything is uncertain, or extra context could help; search the vault before answering from general knowledge or guessing.
---

# Vault reading

The vault is small linked notes behind hubs. Read the least that answers the question, but follow links until the picture is complete; never answer from one note when it links to the owner of the data.

## Finding notes

1. Start at `Index.md`, then the hub it names for the topic.
2. Search by name and by content with your normal file search (`grep -ril`, `ls Reference`). Names are unique and self-describing.
3. Read a note directly when it is small. For a large one, read its headings first, then the section you need.
4. Follow the `[[wikilinks]]` in the note you read to the notes that own the facts it mentions.

## Which note owns the data

| Data | Owner |
| ---- | ---- |
| How something is now (a setup, a person, a place) | its `Reference/` note |
| Why something was decided, what was investigated | `Research/` |
| What happened on a day, an incident | `Logs/` |
| The state of a project | its `Projects/` note |

A `Research/` note is never the source for current state; check the `Reference/` note it links to. Read `Logs/` only for history questions.

## Trust

- `verified:` is the last check against reality; `updated:` is only the last edit. An empty `verified` means never checked.
- A claim with no `## Sources` entry and no `verified` date gets re-checked against the real thing before anything relies on it.
- When a note and reality disagree, or two notes disagree and it matters, ask the user one specific question quoting both, then fix the note with the vault tools.
- Never state something as fact that you have not looked up this session.

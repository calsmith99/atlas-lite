---
tags: [guide]
status: active
updated: 2026-01-01
verified:
---

_How Atlas Lite works and why it is built this way, so you can change it knowing what each part is for._

## Notes

- **A dashboard around your own assistant.** Atlas Lite is a small local page that runs your own Claude Code or Codex, one message at a time, with this vault as its working folder. It does not install anything into `~/.claude` or `~/.codex`, so stopping Atlas leaves your own setup exactly as it was.
- **Local only.** The page is served on your machine at `localhost` and cannot be reached from the network. Your notes never leave the machine except through the assistant you already use.
- **The globe is your notes.** Each note is a point, each link between notes is an arc, and a note flares when the assistant reads or writes it. It exists to show the vault is alive and how connected it is.
- **Notes are written through checked tools.** The assistant files notes with `new_note`, `write_note`, `edit_note` and `append_log`, which refuse a write that breaks the rules and say how to fix it. This is why every note has the right shape and is linked from [[Index]] or a hub, however long the vault grows. See [[Vault Guide]].
- **A check after every turn.** Anything written another way is validated afterwards, and problems go back to the assistant to fix once.
- **A scribe catches what was missed.** If a real exchange ended with nothing filed, a small background run saves whatever was worth keeping. It is on by default and the `scribe` setting turns it off.
- **Permissions.** Commands and writes outside the vault open an Allow or Deny screen. The permissions picker under the message box sets how much is asked: Ask each time, Accept edits, Auto, Plan (read-only) or Bypass for Claude; Edit files or Read-only for Codex. It applies from the next message.
- **Model and effort.** The pickers beside it choose the model and how hard it thinks. Higher effort is slower and uses more of your allowance.
- **Project folders.** Folders you name in setup are readable and editable by the assistant besides the vault, while notes about each project stay here. Ask the assistant to add or remove one. The list is the `project_dirs` setting.
- **Where things live.** Settings are in `~/.atlas-lite/config.json`, your theme and dashboard additions in `~/.atlas-lite/theme/`, the conversation in `~/.atlas-lite/conversation.json`, and every note written is logged in `~/.atlas-lite/changed.jsonl`.
- **Updates.** The rules block in this vault's `CLAUDE.md` and `AGENTS.md` and the `vault-writing` and `vault-reading` skills are refreshed on every start. Edit `CLAUDE.md` outside the marked block; anything inside it is overwritten. Your theme survives updates.
- **Changing it.** See [[Changing Atlas]] for what can be changed and how to ask.
- Back to [[Index]].

## Sources

- Decided, 2026-01-01

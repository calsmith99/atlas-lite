# Atlas Lite

A small dashboard that wraps your own Claude Code **or** Codex: a conversation panel, a globe of your notes, and your usage. Designed for you to customise and make it fit your needs.

## Run

You need Python 3 and either `claude` or `codex` installed and logged in. Nothing else to install.

    git clone https://github.com/calsmith99/atlas-work
    cd atlas-work
    ./run.sh

It opens http://localhost:11800. The first run creates a notes vault at `~/Atlas Vault` and your settings at `~/.atlas-lite/config.json`. Click **Start setup** and your assistant walks you through the rest, one question at a time.

Atlas Lite never touches `~/.claude` or `~/.codex`. Stop using it and your own setup is as it was.

## How it works

- **Notes** are plain Markdown files in the vault (Obsidian optional). The assistant writes them through checked tools that enforce small, single-topic, linked notes, and a background scribe files anything worth keeping that it missed. Set `"scribe": false` to stop that.
- **The globe** shows your notes and their links. Click a star to read the note over it.
- **Permissions:** the pickers under the message box set model, effort and how much the assistant asks first. Claude opens an Allow or Deny screen for commands outside the vault; Codex runs in a sandbox that can write only to the vault and `~/.atlas-lite`.
- **Project folders** you name in setup are readable and editable by the assistant too.
- **Make it yours:** ask the assistant for a theme, a card or a different globe. Your changes live in `~/.atlas-lite/theme` and survive updates.

## Config

`~/.atlas-lite/config.json`: `name`, `provider` (`claude` or `codex`), `vault`, `port`, `permission_mode`, `model`, `effort`, `voice`, `scribe`, `project_dirs`. Environment overrides: `ATLAS_HOME`, `ATLAS_VAULT`, `ATLAS_PROVIDER`, `ATLAS_PORT`.

More detail is in the Atlas Guide note inside every new vault.

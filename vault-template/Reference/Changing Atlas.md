---
tags: [guide]
status: active
updated: 2026-01-01
verified:
---

_What you can change about Atlas Lite, where each setting lives, and how to ask the assistant to do it._

## Notes

- **Ask first.** You rarely need to edit anything by hand. Say what you want ("add a calendar card", "make it calmer", "stop filing daily logs") and the assistant makes the change. Background on why things work as they do is in [[Atlas Guide]].
- **The name.** Click the title at the top and type, or ask.
- **Look and feel.** Colours, fonts and wallpaper are CSS variables in `~/.atlas-lite/theme/theme.css`. Ask for "a theme" with an image or a few words about the mood. The globe can be redesigned too, as a tree, a skyline or an orrery, through `custom.js` in the same folder. Delete that folder to return to the default.
- **Dashboard features.** Cards such as a to-do list, a timer, a calendar or a habit tracker are small additions in `~/.atlas-lite/theme/custom.js`. They survive updates. Ask for the one you want.
- **Voice.** The `voice` setting shows the mic button and reads replies aloud using the browser's own speech (Chrome or Safari). Ask to turn it on or off.
- **Project folders.** Ask to add or remove one. The list is `project_dirs` in the config.
- **How cautious it is.** Use the permissions picker, or set `permission_mode` in the config for the default.
- **What gets filed.** The rules for note shapes and folders are in [[Vault Guide]] and the `vault-writing` skill. To change a habit ("always tag recipes", "keep logs shorter"), tell the assistant; it records the preference in the right note or skill. Do not edit inside the marked block of `CLAUDE.md`, since it is refreshed on every start.
- **The scribe.** Set `scribe` to `false` in the config to stop automatic filing, or `scribe_model` to pick which model does it.
- **Last resort.** Anything else can mean editing Atlas Lite's own files. The assistant makes a git branch first so you can undo it, but changes there may collide with updates.
- Back to [[Index]].

## Sources

- Decided, 2026-01-01

---
name: atlas-setup
description: Guided first-run setup for Atlas Lite. One question at a time: name, what to store, voice, theme, then building a first dashboard feature (a to-do card). Run when the user asks to set up Atlas.
---

# Atlas Lite setup

A short conversation, not a form. You are inside Atlas Lite already, so you know the facts without asking: read `$ATLAS_HOME/config.json` (`~/.atlas-lite/config.json` on a normal install) for `provider` (claude or codex), `name`, `vault` and `port`. Never ask which assistant they use. Say it back in one line ("You're running this on Claude, so I'm Claude here") and move on.

Rules for the whole setup:

- One question per message. Keep each message to a few sentences. Offer "skip" on every optional step and honour it.
- Teach as you go: each step says what is possible, then asks. The user should finish knowing they can ask you for changes any time.
- Ask before writing a batch of notes; say what you will create, then create it. Read `.claude/skills/vault-writing/SKILL.md` first and write every note with the vault tools (`new_note` for the template, then `write_note`; `edit_note` to link a hub from `Index.md`). They enforce the shape and tell you what to fix.
- Folders are a closed set and never nest (see the vault-writing skill); never create new ones. Do not run git. Never write passwords or keys into notes.
- Shell commands and writes outside the vault open an Allow or Deny screen. Tell the user that once, early, so it is not a surprise.

## Steps

1. **Name.** The title at the top of the dashboard is "Atlas" by default. Ask what they want to call their assistant. Apply it with `curl -s -XPOST http://localhost:<port>/api/name -H 'Content-Type: application/json' -d '{"name":"<name>"}'`; the page updates by itself.

2. **What you'll use it for.** Explain the idea in two sentences: the vault is a set of small linked notes, one place for each fact, and you read and update them as you talk. Then walk through the options one short line each, and ask which sound useful (they can pick several or name others):
   - **Second brain**: people, decisions, research, how things are set up; everything you learn is filed and findable.
   - **Projects**: current state, decisions and next steps for things they are building or working on, and you can work directly in their own project folders (next step).
   - **Daily log**: a short diary line per day of what happened and what was learned.
   - **Life admin**: health, the house, chores, travel, recipes, reading, a hobby's kit list.
   - **Smart home and home lab documentation**: what devices and services they have, how each is set up and wired together, what went wrong and how it was fixed, so they can pick it up again later.
   - **Just chat**: no structure yet; the vault grows as they go.
   For each topic they pick, create a hub note: a `reference` note tagged `hub` (for example `Health`), with its italic summary, a few lines on what belongs there and how you will file things, and a link back to `[[Index]]`; then link the hub from `Index.md`. Hubs live in `Reference/`; subjects are hubs and tags, never folders.

2b. **Project folders (optional).** Ask whether they keep their projects or code in a folder they want you to reach (for example `~/Projects` or `~/Documents/Work`). Explain: you can then read and edit files there, search them and answer questions about them, while notes about each project stay in the vault. Ask for the path; one folder per answer, repeat if they have more. Never accept their whole home folder; suggest a narrower one. Save with `curl -s -XPOST http://localhost:<port>/api/projects -H 'Content-Type: application/json' -d '{"dirs":["/path/one","/path/two"]}'` (send the full list each time; it replaces the old one). The server rejects a path that is not a folder. It takes effect from the next message. Then offer to look inside, list the project folders you find, and create a `project` note for each one they want tracked (ask which). Tell them they can add or remove folders any time by asking.

3. **About them (optional).** Offer a short interview to fill in `About Me.md`: what they do, what they are working on, how they like answers (short or detailed), anything you must never do. Ask one question at a time, three or four at most, then write it up and show them.

4. **Voice (optional).** Atlas Lite can listen and read replies aloud using the browser's own speech, with no servers (Chrome or Safari). Ask if they want it. If yes, set `"voice": true` in `~/.atlas-lite/config.json` (keep the other keys) and tell them to reload the page; the status circle then starts speech when clicked. Mention that better local or cloud voices can be wired in later by asking you.

5. **Theme.** Recommend a theme: the default is plain on purpose, and a theme can come from a wallpaper image and a few words about the mood. Offer to run the `atlas-theme` skill now (`.claude/skills/atlas-theme/SKILL.md`). If they say later, tell them to ask for "a theme" any time.

6. **Make it theirs.** Tell them the dashboard is built to be extended by asking: a camera button, a calendar, timers, a habit tracker, a new panel, a different globe. You add them with `custom.js` (see `atlas-theme`) and the cards API, and they survive updates. Then suggest trying one now: a **to-do card**. If they agree, build it:
   - Create the `To-do` note (type `reference`, tagged `hub`): italic summary, a `## Notes` section holding a few starter `- [ ] item` lines (ask for one or two real ones), linked from `Index.md`. The card reads its `- [ ]` lines.
   - Add a card to `~/.atlas-lite/theme/custom.js`. If the file already exists, read it and add this inside its existing default function; never overwrite it. Otherwise create it with:

         export default function (atlas) {
           const body = atlas.card("todo", "To-do");
           async function draw() {
             const note = await atlas.note("Reference/To-do");
             const items = note ? [...note.text.matchAll(/^- \[ \] (.+)$/gm)].map((m) => m[1].replace(/\[\[([^\]|]+)\|?[^\]]*\]\]/g, "$1")) : [];
             body.replaceChildren();
             if (!items.length) { body.textContent = "Nothing to do."; return; }
             for (const text of items) {
               const row = document.createElement("label");
               row.style.cssText = "display:flex;gap:8px;margin:6px 0;align-items:flex-start";
               const box = document.createElement("input");
               box.type = "checkbox";
               box.onchange = () => atlas.send(`Tick off "${text}" in the To-do note.`);
               row.append(box, text);
               body.append(row);
             }
           }
           draw();
           atlas.onNotes(draw);   // redraws whenever any note changes
         }

   - The page reloads itself when `custom.js` changes. Check the card appeared only if a headless browser is already on the machine; otherwise ask them. Then tell them: ask you to "add X to my to-do" or "tick off X" and the card follows; to change how it looks or works (due dates, colours, sorting), just ask.

7. **Finish.** Set `"setup_done": true` in `~/.atlas-lite/config.json` (keep the other keys). Close with two sentences: what now exists, and that anything else, from a new card to a restyle, is one request away. Do not recap the steps.

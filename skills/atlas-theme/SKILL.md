---
name: atlas-theme
description: Create or change the Atlas Lite dashboard theme from a wallpaper image and/or a described vibe. Writes only to ~/.atlas-lite/theme/.
---

# Atlas Lite theme

Atlas Lite's whole look is a set of CSS variables. The theme folder is `$ATLAS_THEME_DIR` (set for you; it is `~/.atlas-lite/theme` on a normal install). A user's theme is one file, `theme.css`, in that folder, plus any images and `custom.js` it uses. Everywhere below, `~/.atlas-lite/theme/` means `$ATLAS_THEME_DIR`: always write there, never to a literal `~/.atlas-lite` path. It is laid on top of the shipped `theme-default.css`, so any variable it leaves out keeps the default, and the open dashboard reloads it within a couple of seconds. Deleting the folder goes back to the default.

Default scope: write only inside `~/.atlas-lite/theme/` (or `$ATLAS_HOME/theme/`). Never touch `~/.claude` or `~/.codex`.

When variables are not enough (a different globe, particles, new geometry, custom animation, restyled panels), the user has asked for full customisation, so you may go further, in this order of preference:

1. **`custom.js`** in the theme folder (below). It survives updates and is removed by deleting the folder.
2. **Extra CSS** in `theme.css`. It is plain CSS laid after `style.css`, so it can restyle any element (`#chat`, `#state-panel`, `.medallion`, `#preview`, `.msg`, and so on).
3. **Editing Atlas Lite itself** (`web/app.js`, `web/style.css`, `web/index.html`, `atlas.py` in the folder named by `~/.atlas-lite/install-path`) only for things the first two cannot do. Before the first edit, run `git status` there; if the folder is a git checkout, run `git switch -c my-atlas` and commit each change, so a later `git pull` of upstream can be merged and the original restored. Tell the user their edits live in that branch. The Allow screen will ask before each edit outside the vault, which is expected.

## Steps

1. Ask what they want if they gave neither a wallpaper nor a vibe: a wallpaper image path, a few words for the mood ("warm and papery", "cold terminal", "forest at night"), or both. One question, then go.
2. Do not go looking for the defaults: every variable you may set is listed in step 4 and your file only needs the ones you change. Do not explore the install folder.
3. **Wallpaper.** If they gave an image: look at it yourself, copy it to `~/.atlas-lite/theme/wallpaper.<ext>` (jpg, png or webp; shrink to about 2560 px wide first if it is huge and `sips` or `magick` exists) and take your palette from it. If they gave none, make one that fits the vibe: author an SVG straight into `~/.atlas-lite/theme/wallpaper.svg` (2560 by 1440, layered shapes, gradients, silhouettes, a moon or sun, grain with `feTurbulence`; atmospheric, not busy, with a calm middle where the graph will sit). Never download images and never wait on an image generator.
4. Write `theme.css` with a single `:root { ... }` block:
   - `--bg`, `--card`, `--bg-2`, `--line`: base surfaces. With a wallpaper, make `--card` semi-transparent so the image shows through, and raise `--blur` a little.
   - `--text`, `--muted`: keep contrast with `--card` at 4.5:1 or better. Check it rather than guessing.
   - `--accent`, `--on-accent`: accent colour and the readable text colour on it.
   - `--backdrop`: the page background. With a wallpaper use `url(/theme/wallpaper.jpg) center / cover no-repeat` (match the extension). Without one, use a quiet gradient.
   - `--veil`: a translucent colour laid over the wallpaper so text stays readable, for example `rgba(6, 8, 14, .55)`. Tune it until the chat text is easy to read over the brightest part of the image.
   - `--globe-rim`, `--globe-shell`, `--link`, `--link-opacity`, `--node-1` to `--node-8`, `--glow`: the globe. The globe sits in the middle of the page, so make sure the links and nodes stand out against whatever the wallpaper has there.
   - Optional: `--radius` (corner roundness), `--font` (a system font stack only; no downloads), `--shadow`.
   - Set `color-scheme: light` or `dark` to match the base.
5. **The renderer: design it, do not recolour it.** Unless the user asked for simple, plain or minimal, the graph is the heart of the theme and it must express the vibe, not merely wear its colours. A theme where only colours, glow and a few particles change is a failure: swap the palettes of two different vibes and, if they would look alike, you have recoloured, not designed. The finished theme needs all of these:

   - **A structure that fits the idea**, built with `atlas.setLayout` and your own geometry: a tree whose notes are leaves on branches, a brass orrery, a skyline of towers, an archipelago, a constellation sky, a coral reef, a bookshelf, a circuit board, a river delta, ink strokes. Leave the sphere unless the vibe wants one (a sphere is itself a design, like a glass orb or an armillary). `atlas.hierarchy()` gives the notes as a tree from Index; `folder` groups them; link counts give each note a size.
   - **Notes and links drawn as things from that world**, not dots and lines: leaves, lanterns, windows, stars, shells, glyphs, towers; branches, vines, wires, threads, bridges. Hide the default points and arcs (`parts.cloud.visible = false` keeps hover and click working) and draw your own.
   - **Decoration that belongs to the style**, the way an old astronomical instrument has brass rings with engraved ticks and gilded orbs, a forest has mist and falling leaves, a night city has lit windows and rain, a manuscript has ornamented frames. Put it both in the scene (rings, particles, ground, sky objects, fog) and in the page's CSS (panel borders, corner ornaments, headings, the state circle, scrollbars, a font stack that suits), so the whole dashboard looks of a piece.
   - **Ambient life in that world's own motion**: leaves drift, embers rise, fish school, rain falls, a lantern sways.
   - **A touch effect in that world**: when the assistant reads or writes a note (`atlas.glow(id, t)` is 1 at the touch, fading over about 6 s), that leaf flares, that window lights, that star flashes.
   - **A camera and framing that show it off**: set `camera.position` and `controls.target`, tune `controls.autoRotateSpeed`, and keep the graph readable between the side panels.

   Anything three.js can draw is available. Keep it legible (notes visible, hoverable through `atlas.pickThreshold`, clickable) and smooth (a few thousand particles is fine; allocate nothing per frame in loops; prefer `InstancedMesh`).

   `examples/` beside this file holds three structure examples (`tree.js`, `orrery.js`, `skyline.js`) and `api-example.js` shows the hooks. They exist to show what is possible and how the API fits together. Do not copy their looks: design something original from the user's own words, reusing only plumbing (a stage group, `onBuild`, `onFrame`, cleanup on rebuild). If the user asks for simple, skip `custom.js` and rely on the theme variables.
6. Tell them it is applied (the page updates by itself) and what they can ask for next ("less dark", "rounder corners", "make the globe calmer", "something completely different"). To tweak, edit the same files; do not start over. Mention that they can ask for a simpler globe.

## Custom rendering: `custom.js`

`~/.atlas-lite/theme/custom.js` is an ES module. Its default export is called once, after the page has loaded, with the `atlas` object (also `window.atlas` in the browser console). The page reloads itself when the file changes.

    export default function (atlas) {
      const { THREE, parts, globe } = atlas;
      atlas.onBuild(() => { /* runs after every rebuild of the points and arcs */ });
      atlas.onFrame((t) => { /* every animation frame, t in ms */ });
    }

What `atlas` gives you:

| Member | What it is |
| ---- | ---- |
| `THREE`, `scene`, `camera`, `renderer`, `controls` | three.js and the live scene; `controls` is OrbitControls (`autoRotate`, `autoRotateSpeed`, `minDistance`) |
| `globe` | the group everything rotates with; add your own meshes here to turn with the notes |
| `parts.cloud` | `THREE.Points`, one point per note (position and colour attributes) |
| `parts.lines` | `THREE.LineSegments`, the arcs between linked notes |
| `parts.body`, `parts.rim`, `parts.graticule` | the faint sphere, its glow, its latitude and longitude lines |
| `nodes`, `positions`, `colors`, `links` | the notes (`id`, `name`, `folder`, `blurb`), their unit-sphere positions (`THREE.Vector3`), colours and links |
| `touch(id)`, `heat` | the touch effect: `touch(id)` makes a note glow as if the assistant had just read or written it; `heat` is the map of notes currently glowing |
| `css(name, fallback)` | read a theme variable, so custom code can follow the theme's colours |
| `setLayout(fn)`, `rebuild()` | `fn(nodes, links, THREE)` returns one `THREE.Vector3` per node, so the notes can sit in any shape; off-sphere layouts get straight links. `rebuild()` redraws after you change something |
| `card(id, title)`, `note(id)`, `onNotes(fn)`, `send(text)` | dashboard features (see `atlas-setup`) |

`parts.cloud` and `parts.lines` are replaced on every rebuild (a note was added, a theme changed), so restyle them inside `atlas.onBuild`, not once at start. To replace them entirely, set `parts.cloud.visible = false` in `onBuild` and add your own object to `globe`. Remove anything you add to `globe` and `scene` when it is rebuilt, or it piles up. An error in `custom.js` is logged to the browser console and never stops the page; if the globe looks wrong, tell the user to delete `custom.js` and ask you again.

Look at the page once if a headless browser is already available (see Be quick); otherwise let the user look.

## Be quick

A theme should take a few minutes, not ten. Decide the whole design in your head from their words, then: write the wallpaper (if you are making one), `theme.css`, `custom.js`, look once, adjust once at most, and finish. Each extra read, render and re-think costs the user waiting time and usage.

- Never search the filesystem (`find /`, `find ~`, `locate`): it can hang for many minutes on network drives. Every path you need is in this file or in `~/.atlas-lite/install-path`.
- Do not read files you do not need (the default theme, the install folder, other skills). This file has everything: variable names, the `atlas` API and the rules.
- Look at the result at most twice. Use a screenshot only if a headless browser is already on the machine (`command -v chromium google-chrome chrome` or the Playwright cache); never install one. Otherwise skip it: the page reloads itself, so say so and let the user look.
- Do not write long explanations afterwards. Two or three sentences: what it looks like, and what they can ask for next.

## Rules

- **"Touched" means one thing:** the assistant read or wrote that note during a turn. The page sends a touch for it and the note glows for a few seconds (the built-in glow blends the note's colour toward `--glow` and fades). It has nothing to do with the mouse: hovering a note only shows its label and tooltip, it must not leave the note highlighted afterwards, and a click opens the note. If your design replaces the points, give your version a clear touch effect (a flare, a ripple, a bloom) driven by `atlas.heat` (id to the time in ms it was touched; a touch lasts about 6 seconds) or by wrapping `atlas.touch`, and keep hover and touch visually distinct.
- Light themes need dark `--text` and a `--glow` that is dark too, or touched notes will vanish.
- Never reference remote URLs. Everything the theme uses lives in the theme folder.
- If a change looks wrong, or they want the original, remove `~/.atlas-lite/theme/theme.css` and the page returns to the default.

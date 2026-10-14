# Voice hook point

Off by default; nothing here does speech. To turn it on, put a module at `voice/hook.js` and start the server
with `ATLAS_VOICE=1`. The page then imports it once:

```js
export function init(api) {
  // api.on("delta", ({session, text}) => ...)   streamed text as Claude writes it
  // api.on("reply", ({session, text}) => ...)   a finished reply: speak it here
  // api.send(text)                              write to the shown session (e.g. from speech-to-text)
}
export function toggle() { /* optional: if present, a microphone button appears and calls this */ }
```

Without `hook.js`, or without `ATLAS_VOICE=1`, no voice code loads and no microphone button shows.

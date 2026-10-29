import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { CSS2DRenderer, CSS2DObject } from "three/addons/renderers/CSS2DRenderer.js";

const $ = (id) => document.getElementById(id);
const post = (path, body = {}) => fetch("/api/" + path, { method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body) }).then(async (r) => { if (!r.ok) throw new Error((await r.json()).error || r.statusText); });

let currentSession = null;
const S = { name: "Atlas", provider: "", vault: "", server: "idle", listening: false, hearing: false, speaking: false,
            working: false, live: null, voice: false };

// ------------------------------------------------------------------ status icon
const WORDS = { asking: "Waiting", speaking: "Speaking", hearing: "Hearing", listening: "Listening", working: "Working", error: "Trouble", idle: "Ready" };
let statusText = "", scribeText = "";
function renderStatus(text) {
  if (text !== undefined) statusText = text;
  const stage = S.speaking ? "speaking" : S.server === "error" ? "error" : S.server === "asking" ? "asking" : S.working ? "working"
    : S.hearing ? "hearing" : S.listening ? "listening" : "idle";
  document.body.dataset.state = stage;
  $("state-word").textContent = stage === "idle" && S.fresh ? "Awake" : WORDS[stage];
  $("state-hint").textContent = stage === "asking" ? "Allow or deny" : S.listening ? "Click to send" : S.voice && Recognition ? "Click to speak" : "Type a message";
  $("state-detail").textContent = stage === "working" || stage === "error" || stage === "asking" ? statusText : scribeText;
}

// ------------------------------------------------------------------ name
function setName(n) {
  S.name = n;
  $("name").textContent = n;
  document.title = n;
}
$("name").addEventListener("click", () => { $("name").contentEditable = "plaintext-only"; $("name").focus(); });
$("name").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); $("name").blur(); } });
$("name").addEventListener("blur", () => {
  $("name").contentEditable = "false";
  const n = $("name").textContent.trim() || "Atlas";
  setName(n);
  post("name", { name: n });
});

// ------------------------------------------------------------------ conversation
const log = $("log");
function render(md) {
  return DOMPurify.sanitize(marked.parse(md, { breaks: true }));
}
function addMsg(role, text) {
  const d = document.createElement("div");
  d.className = "msg " + role;
  if (role === "assistant") d.innerHTML = render(text); else d.textContent = text;
  log.appendChild(d);
  log.scrollTop = log.scrollHeight;
  return d;
}
function stickyScroll() {
  if (log.scrollHeight - log.scrollTop - log.clientHeight < 120) log.scrollTop = log.scrollHeight;
}
function setWorking(on) {
  S.working = on;
  $("send").disabled = on;
  $("stop").hidden = !on;
  $("send").hidden = on;
  renderStatus();
  renderSessions();
}
async function send(text) {
  text = text.trim();
  if (!text) return;
  $("input").value = "";
  autosize();
  try { await post("send", { text }); }
  catch (e) { addMsg("error", e.message); }
}
$("composer").addEventListener("submit", (e) => { e.preventDefault(); stopMic(false); send($("input").value); });
$("input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("composer").requestSubmit(); }
});
function autosize() { const i = $("input"); i.style.height = "auto"; i.style.height = Math.min(i.scrollHeight, 160) + "px"; }
$("input").addEventListener("input", autosize);
$("stop").addEventListener("click", () => post("stop"));
const fail = (e) => addMsg("error", e.message);
let sessionList = [];
function medallion(m) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = `med${m.working ? " working" : ""}${m.id === currentSession ? " on" : ""}${m.add ? " add" : ""}`;
  b.innerHTML = '<svg viewBox="0 0 48 48"><circle class="disc" cx="24" cy="24" r="20"/><circle class="arc" cx="24" cy="24" r="23"/><text class="glyph" x="24" y="25"></text></svg><div class="cap"></div>';
  b.querySelector(".glyph").textContent = m.add ? "+" : (m.title || "?").trim().charAt(0).toUpperCase();
  b.querySelector(".cap").textContent = m.add ? "New" : m.title;
  b.title = m.add ? "Start a new session" : m.title;
  return b;
}
function renderSessions(list, current) {
  if (list) sessionList = list;
  if (current) currentSession = current;
  const add = medallion({ add: true });
  add.addEventListener("click", () => post("new").catch(fail));
  $("sessions").replaceChildren(add, ...sessionList.map((m) => {
    const b = medallion({ ...m, working: S.working && m.id === currentSession });
    b.addEventListener("click", () => { if (m.id !== currentSession) post("session", { id: m.id }).catch(fail); });
    return b;
  }));
  window.edges();
}
{ // fade an edge only where medallions are scrolled out of view; the wheel scrolls sideways
  const strip = $("sessions");
  window.edges = () => {
    const max = strip.scrollWidth - strip.clientWidth;
    strip.classList.toggle("fade-l", strip.scrollLeft > 1);
    strip.classList.toggle("fade-r", strip.scrollLeft < max - 1);
  };
  strip.addEventListener("scroll", window.edges, { passive: true });
  strip.addEventListener("wheel", (e) => {
    if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) { strip.scrollLeft += e.deltaY; e.preventDefault(); }
  }, { passive: false });
  new ResizeObserver(window.edges).observe(strip);
}
function offerSetup() {
  // only on a first run: no setup recorded and no session that has ever had a message
  if (S.setupDone || log.children.length || sessionList.some((m) => m.n > 0)) return;
  const d = document.createElement("div");
  d.className = "msg assistant setup-offer";
  d.innerHTML = "<p><strong>Welcome.</strong> Want a short guided setup? It names your assistant, sets up your notes, and shows you what you can add.</p>";
  const b = document.createElement("button");
  b.textContent = "Start setup";
  b.addEventListener("click", () => { d.remove(); send("Set me up: read .claude/skills/atlas-setup/SKILL.md in the vault and follow it."); });
  d.appendChild(b);
  log.appendChild(d);
}
function showMessages(msgs) {
  log.innerHTML = "";
  current = null;
  for (const m of msgs) addMsg(m.role, m.text);
  offerSetup();
}

// ------------------------------------------------------------------ usage
function renderUsage(u) {
  $("usage-title").textContent = (u.provider === "codex" ? "Codex" : "Claude") + " usage";
  const body = $("usage-body");
  body.innerHTML = "";
  for (const w of u.windows || []) {
    const row = document.createElement("div");
    row.className = "bar-row";
    const reset = w.resets ? new Date(w.resets * 1000).toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" }) : "";
    row.innerHTML = `<div class="top"><span>${w.label}</span><span>${w.used}%</span></div>
      <div class="bar"><i class="${w.used >= 90 ? "full" : w.used >= 70 ? "hot" : ""}" style="width:${Math.min(w.used, 100)}%"></i></div>
      ${reset ? `<div class="muted">Resets ${reset}</div>` : ""}`;
    body.appendChild(row);
  }
  if (u.tokens) {
    const p = document.createElement("p");
    p.className = "muted";
    p.textContent = `Last turn: ${u.tokens.input.toLocaleString()} in, ${u.tokens.output.toLocaleString()} out`;
    body.appendChild(p);
  }
  if (!body.children.length) body.innerHTML = '<p class="muted">Shown after your first message.</p>';
}

// ------------------------------------------------------------------ voice (the browser's own speech, no servers)
const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let rec = null, micText = "";
function startMic() {
  if (!Recognition || rec) return;
  rec = new Recognition();
  rec.continuous = true;
  rec.interimResults = true;
  rec.lang = navigator.language || "en-GB";
  const base = $("input").value ? $("input").value + " " : "";
  micText = "";
  rec.onspeechstart = () => { S.hearing = true; renderStatus(); };
  rec.onspeechend = () => { S.hearing = false; renderStatus(); };
  rec.onresult = (e) => {
    micText = [...e.results].map((r) => r[0].transcript).join(" ").trim();
    $("input").value = base + micText;
    autosize();
  };
  rec.onerror = (e) => { if (e.error !== "no-speech") addMsg("error", "Microphone: " + e.error); stopMic(false); };
  rec.onend = () => { if (rec) stopMic(false); };
  rec.start();
  S.listening = true;
  speechSynthesis.cancel();
  renderStatus();
}
function stopMic(sendNow) {
  const r = rec;
  rec = null;
  if (r) { try { r.stop(); } catch {} }
  S.listening = S.hearing = false;
  renderStatus();
  if (sendNow && $("input").value.trim()) $("composer").requestSubmit();
}
function panelClick() {
  if (S.voice && Recognition) (rec ? stopMic(true) : startMic());
  else $("input").focus();
}
$("state-panel").addEventListener("click", panelClick);
$("state-panel").addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); panelClick(); } });
function speak(text) {
  if (!$("speak").checked || !text) return;
  const plain = text.replace(/```[\s\S]*?```/g, " ").replace(/[*_`#>|]/g, "").replace(/\[([^\]]+)\]\([^)]*\)/g, "$1");
  const u = new SpeechSynthesisUtterance(plain);
  u.onstart = () => { S.speaking = true; renderStatus(); };
  u.onend = u.onerror = () => { S.speaking = false; renderStatus(); };
  speechSynthesis.cancel();
  speechSynthesis.speak(u);
}
function enableVoice(on) {
  S.voice = on;
  $("voice-row").hidden = !(on && window.speechSynthesis);
  renderStatus();
}
$("speak").checked = localStorage.getItem("atlas-speak") === "1";
$("speak").addEventListener("change", () => { localStorage.setItem("atlas-speak", $("speak").checked ? "1" : "0"); if (!$("speak").checked) speechSynthesis.cancel(); });

// ------------------------------------------------------------------ globe
// Every colour on the globe comes from the theme's CSS variables (web/theme-default.css, or ~/.atlas-lite/theme/theme.css).
const cssVar = (name, fallback) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
const palette = () => Array.from({ length: 8 }, (_, i) => cssVar(`--node-${i + 1}`, "#7c9cff"));
const colorOf = (folder, map) => { if (!map.has(folder)) map.set(folder, map.size); return palette()[map.get(folder) % 8]; };

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(50, innerWidth / innerHeight, 0.1, 100);
camera.position.set(0, 0, 4.6);
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
$("globe").appendChild(renderer.domElement);
const labels = new CSS2DRenderer();
labels.setSize(innerWidth, innerHeight);
Object.assign(labels.domElement.style, { position: "absolute", top: 0, left: 0, pointerEvents: "none" });
$("globe").appendChild(labels.domElement);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.enablePan = false;
controls.minDistance = 2.2;
controls.maxDistance = 8;
controls.autoRotate = true;
controls.autoRotateSpeed = 0.4;
const globe = new THREE.Group();
scene.add(globe);
// shift the sphere right of the chat panel so it is not hidden behind it
function framing() {
  // centre the sphere between the two side columns, as in the layout of the panels
  const w = innerWidth, left = Math.min(w * 0.3, 520), right = Math.min(w * 0.22, 360);
  camera.setViewOffset(w, innerHeight, w > 800 ? -(left - right) / 2 : 0, 0, w, innerHeight);
}

function dotTexture() {
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const g = c.getContext("2d");
  const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grad.addColorStop(0, "#fff"); grad.addColorStop(0.45, "#fff"); grad.addColorStop(0.5, "rgba(255,255,255,.35)");
  grad.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = grad; g.fillRect(0, 0, 64, 64);
  return new THREE.CanvasTexture(c);
}
const sprite = dotTexture();

// Place nodes on a sphere: random start, then repel all pairs and pull linked pairs together, staying on the surface.
function layout(nodes, links) {
  const n = nodes.length, pos = nodes.map((_, i) => {
    const y = 1 - (2 * (i + 0.5)) / n, r = Math.sqrt(1 - y * y), a = i * 2.399963;
    return new THREE.Vector3(Math.cos(a) * r, y, Math.sin(a) * r);
  });
  const idx = new Map(nodes.map((nd, i) => [nd.id, i]));
  const pairs = links.map((l) => [idx.get(l.source), idx.get(l.target)]).filter((p) => p[0] !== undefined && p[1] !== undefined);
  const deg = new Array(n).fill(0);
  for (const [a, b] of pairs) { deg[a]++; deg[b]++; }
  const iters = n > 600 ? 40 : 150, k = Math.sqrt(4 / Math.max(n, 1));
  for (let it = 0; it < iters; it++) {
    const f = pos.map(() => new THREE.Vector3());
    if (n <= 900) for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
      const d = pos[i].clone().sub(pos[j]), l2 = Math.max(d.lengthSq(), 1e-4);
      d.multiplyScalar((k * k) / l2 * 0.8);
      f[i].add(d); f[j].sub(d);
    }
    for (const [a, b] of pairs) {
      const d = pos[b].clone().sub(pos[a]), l = d.length();
      d.multiplyScalar(l / k * 0.25 / Math.sqrt(Math.max(deg[a], deg[b])));
      f[a].add(d); f[b].sub(d);
    }
    const step = 0.06 * (1 - it / iters) + 0.004;
    for (let i = 0; i < n; i++) pos[i].add(f[i].clampLength(0, 1).multiplyScalar(step)).normalize();
  }
  return pos;
}

let cloud, lines, nodesNow = [], posNow = [], indexOf = new Map(), baseColors = [];
const heat = new Map();            // node id -> time it was last touched
const labelObjs = new Map();
const colorMap = new Map();

// The sphere itself: a faint body, a few latitude and longitude lines and a soft rim of light, restyled by applyTheme().
const shell = new THREE.Group();
globe.add(shell);
const body = new THREE.Mesh(new THREE.SphereGeometry(0.985, 64, 48), new THREE.MeshBasicMaterial({ transparent: true, depthWrite: false }));
const rim = new THREE.Mesh(new THREE.SphereGeometry(1.14, 64, 48), new THREE.ShaderMaterial({
  transparent: true, side: THREE.BackSide, depthWrite: false, blending: THREE.AdditiveBlending,
  uniforms: { color: { value: new THREE.Color("#7c9cff") } },
  vertexShader: "varying vec3 n; void main() { n = normalize(normalMatrix * normal); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
  fragmentShader: "uniform vec3 color; varying vec3 n; void main() { float k = pow(max(0.0, 0.8 + n.z), 6.0); gl_FragColor = vec4(color, 1.0) * k * 1.4; }" }));
const graticuleLines = (() => {
  const pts = [], seg = 96, ring = (f) => { for (let i = 0; i < seg; i++) { const a = f(i / seg * Math.PI * 2), b = f((i + 1) / seg * Math.PI * 2); pts.push(...a, ...b); } };
  for (const lat of [-60, -30, 0, 30, 60]) { const y = Math.sin(lat * Math.PI / 180), r = Math.cos(lat * Math.PI / 180) * 0.985; ring((t) => [Math.cos(t) * r, y * 0.985, Math.sin(t) * r]); }
  for (let k = 0; k < 6; k++) { const ph = k * Math.PI / 6; ring((t) => [Math.cos(t) * Math.cos(ph) * 0.985, Math.sin(t) * 0.985, Math.cos(t) * Math.sin(ph) * 0.985]); }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
  return new THREE.LineSegments(g, new THREE.LineBasicMaterial({ transparent: true, opacity: 0.07, depthWrite: false }));
})();
shell.add(body, rim, graticuleLines);

let lastGraph = null, layoutOverride = null, onSphere = true;

// The hook for custom rendering. ~/.atlas-lite/theme/custom.js is an ES module whose default export is called once with this
// object. It survives updates, unlike edits to this file. See skills/atlas-theme/SKILL.md for what each part is.
const buildHooks = [], frameHooks = [], noteHooks = [];
const atlas = {
  THREE, scene, camera, renderer, controls, globe, shell, css: cssVar,
  parts: { get cloud() { return cloud; }, get lines() { return lines; }, body, rim, graticule: graticuleLines },
  get nodes() { return nodesNow; }, get positions() { return posNow; }, get colors() { return baseColors; },
  get links() { return lastGraph ? lastGraph.links : []; },
  onBuild: (fn) => { buildHooks.push(fn); if (lastGraph) fn(atlas); },   // after every (re)build of the points and arcs
  onFrame: (fn) => frameHooks.push(fn),                                  // every animation frame, with the time in ms
  touch: (id) => touch(id), heat,
  // how strongly a note is glowing from a touch right now, 1 at the touch fading to 0 over about 6 s: drive your own effects with it
  glow: (id, t = performance.now()) => { const at = heat.get(id); return at === undefined ? 0 : Math.max(0, 1 - (t - at) / HOT_MS); },
  pickThreshold: 0.05,                      // how close the pointer must be to a note's position (scene units) to hover it
  // the notes as a tree: breadth-first from Index (or the most linked note). {root, parent[], depth[], children[][]}, by node index
  hierarchy: () => {
    const n = nodesNow.length, idx = new Map(nodesNow.map((x, i) => [x.id, i])), adj = Array.from({ length: n }, () => []);
    for (const l of (lastGraph ? lastGraph.links : [])) { const a = idx.get(l.source), b = idx.get(l.target); if (a !== undefined && b !== undefined) { adj[a].push(b); adj[b].push(a); } }
    let root = nodesNow.findIndex((x) => x.name === "Index");
    if (root < 0) root = adj.reduce((best, a, i) => (a.length > adj[best].length ? i : best), 0);
    const parent = new Array(n).fill(-1), depth = new Array(n).fill(-1), children = Array.from({ length: n }, () => []), queue = [root];
    depth[root] = 0;
    for (let q = 0; q < queue.length; q++) for (const j of adj[queue[q]]) if (depth[j] < 0) { depth[j] = depth[queue[q]] + 1; parent[j] = queue[q]; children[queue[q]].push(j); queue.push(j); }
    for (let i = 0; i < n; i++) if (depth[i] < 0) { depth[i] = 1; parent[i] = root; children[root].push(i); }   // notes with no links hang off the root
    return { root, parent, depth, children };
  },
  // replace where the notes sit: fn(nodes, links, THREE) returns one THREE.Vector3 per node. Any shape works, not only a sphere.
  setLayout: (fn) => { layoutOverride = fn; if (lastGraph) { lastGraph.positions = null; buildGlobe(lastGraph); } },
  rebuild: () => { if (lastGraph) buildGlobe(lastGraph); },
  // dashboard features: a card in the right column, a note's text, a change feed, and a way to message the assistant
  card: (id, title) => {
    let sec = document.getElementById("card-" + id);
    if (!sec) {
      sec = document.createElement("section");
      sec.id = "card-" + id;
      sec.className = "card side-card";
      sec.innerHTML = "<h2></h2><div class='card-body'></div>";
      $("side").appendChild(sec);
    }
    sec.querySelector("h2").textContent = title;
    return sec.querySelector(".card-body");
  },
  note: async (id) => { const r = await fetch("/api/note?id=" + encodeURIComponent(id)); return r.ok ? r.json() : null; },
  onNotes: (fn) => noteHooks.push(fn),      // called with the graph whenever any note in the vault changes
  send: (text) => send(text),
  post,
};
window.atlas = atlas;
const runBuild = () => buildHooks.forEach((fn) => { try { fn(atlas); } catch (e) { console.error("custom.js onBuild", e); } });

function applyTheme() {
  body.material.color.set(cssVar("--globe-shell", "#9db4ff"));
  body.material.opacity = 0.05;
  graticuleLines.material.color.set(cssVar("--globe-shell", "#9db4ff"));
  rim.material.uniforms.color.value.set(cssVar("--globe-rim", "#7c9cff"));
  glowColor.set(cssVar("--glow", "#ffffff"));
  if (lastGraph) buildGlobe(lastGraph);
}
const glowColor = new THREE.Color("#ffffff");

// A link is an arc over the surface, lifted a little in the middle, rather than a chord through the sphere.
function arc(a, b, out) {
  if (Math.abs(a.length() - 1) > 0.02 || Math.abs(b.length() - 1) > 0.02) { out.push(a.x, a.y, a.z, b.x, b.y, b.z); return; }   // a custom layout off the sphere: straight links
  const ang = a.angleTo(b), n = Math.max(4, Math.min(14, Math.ceil(ang * 6))), lift = 0.12 * Math.min(ang, 1.6) / 1.6;
  let prev = a.clone();
  for (let i = 1; i <= n; i++) {
    const t = i / n, p = a.clone().lerp(b, t).normalize().multiplyScalar(1 + Math.sin(t * Math.PI) * lift);
    out.push(prev.x, prev.y, prev.z, p.x, p.y, p.z);
    prev = p;
  }
}

function buildGlobe(graph) {
  lastGraph = graph;
  for (const o of [cloud, lines]) if (o) { globe.remove(o); o.geometry.dispose(); o.material.dispose(); }
  for (const o of labelObjs.values()) globe.remove(o);
  labelObjs.clear();
  colorMap.clear();
  nodesNow = graph.nodes;
  indexOf = new Map(nodesNow.map((n, i) => [n.id, i]));
  if (!graph.positions || graph.positions.length !== nodesNow.length) {
    graph.positions = layoutOverride ? layoutOverride(nodesNow, graph.links, THREE) : layout(nodesNow, graph.links);
  }
  posNow = graph.positions;
  onSphere = posNow.every((p) => Math.abs(p.length() - 1) < 0.02);
  baseColors = nodesNow.map((n) => new THREE.Color(colorOf(n.folder, colorMap)));
  const pg = new THREE.BufferGeometry();
  pg.setAttribute("position", new THREE.Float32BufferAttribute(posNow.flatMap((p) => [p.x, p.y, p.z]), 3));
  pg.setAttribute("color", new THREE.Float32BufferAttribute(baseColors.flatMap((c) => [c.r, c.g, c.b]), 3));
  cloud = new THREE.Points(pg, new THREE.PointsMaterial({ size: 0.13, map: sprite, vertexColors: true, transparent: true,
    alphaTest: 0.05, depthWrite: false, sizeAttenuation: true }));
  globe.add(cloud);
  const lp = [];
  for (const l of graph.links) {
    const a = posNow[indexOf.get(l.source)], b = posNow[indexOf.get(l.target)];
    if (a && b) arc(a, b, lp);
  }
  const lg = new THREE.BufferGeometry();
  lg.setAttribute("position", new THREE.Float32BufferAttribute(lp, 3));
  lines = new THREE.LineSegments(lg, new THREE.LineBasicMaterial({ color: cssVar("--link", "#9db4ff"), transparent: true,
    opacity: parseFloat(cssVar("--link-opacity", "0.34")), depthWrite: false }));
  globe.add(lines);
  if (nodesNow.length <= 60) nodesNow.forEach((_, i) => labelFor(i));
  for (const [id, at] of pendingTouches) { pendingTouches.delete(id); if (performance.now() - at < 20000) touch(id); }
  runBuild();
}

function labelFor(i) {
  const id = nodesNow[i].id;
  if (!labelObjs.has(id)) {
    const el = document.createElement("div");
    el.className = "label";
    el.textContent = nodesNow[i].name;
    const o = new CSS2DObject(el);
    o.position.copy(posNow[i]).multiplyScalar(1.04);
    globe.add(o);
    labelObjs.set(id, o);
  }
  return labelObjs.get(id);
}
const pendingTouches = new Map();     // a note the assistant just created: flash it once it appears in the graph
function touch(id) {
  if (!indexOf.has(id)) { pendingTouches.set(id, performance.now()); return; }
  if (indexOf.has(id)) { heat.set(id, performance.now()); labelFor(indexOf.get(id)).element.classList.add("hot"); }
}
const HOT_MS = 6000;
let hover = -1;
function frame(t) {
  controls.update();
  if (cloud) {
    const col = cloud.geometry.attributes.color;
    let dirty = false;
    for (const [id, at] of heat) {
      const i = indexOf.get(id), k = 1 - (t - at) / HOT_MS;
      if (i === undefined) { heat.delete(id); continue; }
      const c = baseColors[i];
      if (k <= 0) {
        col.setXYZ(i, c.r, c.g, c.b); heat.delete(id);
        const lo = labelObjs.get(id);
        if (lo) lo.element.classList.remove("hot");
      } else { const m = k * (0.6 + 0.4 * Math.sin(t / 120)); col.setXYZ(i, c.r + (glowColor.r - c.r) * m, c.g + (glowColor.g - c.g) * m, c.b + (glowColor.b - c.b) * m); }
      dirty = true;
    }
    if (dirty) col.needsUpdate = true;
  }
  for (const fn of frameHooks) { try { fn(t, atlas); } catch (e) { console.error("custom.js onFrame", e); frameHooks.splice(frameHooks.indexOf(fn), 1); } }
  renderer.render(scene, camera);
  labels.render(scene, camera);
  requestAnimationFrame(frame);
}

const ray = new THREE.Raycaster();
const mouse = new THREE.Vector2();
function pick(ev) {
  if (!cloud) return -1;
  mouse.set((ev.clientX / innerWidth) * 2 - 1, -(ev.clientY / innerHeight) * 2 + 1);
  ray.setFromCamera(mouse, camera);
  ray.params.Points.threshold = atlas.pickThreshold;
  let hits = ray.intersectObject(cloud);          // works while cloud is hidden, so a custom look can draw its own nodes
  if (onSphere) hits = hits.filter((h) => h.point.distanceTo(camera.position) < camera.position.distanceTo(controls.target) + 0.15);   // near side only
  return hits.length ? hits[0].index : -1;
}
renderer.domElement.addEventListener("pointermove", (ev) => {
  const i = pick(ev);
  if (i === hover) { if (i >= 0) place(ev); return; }
  if (hover >= 0) labelObjs.get(nodesNow[hover]?.id)?.element.classList.remove("hover");
  hover = i;
  renderer.domElement.style.cursor = i >= 0 ? "pointer" : "grab";
  if (i < 0) { $("tip").hidden = true; controls.autoRotate = true; return; }
  controls.autoRotate = false;
  const n = nodesNow[i];
  labelFor(i).element.classList.add("hover");
  $("tip").innerHTML = "";
  $("tip").append(n.name);
  if (n.blurb) { const s = document.createElement("small"); s.textContent = n.blurb; $("tip").append(s); }
  $("tip").hidden = false;
  place(ev);
});
renderer.domElement.addEventListener("pointerleave", () => {
  if (hover >= 0 && nodesNow[hover]) labelObjs.get(nodesNow[hover].id)?.element.classList.remove("hover");
  hover = -1;
  $("tip").hidden = true;
  controls.autoRotate = $("preview").hidden;
});
function place(ev) { $("tip").style.left = ev.clientX + 14 + "px"; $("tip").style.top = ev.clientY + 14 + "px"; }
let downAt = null;
renderer.domElement.addEventListener("pointerdown", (ev) => { downAt = [ev.clientX, ev.clientY]; });
renderer.domElement.addEventListener("click", (ev) => {
  if (downAt && Math.hypot(ev.clientX - downAt[0], ev.clientY - downAt[1]) > 5) return;   // that was a drag, not a click
  const i = pick(ev);
  if (i >= 0) openNote(nodesNow[i].id);
});
addEventListener("resize", () => {
  camera.aspect = innerWidth / innerHeight;
  framing();
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
  labels.setSize(innerWidth, innerHeight);
});

// ------------------------------------------------------------------ live events
let current = null;   // the assistant bubble being streamed
function onEvent(e) {
  switch (e.t) {
    case "status":
      S.server = e.stage;
      setWorking(e.stage === "working" || e.stage === "asking");
      renderStatus(e.text);
      break;
    case "user": S.fresh = false; if (!log.lastElementChild || log.lastElementChild.textContent !== e.text) addMsg("user", e.text); current = null; break;
    case "delta":
      if (!current) { current = addMsg("assistant", ""); current.dataset.raw = ""; }
      current.dataset.raw += e.text;
      current.innerHTML = render(current.dataset.raw);
      stickyScroll();
      break;
    case "turn_end":
      if (e.error) addMsg("error", e.error);
      else if (current) speak(current.dataset.raw);
      current = null;
      break;
    case "session": currentSession = e.current; renderSessions(e.sessions, e.current); showMessages(e.messages); break;
    case "sessions": renderSessions(e.sessions, currentSession); break;
    case "usage": renderUsage(e.usage); break;
    case "notice": { const d = document.createElement("div"); d.className = "notice"; d.textContent = e.text; log.appendChild(d); stickyScroll(); break; }
    case "scribe": scribeText = e.text; renderStatus(); break;
    case "model": renderModel(e.model, e.effort); break;
    case "mode": renderMode(e.mode); break;
    case "permission": addAsk(e); break;
    case "permission_done": removeAsk(e.id); break;
    case "graph": buildGlobe(e.graph); noteHooks.forEach((fn) => { try { fn(e.graph); } catch (x) { console.error("custom.js onNotes", x); } }); break;
    case "touch": touch(e.note); break;
    case "name": setName(e.name); break;
    case "theme": {
      if (e.custom !== S.custom) { location.reload(); break; }
      const link = $("theme");
      link.onload = applyTheme;
      link.href = "/theme.css?v=" + e.v;
      break;
    }
  }
}

async function boot() {
  const s = await (await fetch("/api/state")).json();
  Object.assign(S, { provider: s.provider, vault: s.vault });
  setName(s.name);
  enableVoice(s.voice);
  S.setupDone = s.setup_done;
  modelChoices = s.choices.models;
  renderModel(s.model, s.effort);
  modeChoices = s.modes; renderMode(s.mode);
  S.fresh = s.fresh;
  currentSession = s.current;
  renderSessions(s.sessions, s.current);
  for (const m of s.messages) addMsg(m.role, m.text);
  offerSetup();
  if (s.reply) { current = addMsg("assistant", s.reply); current.dataset.raw = s.reply; }
  S.server = s.status.stage;
  setWorking(s.status.stage === "working" || s.status.stage === "asking");
  renderStatus(s.status.text);
  (s.permissions || []).forEach(addAsk);
  renderUsage(s.usage);
  framing();
  camera.updateProjectionMatrix();
  applyTheme();
  buildGlobe(s.graph);
  requestAnimationFrame(frame);
  S.custom = s.custom;
  if (s.custom) import("/theme/custom.js?v=" + s.custom).then((m) => m.default && m.default(atlas)).catch((e) => console.error("custom.js", e));
  const deepLink = new URLSearchParams(location.search).get("note");
  if (deepLink) openNote(deepLink);
  const es = new EventSource("/api/events");
  es.onmessage = (m) => onEvent(JSON.parse(m.data));
}
boot().catch((e) => { $("state-detail").textContent = String(e.stack || e).slice(0, 400); console.error(e); });


// ------------------------------------------------------------------ the centre preview: a note laid over the globe
let previewNote = null;
async function openNote(id) {
  let n;
  try { n = await (await fetch("/api/note?id=" + encodeURIComponent(id))).json(); } catch { return; }
  if (n.error) return;
  previewNote = n;
  $("preview-title").textContent = n.name;
  $("preview-path").textContent = n.path;
  const html = marked.parse(n.text.replace(/\[\[([^\]|#^]+)(?:[#^][^\]|]*)?(?:\|([^\]]*))?\]\]/g,
    (_, target, alias) => `<a data-note="${encodeURIComponent(target.trim())}">${alias || target}</a>`), { breaks: true });
  $("preview-body").innerHTML = DOMPurify.sanitize(html, { ADD_ATTR: ["data-note"] });
  $("preview").hidden = false;
  $("preview-body").scrollTop = 0;
  controls.autoRotate = false;
}
function closePreview() { $("preview").hidden = true; previewNote = null; controls.autoRotate = true; }
$("preview-close").addEventListener("click", closePreview);
$("preview-body").addEventListener("click", (e) => {
  const a = e.target.closest("a[data-note]");
  if (!a) return;
  const name = decodeURIComponent(a.dataset.note).split("/").pop().toLowerCase();
  const node = nodesNow.find((n) => n.name.toLowerCase() === name);
  if (node) openNote(node.id);
});
addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("preview").hidden) closePreview(); });


// ------------------------------------------------------------------ the permission screen
const asks = [];
const TOOL_ASK = { Bash: "Run a command", Edit: "Edit a file", Write: "Write a file", Read: "Read a file", NotebookEdit: "Edit a notebook",
  WebFetch: "Open a web page", WebSearch: "Search the web", Glob: "List files", Grep: "Search files" };
function addAsk(p) { if (!asks.some((a) => a.id === p.id)) asks.push(p); showAsk(); }
function removeAsk(id) { const i = asks.findIndex((a) => a.id === id); if (i >= 0) asks.splice(i, 1); showAsk(); }
function showAsk() {
  const a = asks[0];
  $("ask").hidden = !a;
  if (!a) return;
  $("ask-title").textContent = (TOOL_ASK[a.tool] || `Use ${a.tool}`) + "?";
  $("ask-why").textContent = a.description || `${S.provider === "codex" ? "Codex" : "Claude"} is asking before it goes ahead.`;
  $("ask-detail").textContent = a.detail || "(no details)";
  $("ask-always").textContent = { Bash: "Allow all commands this session", Edit: "Allow all edits this session", Write: "Allow all writes this session" }[a.tool]
    || `Allow ${a.tool} this session`;
  $("ask-more").textContent = asks.length > 1 ? `${asks.length - 1} more waiting` : "";
  $("ask-allow").focus();
}
function answer(allow, always) {
  const a = asks[0];
  if (!a) return;
  post("answer", { id: a.id, allow, always }).catch((e) => addMsg("error", e.message));
  removeAsk(a.id);
}
$("ask-allow").addEventListener("click", () => answer(true, false));
$("ask-always").addEventListener("click", () => answer(true, true));
$("ask-deny").addEventListener("click", () => answer(false, false));


// ------------------------------------------------------------------ model and effort
let modelChoices = [];
function renderModel(model, effort) {
  const mp = $("model-pick"), ep = $("effort-pick");
  mp.replaceChildren(...modelChoices.map((m) => Object.assign(document.createElement("option"), { value: m.id, textContent: m.label })));
  mp.value = model || "";
  const efforts = (modelChoices.find((m) => m.id === (model || "")) || modelChoices[0] || { efforts: [] }).efforts;
  ep.replaceChildren(Object.assign(document.createElement("option"), { value: "", textContent: "Default effort" }),
    ...efforts.map((e) => Object.assign(document.createElement("option"), { value: e, textContent: e })));
  ep.value = efforts.includes(effort) ? effort : "";
}
let modeChoices = [];
function renderMode(mode) {
  const sel = $("mode-pick");
  sel.replaceChildren(...modeChoices.map((m) => Object.assign(document.createElement("option"), { value: m.id, textContent: m.label })));
  sel.value = mode;
}
$("mode-pick").addEventListener("change", () => post("mode", { mode: $("mode-pick").value }).catch((e) => addMsg("error", e.message)));
function saveModel() {
  post("model", { model: $("model-pick").value, effort: $("effort-pick").value }).catch((e) => addMsg("error", e.message));
}
$("model-pick").addEventListener("change", () => { $("effort-pick").value = ""; renderModel($("model-pick").value, ""); saveModel(); });
$("effort-pick").addEventListener("change", saveModel);

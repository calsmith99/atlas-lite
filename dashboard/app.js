// Work Atlas dashboard: the work vault as a celestial globe, plus the live conversation of every Claude
// session on this machine, fed by one WebSocket from dashboard.py. Any session that reads or edits a note lights it.
import { WorkControls, post } from "./controls.js";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { CSS2DRenderer, CSS2DObject } from "three/addons/renderers/CSS2DRenderer.js";

const R = 100;                       // globe radius
const TILT = THREE.MathUtils.degToRad(23.44);
const SPIN = 0.035;                  // rad/s, about three minutes a turn
const HEAT_FADE = 14;                // seconds for a touched note to cool
const EMBER = 0.18;                  // notes touched this session keep this glow
const TINT_FADE = 300;               // seconds for a touched note to fade from blue back to its own colour
const FOLDER_COLOURS = {
  Tickets: "#8fc0aa", Reference: "#f3dc9a", Research: "#f4ecd8", Logs: "#e0995a", Extras: "#a89274", "": "#ffe7a8",
};
const FALLBACK_COLOURS = ["#8fc0aa", "#f3dc9a", "#e0995a", "#9db4e8", "#d99ac5", "#b5d98a", "#e8b49d", "#9ad9d4"];
const folderColour = (f) => FOLDER_COLOURS[f] ?? (f ? FALLBACK_COLOURS[hash(f) % FALLBACK_COLOURS.length] : FOLDER_COLOURS[""]);
const TOUCH_COLOUR = new THREE.Color("#4f9dff");  // read or edited by Atlas

const $ = (s) => document.querySelector(s);
const clamp = (x, a, b) => Math.min(b, Math.max(a, x));

// ---------------------------------------------------------------- scene
const host = $("#globe");
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
host.appendChild(renderer.domElement);
const labels = new CSS2DRenderer();
labels.domElement.style.cssText = "position:absolute;inset:0;pointer-events:none";
host.appendChild(labels.domElement);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(38, 1, 1, 5000);
camera.position.set(0, 40, 540);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.enablePan = false;
controls.minDistance = 180;
controls.maxDistance = 900;
controls.autoRotate = true;
controls.autoRotateSpeed = 0.12;     // the camera drifts slowly as well as the globe turning

scene.add(new THREE.AmbientLight(0x6b4a2a, 1.2));
const key = new THREE.PointLight(0xffd9a0, 2.2, 0, 0);
key.position.set(-260, 220, 300);
scene.add(key);
const rim = new THREE.PointLight(0xc2602e, 1.4, 0, 0);
rim.position.set(300, -120, -200);
scene.add(rim);

const globe = new THREE.Group();     // tilted like the earth's axis
globe.rotation.z = TILT;
scene.add(globe);
const sky = new THREE.Group();       // turns about the axis: stars, links, graticule
globe.add(sky);

// shared shader bits: fade what's on the far side of the globe
const facingGLSL = `
  vec3 n = normalize(normalMatrix * normalize(position));
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  float facing = dot(n, normalize(-mv.xyz));
  vFront = smoothstep(-0.35, 0.35, facing);`;

function lineMaterial(opacity) {
  return new THREE.ShaderMaterial({
    uniforms: { uOpacity: { value: opacity }, uDim: { value: 1 } },
    vertexShader: `attribute vec3 color; varying vec3 vColor; varying float vFront;
      void main() { ${facingGLSL} vColor = color; gl_Position = projectionMatrix * mv; }`,
    fragmentShader: `uniform float uOpacity; uniform float uDim; varying vec3 vColor; varying float vFront;
      void main() { gl_FragColor = vec4(vColor * uDim, uOpacity * mix(0.18, 1.0, vFront)); }`,
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  });
}

function circle(radius, segments, transform) {
  const pts = [];
  for (let i = 0; i <= segments; i++) {
    const a = (i / segments) * Math.PI * 2;
    const v = new THREE.Vector3(Math.cos(a) * radius, 0, Math.sin(a) * radius);
    pts.push(transform ? transform(v) : v);
  }
  return pts;
}

function segmentsGeometry(polylines, colour) {
  const pos = [], col = [];
  const c = new THREE.Color(colour);
  for (const line of polylines) {
    for (let i = 0; i < line.length - 1; i++) {
      pos.push(line[i].x, line[i].y, line[i].z, line[i + 1].x, line[i + 1].y, line[i + 1].z);
      col.push(c.r, c.g, c.b, c.r, c.g, c.b);
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
  return g;
}

// ---------------------------------------------------------------- the celestial sphere's engraving
const lineMats = [];
function engraving() {
  const faint = [], bold = [];
  const r = R * 1.002;
  for (let lat = -75; lat <= 75; lat += 15) {           // parallels
    const phi = THREE.MathUtils.degToRad(lat);
    (lat === 0 ? bold : faint).push(circle(r * Math.cos(phi), 128, (v) => v.setY(r * Math.sin(phi))));
  }
  for (let lon = 0; lon < 180; lon += 15) {             // meridians
    const m = new THREE.Matrix4().makeRotationY(THREE.MathUtils.degToRad(lon)).multiply(new THREE.Matrix4().makeRotationX(Math.PI / 2));
    faint.push(circle(r, 128, (v) => v.applyMatrix4(m)));
  }
  const ecl = new THREE.Matrix4().makeRotationZ(-TILT);  // the ecliptic and the zodiac band either side
  bold.push(circle(r, 180, (v) => v.applyMatrix4(ecl)));
  for (const off of [-8, 8]) {
    const phi = THREE.MathUtils.degToRad(off);
    faint.push(circle(r * Math.cos(phi), 180, (v) => v.setY(r * Math.sin(phi)).applyMatrix4(ecl)));
  }
  const ticks = [];                                     // degree ticks along the ecliptic, every 10°
  for (let d = 0; d < 360; d += 10) {
    const a = THREE.MathUtils.degToRad(d);
    const len = d % 30 === 0 ? 7 : 3.5;
    const p = (s) => new THREE.Vector3(Math.cos(a) * r, s, Math.sin(a) * r).applyMatrix4(ecl);
    ticks.push([p(-len), p(len)]);
  }
  const mFaint = lineMaterial(0.05), mBold = lineMaterial(0.14);
  lineMats.push(mFaint, mBold);
  sky.add(new THREE.LineSegments(segmentsGeometry(faint, "#c9a45c"), mFaint));
  sky.add(new THREE.LineSegments(segmentsGeometry([...bold, ...ticks], "#e2bd6e"), mBold));
}
engraving();

// ---------------------------------------------------------------- brass armillary rings (outside the sky, don't spin with it)
const brass = new THREE.MeshPhongMaterial({ color: 0x8a6428, specular: 0xffe0a0, shininess: 70, emissive: 0x2a1906 });
const armillary = new THREE.Group();
globe.add(armillary);
function ring(radius, tube, rot) {
  const m = new THREE.Mesh(new THREE.TorusGeometry(radius, tube, 12, 220), brass);
  m.rotation.set(...rot);
  armillary.add(m);
  return m;
}
const meridianRing = ring(R * 1.16, 1.1, [0, 0, 0]);             // fixed meridian, holds the axis
const horizonRing = ring(R * 1.24, 0.9, [Math.PI / 2, 0, -TILT]); // horizon, level with the world
const colureRing = ring(R * 1.1, 0.6, [0, Math.PI / 2, 0]);
{
  const ticks = [];                                               // graduations on the meridian ring
  for (let d = 0; d < 360; d += 5) {
    const a = THREE.MathUtils.degToRad(d), r0 = R * 1.16 + 1.4, r1 = r0 + (d % 30 === 0 ? 6 : d % 10 === 0 ? 3.5 : 2);
    ticks.push([new THREE.Vector3(Math.cos(a) * r0, Math.sin(a) * r0, 0), new THREE.Vector3(Math.cos(a) * r1, Math.sin(a) * r1, 0)]);
  }
  const m = lineMaterial(0.55);
  lineMats.push(m);
  meridianRing.add(new THREE.LineSegments(segmentsGeometry(ticks, "#e2bd6e"), m));
  const axis = new THREE.Mesh(new THREE.CylinderGeometry(0.9, 0.9, R * 2.5, 12), brass);
  armillary.add(axis);
  for (const s of [-1, 1]) {
    const knob = new THREE.Mesh(new THREE.SphereGeometry(3.2, 20, 14), brass);
    knob.position.y = s * R * 1.25;
    armillary.add(knob);
  }
}

// ---------------------------------------------------------------- halo behind the globe (breathes with speech)
function haloTexture() {
  const c = document.createElement("canvas");
  c.width = c.height = 256;
  const g = c.getContext("2d");
  const grad = g.createRadialGradient(128, 128, 30, 128, 128, 128);
  grad.addColorStop(0, "rgba(255,210,140,0.55)");
  grad.addColorStop(0.45, "rgba(200,120,50,0.18)");
  grad.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 256, 256);
  return new THREE.CanvasTexture(c);
}
const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: haloTexture(), blending: THREE.AdditiveBlending, depthWrite: false, transparent: true }));
halo.scale.setScalar(R * 3.4);
halo.renderOrder = -1;
scene.add(halo);

// distant field stars
{
  const n = 1400, pos = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    const v = new THREE.Vector3().randomDirection().multiplyScalar(1400 + Math.random() * 1600);
    pos.set([v.x, v.y, v.z], i * 3);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  scene.add(new THREE.Points(g, new THREE.PointsMaterial({ color: 0xcfb58a, size: 2, sizeAttenuation: false, transparent: true, opacity: 0.45 })));
}

// ---------------------------------------------------------------- the vault: notes as stars on the sphere
let nodes = [], index = new Map(), stars, links, linkPairs = [], labelObjs = new Map();
let heat, heatKind, ember, tint;

function hash(s) { let h = 2166136261; for (const ch of s) h = Math.imul(h ^ ch.charCodeAt(0), 16777619); return h >>> 0; }
function rng(seed) { return () => { seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }

// Groups of notes that link mostly to each other (the homelab, the kitchen, Atlas), found by Louvain modularity:
// a note joins whichever group its links gain the most from, then groups merge as whole nodes. A link counts less
// the busier its ends are, so Index and the machine notes don't swallow everything. Fixed order, so it's stable.
function communities(n, L, deg) {
  let E = L.map(([a, b]) => [a, b, 1 / Math.sqrt(deg[a] * deg[b])]);
  let members = [...Array(n).keys()].map((i) => [i]), N = n;
  for (let level = 0; level < 6; level++) {
    const adj = Array.from({ length: N }, () => new Map()), k = new Float64Array(N);
    let m2 = 0;
    for (const [a, b, w] of E) {
      adj[a].set(b, (adj[a].get(b) || 0) + w); adj[b].set(a, (adj[b].get(a) || 0) + w);
      k[a] += w; k[b] += w; m2 += 2 * w;
    }
    if (!m2) break;
    const c = [...Array(N).keys()], tot = Float64Array.from(k);
    let improved = false;
    for (let pass = 0; pass < 20; pass++) {
      let moved = false;
      for (let i = 0; i < N; i++) {
        const links = new Map();
        for (const [j, w] of adj[i]) if (j !== i) links.set(c[j], (links.get(c[j]) || 0) + w);
        const own = c[i];
        tot[own] -= k[i];
        let best = own, gain = (links.get(own) || 0) - tot[own] * k[i] / m2;
        for (const [cc, w] of links) { const g = w - tot[cc] * k[i] / m2; if (g > gain + 1e-12) { gain = g; best = cc; } }
        tot[best] += k[i];
        if (best !== own) { c[i] = best; moved = improved = true; }
      }
      if (!moved) break;
    }
    if (!improved) break;
    const ids = new Map();
    c.forEach((x) => { if (!ids.has(x)) ids.set(x, ids.size); });
    const next = Array.from({ length: ids.size }, () => []);
    members.forEach((m, i) => next[ids.get(c[i])].push(...m));
    const agg = new Map();
    for (const [a, b, w] of E) {
      const x = ids.get(c[a]), y = ids.get(c[b]), key = Math.min(x, y) + "," + Math.max(x, y);
      agg.set(key, (agg.get(key) || 0) + w);
    }
    E = [...agg].map(([key, w]) => [...key.split(",").map(Number), w]);
    members = next; N = ids.size;
  }
  const label = new Array(n);
  members.forEach((m, g) => m.forEach((i) => (label[i] = g)));
  return label;
}

// Force layout constrained to the sphere: every note repels every other, links pull together, and each group
// starts in its own patch of sky so it settles as a constellation. A link's pull is shared out over its ends'
// links, so hubs sit between their groups instead of dragging every group onto themselves. Seeded, so it's stable.
const BIG_GRAPH = 800, GRID_CELL = 0.25;
function layout(graph) {
  const L = graph.links.map((l) => [index.get(l.source), index.get(l.target)]).filter(([a, b]) => a != null && b != null && a !== b);
  const deg = new Array(graph.nodes.length).fill(0);
  L.forEach(([a, b]) => { deg[a]++; deg[b]++; });
  let label;
  if (graph.group === "folder") {   // pre-grouped graph (e.g. one constellation per repo): skip community detection
    const ids = new Map();
    label = graph.nodes.map((n) => { if (!ids.has(n.folder)) ids.set(n.folder, ids.size); return ids.get(n.folder); });
  } else label = communities(graph.nodes.length, L, deg);
  const size = new Map();
  label.forEach((l) => size.set(l, (size.get(l) || 0) + 1));
  // biggest groups first, spread evenly over the sphere (golden-angle spiral); lone notes go by folder
  const groups = [...size.keys()].sort((a, b) => size.get(b) - size.get(a) || a - b);
  const centres = new Map(groups.map((g, i) => {
    const y = 1 - (2 * (i + 0.5)) / groups.length, r = Math.sqrt(1 - y * y), a = i * 2.39996;
    return [g, new THREE.Vector3(Math.cos(a) * r, y * 0.85, Math.sin(a) * r).normalize()];
  }));
  const spread = (g) => 0.25 + 0.5 * Math.sqrt(size.get(g) / graph.nodes.length);
  const P = graph.nodes.map((n, i) => {
    const rand = rng(hash(n.id));
    return centres.get(label[i]).clone().add(new THREE.Vector3(rand() - 0.5, rand() - 0.5, rand() - 0.5).multiplyScalar(spread(label[i]))).normalize();
  });
  const F = P.map(() => new THREE.Vector3());
  const d = new THREE.Vector3();
  const pull = L.map(([a, b]) => 0.12 / Math.sqrt(Math.min(deg[a], deg[b]) * Math.sqrt(Math.max(deg[a], deg[b]))) * (label[a] === label[b] ? 1 : 0.35));
  for (let it = 0; it < 400; it++) {
    const cool = 1 - it / 400;
    F.forEach((f) => f.set(0, 0, 0));
    const repel = (i, j) => {
      d.subVectors(P[i], P[j]);
      const dist2 = Math.max(d.lengthSq(), 1e-4);
      d.multiplyScalar((label[i] === label[j] ? 0.0012 : 0.0032) / dist2);
      F[i].add(d); F[j].sub(d);
    };
    if (P.length <= BIG_GRAPH) {
      for (let i = 0; i < P.length; i++) for (let j = i + 1; j < P.length; j++) repel(i, j);
    } else {
      // all-pairs is n² per pass and froze the page on a ~3,000-node code graph; past BIG_GRAPH only nearby
      // stars push each other (a 3D grid over the sphere), since the push falls off with distance squared anyway
      const cell = (v) => Math.floor((v + 1) / GRID_CELL);
      const key = (x, y, z) => (x * 64 + y) * 64 + z;
      const grid = new Map();
      P.forEach((p, i) => {
        const k = key(cell(p.x), cell(p.y), cell(p.z));
        (grid.get(k) || grid.set(k, []).get(k)).push(i);
      });
      for (let i = 0; i < P.length; i++) {
        const x = cell(P[i].x), y = cell(P[i].y), z = cell(P[i].z);
        for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) for (let dz = -1; dz <= 1; dz++) {
          const near = grid.get(key(x + dx, y + dy, z + dz));
          if (near) for (const j of near) if (j > i) repel(i, j);
        }
      }
    }
    L.forEach(([a, b], k) => {
      d.subVectors(P[b], P[a]).multiplyScalar(pull[k]);
      F[a].add(d); F[b].sub(d);
    });
    // each note also drifts toward the middle of its own group, which is what keeps a constellation compact
    const mid = new Map();
    P.forEach((p, i) => { if (size.get(label[i]) > 1) mid.set(label[i], (mid.get(label[i]) || new THREE.Vector3()).add(p)); });
    for (let i = 0; i < P.length; i++) {
      const m = mid.get(label[i]);
      if (m) F[i].addScaledVector(d.copy(m).normalize().sub(P[i]), 0.025);
    }
    for (let i = 0; i < P.length; i++) {
      const f = F[i];
      f.addScaledVector(P[i], -f.dot(P[i]));              // tangential only
      const m = f.length(), cap = 0.06 * cool + 0.004;
      if (m > cap) f.multiplyScalar(cap / m);
      P[i].add(f).normalize();
    }
  }
  return { P, L, label };
}

// a rebuild replaces these, so free the old ones: three.js holds their GPU buffers until disposed
function dispose(obj) {
  if (!obj) return;
  obj.removeFromParent();
  obj.geometry.dispose();
  obj.material.dispose();
}

function buildGraph(graph) {
  nodes = graph.nodes;
  index = new Map(nodes.map((n, i) => [n.id, i]));
  const { P, L, label: group } = layout(graph);
  linkPairs = L;
  const deg = new Array(nodes.length).fill(0);
  L.forEach(([a, b]) => { deg[a]++; deg[b]++; });
  nodes.forEach((n, i) => { n.p = P[i].clone().multiplyScalar(R); n.deg = deg[i]; });
  heat = new Float32Array(nodes.length);
  heatKind = new Float32Array(nodes.length);
  ember = new Float32Array(nodes.length);
  tint = new Float32Array(nodes.length);

  const pos = new Float32Array(nodes.length * 3), size = new Float32Array(nodes.length), col = new Float32Array(nodes.length * 3), seed = new Float32Array(nodes.length);
  nodes.forEach((n, i) => {
    pos.set([n.p.x, n.p.y, n.p.z], i * 3);
    size[i] = 5 + Math.sqrt(n.deg) * 3.2;
    const c = new THREE.Color(folderColour(n.folder));
    col.set([c.r, c.g, c.b], i * 3);
    seed[i] = (hash(n.id) % 1000) / 1000;
  });
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  g.setAttribute("size", new THREE.BufferAttribute(size, 1));
  g.setAttribute("color", new THREE.BufferAttribute(col, 3));
  g.setAttribute("seed", new THREE.BufferAttribute(seed, 1));
  g.setAttribute("heat", new THREE.BufferAttribute(heat, 1));
  g.setAttribute("tint", new THREE.BufferAttribute(tint, 1));
  dispose(stars);
  stars = new THREE.Points(g, new THREE.ShaderMaterial({
    uniforms: { uTime: { value: 0 }, uPulse: { value: 0 }, uDim: { value: 1 }, uScale: { value: 1 },
      uTouch: { value: TOUCH_COLOUR } },
    vertexShader: `
      attribute float size; attribute vec3 color; attribute float seed; attribute float heat; attribute float tint;
      uniform float uTime; uniform float uPulse; uniform float uScale; uniform vec3 uTouch;
      varying vec3 vColor; varying float vFront; varying float vHeat; varying float vTw;
      void main() {
        ${facingGLSL}
        vHeat = heat;
        vColor = mix(color, uTouch, tint);
        vTw = 0.82 + 0.18 * sin(uTime * (0.7 + seed * 1.6) + seed * 40.0);
        float s = size * (1.0 + heat * 1.8 + uPulse * 0.55);
        gl_PointSize = s * uScale * (420.0 / -mv.z);
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: `
      uniform float uDim; uniform float uPulse;
      varying vec3 vColor; varying float vFront; varying float vHeat; varying float vTw;
      void main() {
        vec2 uv = gl_PointCoord - 0.5;
        float d = length(uv);
        float core = smoothstep(0.12, 0.0, d);
        float glow = exp(-d * d * 22.0);
        float spikes = (max(0.0, 1.0 - abs(uv.x) * 26.0) + max(0.0, 1.0 - abs(uv.y) * 26.0)) * smoothstep(0.5, 0.0, d);
        float a = (core + glow * 0.75 + spikes * (0.25 + vHeat * 0.6)) * vTw;
        a *= mix(0.16, 1.0, vFront) * uDim * (1.0 + uPulse * 0.5);
        gl_FragColor = vec4(vColor * (1.0 + vHeat * 0.8), a);
      }`,
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  }));
  sky.add(stars);

  // links as great-circle arcs, like constellation lines on an old star globe
  const arcs = [];
  const qa = new THREE.Quaternion();
  for (const [a, b] of L) {
    const A = P[a], B = P[b], arc = [];
    const segs = Math.max(4, Math.ceil(A.angleTo(B) / 0.08));
    for (let s = 0; s <= segs; s++) {
      qa.setFromUnitVectors(A, B);
      const q = new THREE.Quaternion().slerp(qa, s / segs);
      arc.push(A.clone().applyQuaternion(q).multiplyScalar(R * 0.998));
    }
    arcs.push(arc);
  }
  if (links) lineMats.splice(lineMats.indexOf(links.material), 1);
  dispose(links);
  const lg = segmentsGeometry(arcs, "#b98a44");
  // Links inside a group stay bright; ones out to a hub or across to another group are fainter, the longer the fainter,
  // so each constellation reads on its own and the cross-links are a haze behind them.
  {
    const c = lg.attributes.color.array;
    let v = 0;
    L.forEach(([a, b], k) => {
      const same = group[a] === group[b], hub = Math.max(deg[a], deg[b]);
      const long = P[a].angleTo(P[b]);
      const k_ = same ? 1 : Math.max(0.3, Math.min(1, 4 / Math.sqrt(hub))) * 0.7 / (1 + long * 0.8);
      for (let s = 0; s < (arcs[k].length - 1) * 2; s++, v++) { c[v * 3] *= k_; c[v * 3 + 1] *= k_; c[v * 3 + 2] *= k_; }
    });
  }
  lg.userData.base = Float32Array.from(lg.attributes.color.array);
  lg.userData.owner = [];                                // vertex -> [a, b]
  arcs.forEach((arc, k) => { for (let s = 0; s < (arc.length - 1) * 2; s++) lg.userData.owner.push(k); });
  const lm = lineMaterial(0.45);
  lineMats.push(lm);
  links = new THREE.LineSegments(lg, lm);
  sky.add(links);

  // each constellation is named after its busiest note, always faintly there; one name per group keeps them apart
  labelObjs.forEach((o) => o.removeFromParent());
  labelObjs = new Map();
  const named = new Map();
  [...nodes.keys()].sort((a, b) => nodes[b].deg - nodes[a].deg).forEach((i) => { if (!named.has(group[i])) named.set(group[i], i); });
  [...named.values()].filter((i) => nodes[i].deg >= 6).slice(0, 10).forEach((i) => label(i, false));
  $("#notecount").textContent = `${nodes.length} notes · ${L.length} links`;
}

function label(i, hot, kind) {
  let o = labelObjs.get(i);
  if (!o) {
    const el = document.createElement("div");
    el.className = "star-label";
    el.textContent = nodes[i].name;
    o = new CSS2DObject(el);
    o.position.copy(nodes[i].p).multiplyScalar(1.02);
    o.userData = { i, hub: !hot };
    sky.add(o);
    labelObjs.set(i, o);
  }
  o.userData.hot = hot;
  o.element.classList.toggle("hot", hot);
  o.element.classList.toggle("edit", kind === "edit");
  return o;
}

// ---------------------------------------------------------------- touching notes
let focus = null, lastFocus = 0, spinTarget = null;
function touch(ids, act, live, ts) {
  const age = ts ? Math.max(0, (Date.now() - Date.parse(ts)) / 1000) : (live ? 0 : TINT_FADE);
  for (const id of ids) {
    const i = index.get(id);
    if (i == null) continue;
    ember[i] = EMBER;
    tint[i] = Math.max(tint[i], 1 - age / TINT_FADE);
    if (!live) { heat[i] = Math.max(heat[i], EMBER); continue; }
    heat[i] = 1;
    heatKind[i] = act === "edit" ? 1 : Math.min(heatKind[i], 0);
    label(i, true, act);
    const now = performance.now();
    if (act === "edit" || now - lastFocus > 4000) { focus = i; lastFocus = now; }
  }
  if (stars) { stars.geometry.attributes.heat.needsUpdate = true; stars.geometry.attributes.tint.needsUpdate = true; }
}

const held = new Set();                 // the home dashboard's night view holds notes lit; nothing does here

function faceNode(i) {
  // turn the sky about its axis so the note swings round to face the camera
  const p = nodes[i].p;
  const want = -Math.atan2(p.x, p.z) + camAngleInGlobe();
  let cur = sky.rotation.y, delta = ((want - cur) % (Math.PI * 2) + Math.PI * 3) % (Math.PI * 2) - Math.PI;
  spinTarget = { from: cur, to: cur + delta, t0: performance.now(), dur: 2200 };
}
function camAngleInGlobe() {
  const c = camera.position.clone().applyQuaternion(globe.quaternion.clone().invert());
  return Math.atan2(c.x, c.z);
}

// ---------------------------------------------------------------- layout-aware framing
let viewX = null, viewTarget = 0;   // horizontal view offset, eased when the conversation panel folds
let viewY = 0;                      // vertical, on phones: centres the globe in the space below the title
function applyView() {
  camera.setViewOffset(host.clientWidth, host.clientHeight, viewX ?? 0, viewY, host.clientWidth, host.clientHeight);
  camera.updateProjectionMatrix();
}
function resize(animate = false) {
  const w = host.clientWidth, h = host.clientHeight;
  renderer.setSize(w, h);
  labels.setSize(w, h);
  camera.aspect = w / h;
  const narrow = innerWidth <= 820;
  if (narrow) {
    viewX = null;
    viewY = -($("#title").getBoundingClientRect().bottom - host.getBoundingClientRect().top) / 2;
    applyView();
    return;
  }
  viewY = 0;
  // Centre the globe between the conversation and activity panels.
  const left = $("#left").offsetWidth + 16;
  const right = $("#right").offsetWidth + 16;
  viewTarget = -(left - right) / 2;
  if (!animate || viewX === null) viewX = viewTarget;
  applyView();
}
addEventListener("resize", () => resize());

// ---------------------------------------------------------------- hover
const ray = new THREE.Raycaster();
ray.params.Points.threshold = 3.5;
const mouse = new THREE.Vector2();
const tip = $("#tooltip");
let tipPinned = false;
renderer.domElement.addEventListener("pointermove", (e) => {
  if (!stars || tipPinned) return;
  const r = renderer.domElement.getBoundingClientRect();
  mouse.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  ray.setFromCamera(mouse, camera);
  const hit = ray.intersectObject(stars)[0];
  if (hit && hit.distance < camera.position.length()) {
    const n = nodes[hit.index];
    tip.innerHTML = `<b></b><i></i>`;
    tip.querySelector("b").textContent = n.name;
    tip.querySelector("i").textContent = n.blurb || n.folder;
    tip.style.display = "block";
    tip.style.left = Math.min(e.clientX + 14, innerWidth - 320) + "px";
    tip.style.top = e.clientY + 14 + "px";
  } else tip.style.display = "none";
});
renderer.domElement.addEventListener("pointerleave", () => { if (!tipPinned) tip.style.display = "none"; });
let userHold = 0;
controls.addEventListener("start", () => (userHold = Infinity));
controls.addEventListener("end", () => (userHold = performance.now() + 6000));

// ---------------------------------------------------------------- animation
let state = "idle", level = 0, levelTarget = 0;
const clock = new THREE.Clock();
function frame() {
  const dt = Math.min(clock.getDelta(), 0.1), t = clock.elapsedTime;
  if (viewX !== null && viewX !== viewTarget) {
    const d = viewTarget - viewX;
    viewX = Math.abs(d) < 0.5 ? viewTarget : viewX + d * (1 - Math.exp(-dt * 7));
    applyView();
  }
  level += (levelTarget - level) * (levelTarget > level ? 0.5 : 0.12);
  document.body.style.setProperty("--level", level.toFixed(3));

  const working = state === "working";
  if (spinTarget) {
    const k = clamp((performance.now() - spinTarget.t0) / spinTarget.dur, 0, 1);
    const e = k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
    sky.rotation.y = spinTarget.from + (spinTarget.to - spinTarget.from) * e;
    if (k >= 1) spinTarget = null;
  } else sky.rotation.y += dt * SPIN * (working ? 2.2 : 1);
  if (focus != null) { faceNode(focus); focus = null; }
  colureRing.rotation.y += dt * 0.05;
  globe.position.y = Math.sin(t * 0.21) * 3.5;
  globe.rotation.x = Math.sin(t * 0.13) * 0.04;
  controls.autoRotate = performance.now() > userHold;

  // cool touched notes back down to their ember
  if (stars) {
    let hot = false, tinted = false;
    for (let i = 0; i < tint.length; i++) {
      if (tint[i] > 0) { tint[i] = Math.max(0, tint[i] - dt / TINT_FADE); tinted = true; }
    }
    if (tinted) stars.geometry.attributes.tint.needsUpdate = true;
    for (let i = 0; i < heat.length; i++) {
      if (heat[i] > ember[i] && !held.has(i)) { heat[i] = Math.max(ember[i], heat[i] - dt / HEAT_FADE); hot = true; }
    }
    if (hot || frame.wasHot) {
      stars.geometry.attributes.heat.needsUpdate = true;
      const g = links.geometry, c = g.attributes.color.array, base = g.userData.base, owner = g.userData.owner;
      for (let v = 0; v < owner.length; v++) {
        const [a, b] = linkPairs[owner[v]];
        const h = Math.max(heat[a], heat[b]);
        const boost = 1 + h * 3.2;
        c[v * 3] = base[v * 3] * boost; c[v * 3 + 1] = base[v * 3 + 1] * boost; c[v * 3 + 2] = base[v * 3 + 2] * boost;
      }
      g.attributes.color.needsUpdate = true;
    }
    frame.wasHot = hot;
    for (const [i, o] of labelObjs) {
      if (o.userData.hot && heat[i] <= ember[i] + 0.01) {
        if (o.userData.hub) { o.userData.hot = false; o.element.classList.remove("hot", "edit"); }
        else { o.removeFromParent(); labelObjs.delete(i); continue; }
      }
      const wp = o.getWorldPosition(new THREE.Vector3());
      const front = wp.clone().sub(globe.position).normalize().dot(camera.position.clone().sub(wp).normalize());
      o.element.style.opacity = clamp((front + 0.1) * 2.5, 0, 1) * (o.userData.hot ? 1 : 0.55);
    }
    const m = stars.material.uniforms;
    m.uTime.value = t;
    m.uPulse.value = level;
    m.uDim.value = state === "offline" ? 0.55 : 1;
  }
  lineMats.forEach((m) => (m.uniforms.uDim.value = state === "offline" ? 0.5 : 1 + level * 0.8));
  const breathe = state === "listening" || state === "asking" ? 0.5 + 0.5 * Math.sin(t * 3) : 0;
  halo.material.opacity = (state === "offline" ? 0.25 : 0.55) + level * 0.6 + breathe * 0.35 + (working ? 0.12 * Math.sin(t * 1.3) : 0);
  halo.material.color.set(state === "listening" ? 0xa8e0c8 : state === "asking" ? 0xfff0d8 : 0xffffff);
  halo.scale.setScalar(R * (3.4 + level * 0.5 + breathe * 0.2));
  halo.position.copy(globe.position);

  controls.update();
  renderer.render(scene, camera);
  labels.render(scene, camera);
  requestAnimationFrame(frame);
}

// ---------------------------------------------------------------- transcript
const entriesEl = $("#entries");
const toolEls = new Map();
marked.setOptions({ gfm: true, breaks: true });
const md = (s) => DOMPurify.sanitize(marked.parse(s));
const MAX_ENTRY_ELS = 900;           // about the server's 300-entry history; a tool call is two elements
const nearBottom = () => entriesEl.scrollHeight - entriesEl.scrollTop - entriesEl.clientHeight < 80;

function addEntry(e, live, touchNotes = true) {
  const stick = nearBottom();
  if (live && e.kind === "claude") dropStream();
  if (e.kind === "user" || e.kind === "claude") {
    const div = document.createElement("div");
    div.className = `entry ${e.kind}${live ? " live" : ""}`;
    const who = e.kind === "user" ? "You" : "Claude";
    div.innerHTML = `<span class="who"></span><div class="body"></div>`;
    div.querySelector(".who").textContent = who;
    const body = div.querySelector(".body");
    if (e.kind === "claude") { body.innerHTML = md(e.text); work.decorate(body, live); }
    else { body.textContent = e.text; body.style.display = "inline"; }
    entriesEl.append(div);
  } else if (e.kind === "tool") {
    const div = document.createElement("div");
    div.className = `tool${e.act === "edit" && e.notes.length ? " edit" : ""}`;
    div.innerHTML = `<span class="name"></span> <span class="sum"></span> <span class="count"></span>`;
    div.querySelector(".name").textContent = "▸ " + e.tool.replace("__", " · ");
    div.querySelector(".sum").textContent = e.summary;
    div.title = e.summary;
    const res = document.createElement("pre");
    res.className = "tool-result";
    div.addEventListener("click", () => div.classList.toggle("open"));
    entriesEl.append(div, res);
    div.dataset.id = e.id;
    toolEls.set(e.id, div);
    if (touchNotes && e.notes.length) touch(e.notes, e.act, live, e.ts);
  } else if (e.kind === "result") {
    const div = toolEls.get(e.id);
    if (div) {
      div.nextSibling.textContent = e.text || "(no output)";
      div.querySelector(".count").textContent = e.lines ? `· ${e.lines} line${e.lines === 1 ? "" : "s"}` : "";
      if (e.error) div.classList.add("error");
    }
  }
  // keep only the recent conversation, as the server does, so a long session doesn't pile up in the page
  while (entriesEl.childElementCount > MAX_ENTRY_ELS) {
    const old = entriesEl.firstElementChild;
    if (old.dataset.id) toolEls.delete(old.dataset.id);
    old.remove();
  }
  if (stick || !live) entriesEl.scrollTop = entriesEl.scrollHeight;
}

function tick() {
  $("#clock").textContent = new Date().toLocaleString([], { weekday: "long", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });
}
setInterval(tick, 10000);
tick();

// ---------------------------------------------------------------- sessions
// Every Claude session from the last few hours is a medallion under the conversation; a working one is lit.
// The conversation shows one: the latest working one until you pick one, which pins it.
const sessions = new Map();                  // id -> meta {id, title, cwd, last, working, driving}
let shown = null, pinned = false, config = {};
const submitting = new Set();
const work = new WorkControls({session: () => shown, meta: () => sessions.get(shown), error: showError, markdown: md});

function ago(t) {
  const s = Date.now() / 1000 - t;
  return s < 60 ? "just now" : s < 3600 ? `${Math.round(s / 60)} min ago` : s < 86400 ? `${Math.floor(s / 3600)} h ago` : `${Math.floor(s / 86400)} d ago`;
}
const shortCwd = (p) => (p || "").replace(/^\/Users\/[^/]+/, "~").replace(/^\/home\/[^/]+/, "~");
const NS = "http://www.w3.org/2000/svg";

function medallion(m) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = `med${m.working ? " working" : ""}${m.id === shown ? " on" : ""}${m.add ? " add" : ""}`;
  const glyph = m.add ? "+" : (m.title || "?").trim().charAt(0).toUpperCase();
  b.innerHTML = `<svg viewBox="0 0 66 66"><circle class="disc" cx="33" cy="33" r="24"/><circle class="arc" cx="33" cy="33" r="29"/><text class="glyph" x="33" y="34"></text></svg><div class="cap"></div>`;
  b.querySelector(".glyph").textContent = glyph;
  b.querySelector(".cap").textContent = m.add ? "New" : m.title;
  b.title = m.add ? "Start a new session, or pick up an older one" : `${m.title}\n${shortCwd(m.cwd)}\n${m.working ? "working" : ago(m.last)}`;
  return b;
}

function renderSessions() {
  const list = [...sessions.values()].sort((a, b) => b.last - a.last);
  const add = medallion({ add: true });
  add.addEventListener("click", togglePopover);
  $("#sessions").replaceChildren(...list.map((m) => {
    const b = medallion(m);
    b.addEventListener("click", () => { pinned = true; $("#popover").hidden = true; show(m.id); });
    return b;
  }), add);
  state = list.some((m) => m.working) ? "working" : "idle";   // the globe turns faster while any session works
  document.body.dataset.state = state;
  syncComposer();
}
setInterval(renderSessions, 30000);

function syncComposer() {
  const m = sessions.get(shown);
  const other = m && m.working && !m.driving;
  const busy = m && m.driving;
  $("#draft").disabled = !m || other || !work.connected;
  $("#send").disabled = $("#draft").disabled || submitting.has(shown);
  $("#draft").placeholder = !m ? "Start a session below, or pick one" : busy ? "Type a correction to stop and redirect Claude…" : other ? "Another process is driving this session" : "Write to Claude";
  const note = $("#driver-note");
  note.hidden = !(busy || other);
  note.textContent = busy ? "working · corrections interrupt" : "driven elsewhere";
  work.render();
}

const streamEl = () => entriesEl.querySelector(".entry.streaming");
function dropStream() { streamEl()?.remove(); }
function delta(text) {
  let el = streamEl();
  if (!el) {
    el = document.createElement("div");
    el.className = "entry claude streaming";
    el.innerHTML = `<span class="who">Claude</span><div class="body"></div>`;
    entriesEl.append(el);
  }
  const stick = nearBottom();
  el.querySelector(".body").textContent += text;
  if (stick) entriesEl.scrollTop = entriesEl.scrollHeight;
}

async function show(id) {
  if (shown !== id) work.closePreview();
  shown = id;
  renderSessions();
  const m = sessions.get(id);
  $("#session-title").textContent = m?.title || "The Conversation";
  $("#session-cwd").textContent = shortCwd(m?.cwd);
  entriesEl.innerHTML = "";
  toolEls.clear();
  try {
    const r = await (await fetch(`/api/session/${id}`)).json();
    if (shown !== id) return;
    r.history.forEach((e) => addEntry(e, false, false));
    work.restore(r.runtime);
  } catch {}
}

function onSession(m) {
  const was = sessions.get(m.id);
  sessions.set(m.id, m);
  if (!pinned && m.working && m.id !== shown) show(m.id);   // follow whichever session is busy
  else if (m.id === shown) {
    $("#session-title").textContent = m.title;
    $("#session-cwd").textContent = shortCwd(m.cwd);
    if (was?.pending && !m.pending) show(m.id);              // its log file now exists: load the turn so far
  }
  renderSessions();
}

// new session or an older one
async function togglePopover() {
  const pop = $("#popover");
  pop.hidden = !pop.hidden;
  if (pop.hidden) return;
  if (!$("#new-cwd").value) $("#new-cwd").value = config.defaultCwd || "";
  const list = $("#older-list");
  list.textContent = "";
  try {
    const older = await (await fetch("/api/sessions/older")).json();
    list.replaceChildren(...older.map((o) => {
      const d = document.createElement("div");
      d.className = "old";
      d.innerHTML = "<span></span><small></small>";
      d.querySelector("span").textContent = o.title;
      d.querySelector("small").textContent = `${shortCwd(o.cwd)} · ${ago(o.last)}`;
      d.title = o.id;
      d.addEventListener("click", async () => {
        const r = await fetch(`/api/session/${o.id}/adopt`, { method: "POST" });
        if (!r.ok) return;
        const { session } = await r.json();
        sessions.set(session.id, session);
        pinned = true;
        pop.hidden = true;
        show(session.id);
      });
      return d;
    }));
    if (!older.length) list.innerHTML = '<p class="muted">No older sessions.</p>';
  } catch {}
}

$("#new-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const r = await fetch("/api/sessions/new", { method: "POST", body: JSON.stringify({ cwd: $("#new-cwd").value.trim() }) });
  const j = await r.json();
  if (!r.ok) return showError(j.error);
  $("#popover").hidden = true;
  pinned = true;
  if (!sessions.has(j.id)) sessions.set(j.id, { id: j.id, title: "New session", cwd: $("#new-cwd").value.trim(), last: Date.now() / 1000 });
  await show(j.id);
  $("#draft").focus();
});

function showError(text) {
  const el = $("#composer-error");
  el.hidden = !text;
  el.textContent = text || "";
}

async function sendText(text) {
  if (!shown || !text.trim() || submitting.has(shown)) return false;
  showError("");
  const sid = shown, m = sessions.get(sid);
  submitting.add(sid); syncComposer();
  try {
    await post(`/api/session/${sid}/${m?.driving ? 'interrupt' : 'send'}`, {text});
    return true;
  } catch(e) { showError(e.message); return false; }
  finally { submitting.delete(sid); syncComposer(); }
}
$("#composer").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const text = $("#draft").value;
  if (await sendText(text)) { if ($("#draft").value === text) $("#draft").value = ""; }
});
$("#draft").addEventListener("keydown", (ev) => {
  if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) { ev.preventDefault(); $("#composer").requestSubmit(); }
});

// click a star: a note opens in Obsidian; a code file lists its functions/classes in the tooltip (click empty sky to close)
renderer.domElement.addEventListener("click", (e) => {
  if (!stars) return;
  const r = renderer.domElement.getBoundingClientRect();
  mouse.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  ray.setFromCamera(mouse, camera);
  const hit = ray.intersectObject(stars)[0];
  if (graphId !== "notes") {
    if (hit && hit.distance < camera.position.length() && nodes[hit.index].symbols) {
      const n = nodes[hit.index];
      tip.innerHTML = `<b></b><i></i><ul style="margin:6px 0 0;padding-left:16px;max-height:50vh;overflow:auto"></ul>`;
      tip.querySelector("b").textContent = n.name;
      tip.querySelector("i").textContent = `${n.folder}/${n.path}`;
      const ul = tip.querySelector("ul");
      for (const s of n.symbols.slice(0, 200)) {
        const li = document.createElement("li");
        li.textContent = `${s.label}  ${s.loc}`;
        ul.append(li);
      }
      if (!n.symbols.length) ul.innerHTML = "<li>no functions or classes</li>";
      tipPinned = true;
      tip.style.pointerEvents = "auto";
      tip.style.display = "block";
      tip.style.left = Math.min(e.clientX + 14, innerWidth - 320) + "px";
      tip.style.top = Math.min(e.clientY + 14, innerHeight - 300) + "px";
    } else { tipPinned = false; tip.style.display = "none"; }
    return;
  }
  if (!vaultName) return;
  if (hit && hit.distance < camera.position.length())
    location.href = `obsidian://open?vault=${encodeURIComponent(vaultName)}&file=${encodeURIComponent(nodes[hit.index].id)}`;
});

// ---------------------------------------------------------------- extension points
// add-ons (addons/README.md) and the optional voice hook get this small API; both are off unless present.
const listeners = new Map();
const on = (ev, fn) => listeners.set(ev, [...(listeners.get(ev) || []), fn]);
const emit = (ev, data) => (listeners.get(ev) || []).forEach((fn) => { try { fn(data); } catch (e) { console.error(e); } });
const api = { on, send: sendText, status: ({listening = false} = {}) => { work.listening = listening; work.render(); }, session: () => shown, touch: (ids, act = "read") => touch(ids, act, true) };

async function loadExtensions() {
  for (const a of config.addons || []) {
    if (!a.panel) continue;
    try {
      const panel = document.createElement("section");
      panel.className = "panel addon";
      panel.dataset.addon = a.name;
      $("#addons").append(panel);
      (await import(a.panel)).mount(panel, api);
    } catch (e) { console.error(`add-on ${a.name}`, e); }
  }
  if (config.voice) {
    try {
      const v = await import("/voice/hook.js");
      v.init?.(api);
      work.voice = true; work.render();
      if (v.toggle) { $("#mic").hidden = false; $("#mic").addEventListener("click", () => v.toggle()); }
    } catch (e) { console.error("voice hook", e); }
  }
}

// ---------------------------------------------------------------- the globe slot
let graphId = "notes", vaultName = null;
async function loadGraph(id = graphId) {
  const g = await (await fetch(`/api/graph/${id}`)).json();
  vaultName = g.vault;
  graphId = id; tipPinned = false; tip.style.display = "none";
  buildGraph(g);
  const src = (config.graphs || []).find((s) => s.id === id);
  $("#flip-name").textContent = src?.label || id;
}
$("#flip").addEventListener("click", async () => {
  const all = config.graphs || [];
  if (all.length < 2) return;
  const next = all[(all.findIndex((s) => s.id === graphId) + 1) % all.length];
  $("#flip").classList.add("turning");
  setTimeout(() => $("#flip").classList.remove("turning"), 700);
  try { await loadGraph(next.id); } catch (e) { console.error("flip failed", e); }
});

// ---------------------------------------------------------------- wiring
function connect() {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (["status", "permission", "permission_done", "usage"].includes(m.t)) work.event(m);
    switch (m.t) {
      case "hello":
        work.connection(true);
        work.restore(m.runtime);
        heat.fill(0); ember.fill(0); tint.fill(0);
        if (graphId === "notes") m.touches.forEach((t) => touch(t.notes, t.act, false, t.ts));
        sessions.clear();
        m.sessions.forEach((s) => sessions.set(s.id, s));
        if (!shown || !sessions.has(shown)) { pinned = false; if (m.sessions[0]) show(m.sessions[0].id); else renderSessions(); }
        else show(shown);
        break;
      case "session": onSession(m.session); break;
      case "entry":
        if (m.entry.kind === "tool" && m.entry.notes.length && graphId === "notes") touch(m.entry.notes, m.entry.act, true, m.entry.ts);
        if (m.session === shown) addEntry(m.entry, true, false);
        if (m.entry.kind === "claude") emit("reply", { session: m.session, text: m.entry.text });
        break;
      case "delta":
        if (m.session === shown) delta(m.text);
        emit("delta", m);
        break;
      case "turn_end":
        if (m.session === shown) { dropStream(); showError(m.error); show(m.session); }
        break;
    }
  };
  ws.onclose = () => { work.connection(false); syncComposer(); setTimeout(connect, 2000); };
  ws.onerror = () => ws.close();
}

resize();
config = await (await fetch("/api/config")).json();
$("#flip").classList.toggle("single", (config.graphs || []).length < 2);
$("#flip").title = (config.graphs || []).length < 2 ? "Only the notes graph is registered (see README: pluggable graph sources)" : "Flip the globe to the next graph";
await loadGraph(new URLSearchParams(location.search).get("graph") || "notes");
connect();
frame();
loadExtensions();
setInterval(async () => {                    // pick up new notes and links; keep what's lit
  try {
    const g = await (await fetch(`/api/graph/${graphId}`)).json();
    if (g.nodes.length !== nodes.length || g.links.length !== linkPairs.length) {
      const keep = new Map(nodes.map((n, i) => [n.id, [heat[i], ember[i], heatKind[i], tint[i]]]));
      buildGraph(g);
      nodes.forEach((n, i) => { const k = keep.get(n.id); if (k) [heat[i], ember[i], heatKind[i], tint[i]] = k; });
    }
  } catch {}
}, 30000);

// session strip: fade an edge only when medallions are scrolled past it; the wheel scrolls sideways
{
  const strip = $("#sessions");
  const edges = () => {
    const max = strip.scrollWidth - strip.clientWidth;
    strip.classList.toggle("fade-l", strip.scrollLeft > 1);
    strip.classList.toggle("fade-r", strip.scrollLeft < max - 1);
  };
  strip.addEventListener("scroll", edges, { passive: true });
  strip.addEventListener("wheel", (e) => {
    if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) { strip.scrollLeft += e.deltaY; e.preventDefault(); }
  }, { passive: false });
  new ResizeObserver(edges).observe(strip);
  new MutationObserver(edges).observe(strip, { childList: true });
}

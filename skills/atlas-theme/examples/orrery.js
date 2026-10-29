// STRUCTURE EXAMPLE: an orrery. Index is the sun, each folder is a tilted brass ring, notes are beads riding their ring.
// Inspiration only: it shows ring layouts with decoration (tick marks, an armillary meridian) that belongs to the idea.
export default function (atlas) {
  const { THREE, globe, parts, controls, camera } = atlas;
  const stage = new THREE.Group(); globe.add(stage);
  const folders = () => [...new Set(atlas.nodes.map((n) => n.folder || "·"))];
  const ringOf = (f) => folders().indexOf(f || "·");
  atlas.setLayout((nodes, links, T) => {
    const byRing = {};
    nodes.forEach((n, i) => (byRing[ringOf(n.folder)] = byRing[ringOf(n.folder)] || []).push(i));
    const pos = new Array(nodes.length);
    Object.entries(byRing).forEach(([r, ids]) => {
      const radius = 0.55 + r * 0.38, tilt = new T.Euler(0.35 + r * 0.45, 0, r * 0.7);
      ids.forEach((i, k) => {
        const a = (k / ids.length) * Math.PI * 2 + r;
        pos[i] = new T.Vector3(Math.cos(a) * radius, Math.sin(a) * radius, 0).applyEuler(tilt);
      });
    });
    const sun = nodes.findIndex((n) => n.name === "Index");
    if (sun >= 0) pos[sun] = new T.Vector3(0, 0, 0);
    return pos;
  });
  let spinners = [];
  atlas.onBuild(() => {
    stage.clear(); spinners = [];
    parts.lines.visible = false; for (const o of [parts.body, parts.rim, parts.graticule]) o.visible = false;
    atlas.pickThreshold = 0.07; controls.target.set(0, 0, 0); camera.position.set(0, 1.6, 4.6);
    const brass = new THREE.MeshBasicMaterial({ color: atlas.css("--link", "#c9a45c") });
    folders().forEach((f, r) => {
      const radius = 0.55 + r * 0.38, g = new THREE.Group();
      g.rotation.set(0.35 + r * 0.45, 0, r * 0.7);
      g.add(new THREE.Mesh(new THREE.TorusGeometry(radius, 0.006, 8, 160), brass));
      for (let k = 0; k < 48; k++) {                                         // tick marks round the ring
        const a = (k / 48) * Math.PI * 2, t = new THREE.Mesh(new THREE.BoxGeometry(0.004, k % 4 ? 0.02 : 0.045, 0.004), brass);
        t.position.set(Math.cos(a) * radius, Math.sin(a) * radius, 0); t.rotation.z = a - Math.PI / 2; g.add(t);
      }
      stage.add(g);
    });
    const sun = new THREE.Mesh(new THREE.SphereGeometry(0.16, 24, 16), new THREE.MeshBasicMaterial({ color: atlas.css("--accent", "#f2d68e") }));
    stage.add(sun); spinners.push(sun);
  });
  atlas.onFrame((t) => { stage.rotation.y = t / 22000; for (const s of spinners) s.scale.setScalar(1 + 0.06 * Math.sin(t / 500)); });
}

// STRUCTURE EXAMPLE: the notes as a tree. Index is the trunk, hubs are boughs, notes are leaves that sway; links become the twigs.
// Inspiration for how a layout and its own geometry replace the sphere. Do not reuse as is: draw your own trees (or whatever suits).
export default function (atlas) {
  const { THREE, scene, globe, parts, controls, camera } = atlas;
  const stage = new THREE.Group(); globe.add(stage);
  const leafColor = (i) => new THREE.Color(atlas.css(`--node-${(atlas.nodes[i] ? hash(atlas.nodes[i].folder) : 0) % 8 + 1}`, "#c0813a"));
  const hash = (s) => [...s].reduce((a, c) => (a * 31 + c.charCodeAt(0)) >>> 0, 7);
  let leaves, leafData = [], branches;

  atlas.setLayout((nodes, links, T) => {
    const h = atlas.hierarchy(), pos = new Array(nodes.length), ang = new Array(nodes.length), len = new Array(nodes.length);
    const place = (i, p, dir, d) => {              // grow children outward and upward from this node
      pos[i] = p;
      const kids = h.children[i], spread = Math.min(2.4, 0.5 + kids.length * 0.35);
      kids.forEach((k, j) => {
        const a = dir + (kids.length === 1 ? 0 : (j / (kids.length - 1) - 0.5) * spread) + (Math.random() - 0.5) * 0.15;
        const l = Math.max(0.25, 0.9 / (d + 1.2)) * (0.85 + Math.random() * 0.3);
        place(k, new T.Vector3(p.x + Math.sin(a) * l, p.y + Math.cos(a) * l * 0.8, p.z + (Math.random() - 0.5) * l * 0.9), a, d + 1);
      });
    };
    place(h.root, new T.Vector3(0, -1.3, 0), 0, 0);
    return pos;
  });

  atlas.onBuild(() => {
    stage.clear();
    parts.cloud.visible = false; parts.lines.visible = false;            // hidden, but still used to pick the note under the pointer
    for (const o of [parts.body, parts.rim, parts.graticule]) o.visible = false;
    atlas.pickThreshold = 0.09;
    controls.target.set(0, -0.1, 0); camera.position.set(0, 0.2, 4.4); controls.autoRotateSpeed = 0.5;
    const h = atlas.hierarchy(), P = atlas.positions;
    // boughs: a curved tube from each parent to each child
    const group = new THREE.Group();
    atlas.nodes.forEach((_, i) => {
      const p = h.parent[i]; if (p < 0) return;
      const a = P[p], b = P[i], mid = a.clone().lerp(b, 0.5).add(new THREE.Vector3((Math.random() - 0.5) * 0.08, 0.05, 0));
      const w = Math.max(0.004, 0.03 / (h.depth[i] + 0.5));
      group.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.QuadraticBezierCurve3(a, mid, b), 10, w, 5), new THREE.MeshBasicMaterial({ color: atlas.css("--link", "#6b4a2a") })));
    });
    stage.add(group);
    // leaves: one flat leaf shape per note, tinted by folder, swaying and flaring when the assistant touches the note
    const shape = new THREE.Shape(); shape.moveTo(0, 0); shape.quadraticCurveTo(0.07, 0.07, 0, 0.2); shape.quadraticCurveTo(-0.07, 0.07, 0, 0);
    leaves = new THREE.InstancedMesh(new THREE.ShapeGeometry(shape), new THREE.MeshBasicMaterial({ side: THREE.DoubleSide, transparent: true }), atlas.nodes.length);
    leafData = atlas.nodes.map((_, i) => ({ rot: Math.random() * Math.PI * 2, tilt: (Math.random() - 0.5) * 1.2, ph: Math.random() * 6.28 }));
    atlas.nodes.forEach((_, i) => leaves.setColorAt(i, leafColor(i)));
    stage.add(leaves);
  });

  const m = new THREE.Object3D();
  atlas.onFrame((t) => {
    if (!leaves) return;
    atlas.nodes.forEach((n, i) => {
      const d = leafData[i], g = atlas.glow(n.id, t);
      m.position.copy(atlas.positions[i]);
      m.rotation.set(0.4, d.rot + Math.sin(t / 1400 + d.ph) * 0.18, d.tilt + Math.sin(t / 900 + d.ph) * 0.1);
      m.scale.setScalar(1 + g * 1.6 + 0.05 * Math.sin(t / 700 + d.ph));
      m.updateMatrix(); leaves.setMatrixAt(i, m.matrix);
    });
    leaves.instanceMatrix.needsUpdate = true;
  });
}

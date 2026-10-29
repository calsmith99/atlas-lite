// STRUCTURE EXAMPLE: a night city. Each folder is a district, each note a tower whose height is how linked it is,
// windows lit at random, a touched tower flares. Inspiration only: it shows nodes drawn as boxes on a grid.
export default function (atlas) {
  const { THREE, globe, parts, controls, camera } = atlas;
  const stage = new THREE.Group(); globe.add(stage);
  let towers, base = [];
  atlas.setLayout((nodes, links, T) => {
    const deg = nodes.map(() => 0); const idx = new Map(nodes.map((n, i) => [n.id, i]));
    links.forEach((l) => { deg[idx.get(l.source)]++; deg[idx.get(l.target)]++; });
    const districts = [...new Set(nodes.map((n) => n.folder || "·"))], pos = [];
    districts.forEach((d, di) => {
      const ids = nodes.map((n, i) => i).filter((i) => (nodes[i].folder || "·") === d), cols = Math.ceil(Math.sqrt(ids.length));
      ids.forEach((i, k) => pos[i] = new T.Vector3((di - (districts.length - 1) / 2) * 1.5 + (k % cols) * 0.2 - cols * 0.1, 0.05 + Math.min(1.6, 0.12 + deg[i] * 0.05) / 2, Math.floor(k / cols) * 0.2 - 0.3));
    });
    base = deg;
    return pos;
  });
  atlas.onBuild(() => {
    stage.clear(); parts.lines.visible = false; parts.cloud.visible = false;
    for (const o of [parts.body, parts.rim, parts.graticule]) o.visible = false;
    atlas.pickThreshold = 0.1; controls.target.set(0, 0.3, 0); camera.position.set(0, 1.1, 4.2);
    const ground = new THREE.GridHelper(8, 40, atlas.css("--link", "#4a5a7a"), atlas.css("--link", "#2a3350")); ground.material.opacity = 0.4; ground.material.transparent = true;
    stage.add(ground);
    towers = new THREE.InstancedMesh(new THREE.BoxGeometry(0.14, 1, 0.14), new THREE.MeshBasicMaterial(), atlas.nodes.length);
    atlas.nodes.forEach((n, i) => towers.setColorAt(i, new THREE.Color(atlas.css(`--node-${i % 8 + 1}`, "#7c9cff")).multiplyScalar(0.55)));
    stage.add(towers);
  });
  const m = new THREE.Object3D();
  atlas.onFrame((t) => {
    if (!towers) return;
    atlas.nodes.forEach((n, i) => {
      const h = Math.min(1.6, 0.12 + base[i] * 0.05), g = atlas.glow(n.id, t);
      m.position.set(atlas.positions[i].x, h / 2, atlas.positions[i].z); m.scale.set(1 + g * 0.6, h * (1 + g * 0.3), 1 + g * 0.6);
      m.updateMatrix(); towers.setMatrixAt(i, m.matrix);
    });
    towers.instanceMatrix.needsUpdate = true;
  });
}

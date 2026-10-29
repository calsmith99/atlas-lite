// API EXAMPLE, not a template. It shows how custom.js talks to the renderer: scene objects added next to and inside the globe,
// per-frame animation, rebuild hooks and reading the theme variables. Its look (a halo, stars, two rings, travelling pulses) is
// one arbitrary design among endless possibilities. Never reuse it as the user's look: design the renderer from their words.
export default function (atlas) {
  const { THREE, scene, globe, parts, controls } = atlas;
  const col = (name, fb) => new THREE.Color(atlas.css(name, fb));
  const stage = new THREE.Group();            // does not turn with the notes: stars, halo, rings
  scene.add(stage);
  globe.rotation.z = 0.32;                    // axial tilt

  const soft = (() => {                       // round soft-edged sprite texture
    const c = document.createElement("canvas"); c.width = c.height = 128;
    const g = c.getContext("2d"), r = g.createRadialGradient(64, 64, 0, 64, 64, 64);
    r.addColorStop(0, "rgba(255,255,255,1)"); r.addColorStop(0.35, "rgba(255,255,255,.45)"); r.addColorStop(1, "rgba(255,255,255,0)");
    g.fillStyle = r; g.fillRect(0, 0, 128, 128);
    return new THREE.CanvasTexture(c);
  })();

  // starfield
  const N = 1400, sp = new Float32Array(N * 3);
  for (let i = 0; i < N; i++) {
    const r = 6 + Math.random() * 9, a = Math.random() * Math.PI * 2, y = Math.random() * 2 - 1, k = Math.sqrt(1 - y * y);
    sp.set([Math.cos(a) * k * r, y * r, Math.sin(a) * k * r], i * 3);
  }
  const starGeo = new THREE.BufferGeometry();
  starGeo.setAttribute("position", new THREE.BufferAttribute(sp, 3));
  const stars = new THREE.Points(starGeo, new THREE.PointsMaterial({ size: 0.035, map: soft, transparent: true, opacity: 0.7, depthWrite: false,
    color: col("--globe-shell", "#ffffff"), blending: THREE.AdditiveBlending }));
  stage.add(stars);

  // halo behind the sphere
  const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: soft, color: col("--globe-rim", "#7c9cff"), transparent: true, opacity: 0.32,
    depthWrite: false, blending: THREE.AdditiveBlending }));
  halo.scale.set(4.6, 4.6, 1);
  stage.add(halo);

  // two orbit rings, each with a few satellites
  const rings = [[1.32, 0.9, 0.0, 0.25], [1.5, -0.5, 0.6, -0.17]].map(([radius, tx, tz, speed]) => {
    const g = new THREE.Group();
    g.rotation.set(tx, 0, tz);
    g.add(new THREE.Mesh(new THREE.TorusGeometry(radius, 0.0035, 8, 240),
      new THREE.MeshBasicMaterial({ color: col("--link", "#9db4ff"), transparent: true, opacity: 0.4, depthWrite: false })));
    const sats = new THREE.Points(new THREE.BufferGeometry(), new THREE.PointsMaterial({ size: 0.11, map: soft, transparent: true,
      color: col("--accent", "#7c9cff"), depthWrite: false, blending: THREE.AdditiveBlending }));
    const pos = new Float32Array(9);
    for (let i = 0; i < 3; i++) { const a = (i / 3) * Math.PI * 2; pos.set([Math.cos(a) * radius, Math.sin(a) * radius, 0], i * 3); }
    sats.geometry.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    g.add(sats);
    stage.add(g);
    return { g, speed };
  });

  // light pulses that travel along the links
  let pulses = null, pulseState = [];
  const PULSES = 28;
  const arcAt = (a, b, t) => {                // same lift as the arcs the globe draws
    const ang = a.angleTo(b), lift = 0.12 * Math.min(ang, 1.6) / 1.6;
    return a.clone().lerp(b, t).normalize().multiplyScalar(1 + Math.sin(t * Math.PI) * lift + 0.004);
  };
  function rebuild() {
    if (pulses) { globe.remove(pulses); pulses.geometry.dispose(); pulses.material.dispose(); }
    const idx = new Map(atlas.nodes.map((n, i) => [n.id, i]));
    const links = atlas.links.map((l) => [atlas.positions[idx.get(l.source)], atlas.positions[idx.get(l.target)]]).filter((l) => l[0] && l[1]);
    pulseState = links.length ? Array.from({ length: Math.min(PULSES, links.length) }, () => ({
      l: links[Math.floor(Math.random() * links.length)], t: Math.random(), v: 0.18 + Math.random() * 0.3 })) : [];
    pulses = new THREE.Points(new THREE.BufferGeometry(), new THREE.PointsMaterial({ size: 0.085, map: soft, transparent: true, depthWrite: false,
      color: col("--glow", "#ffffff"), blending: THREE.AdditiveBlending }));
    pulses.geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(pulseState.length * 3), 3));
    pulses.userData.links = links;
    globe.add(pulses);
    // a slightly bolder, additive look for the notes themselves
    parts.cloud.material.blending = THREE.AdditiveBlending;
    parts.lines.material.blending = THREE.AdditiveBlending;
    parts.lines.material.opacity = Math.min(0.55, parts.lines.material.opacity * 1.3);
  }
  atlas.onBuild(rebuild);

  let last = 0;
  atlas.onFrame((t) => {
    const dt = Math.min(0.05, (t - last) / 1000); last = t;
    stars.rotation.y += dt * 0.004;
    for (const { g, speed } of rings) g.children[1].rotation.z += dt * speed * 2;
    if (parts.cloud) parts.cloud.material.size = 0.13 + 0.02 * Math.sin(t / 650);
    if (pulses && pulseState.length) {
      const arr = pulses.geometry.attributes.position.array, links = pulses.userData.links;
      pulseState.forEach((p, i) => {
        p.t += dt * p.v;
        if (p.t >= 1) { p.t = 0; p.l = links[Math.floor(Math.random() * links.length)]; }
        arr.set(arcAt(p.l[0], p.l[1], p.t).toArray(), i * 3);
      });
      pulses.geometry.attributes.position.needsUpdate = true;
    }
    halo.material.opacity = 0.28 + 0.05 * Math.sin(t / 1800);
  });
}

// The Hopper level built as a porcelain lab diorama: plates on pillars in front of
// a measured grid wall (a motion-study backdrop), a floor plate at the kill plane,
// the goal drawn as a spectrograph slit, and the bodies for the player and ghosts.
import * as THREE from "three";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";
import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { LEVEL } from "@/hopper/sim";

export interface Palette {
  ground: string;
  plate: string;
  ink: string;
  muted: string;
  faint: string;
  line: string;
  hairline: string;
  accent: string;
  broken: string;
  amber: string;
  mono: string;
}

const FLOOR_Y = LEVEL.killY;
const WALL_Z = -6.5;
const SPAN = { from: -12, to: 100 };

/** A tiling grid texture: one cell = `units` world units, minor line every unit. */
function gridTexture(p: Palette, units: number): THREE.CanvasTexture {
  const px = 128 * units;
  const c = document.createElement("canvas");
  c.width = px;
  c.height = px;
  const g = c.getContext("2d")!;
  g.fillStyle = p.plate;
  g.fillRect(0, 0, px, px);
  const cell = px / units;
  g.strokeStyle = p.hairline;
  g.lineWidth = 2;
  for (let i = 1; i < units; i++) {
    g.beginPath();
    g.moveTo(i * cell, 0);
    g.lineTo(i * cell, px);
    g.moveTo(0, i * cell);
    g.lineTo(px, i * cell);
    g.stroke();
  }
  g.strokeStyle = p.line;
  g.lineWidth = 3;
  g.strokeRect(0, 0, px, px);
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  return tex;
}

/** One long strip of x labels (0, 5, 10 ...) for the top of the grid wall. */
function rulerTexture(p: Palette): { tex: THREE.CanvasTexture; width: number } {
  const unitsWide = SPAN.to - SPAN.from;
  const ppu = 48;
  const c = document.createElement("canvas");
  c.width = Math.min(8192, unitsWide * ppu);
  c.height = 96;
  const scale = c.width / unitsWide;
  const g = c.getContext("2d")!;
  g.clearRect(0, 0, c.width, c.height);
  g.fillStyle = p.muted;
  g.strokeStyle = p.muted;
  g.font = `500 26px ${p.mono}`;
  g.textBaseline = "top";
  for (let x = Math.ceil(SPAN.from); x <= SPAN.to; x++) {
    const sx = (x - SPAN.from) * scale;
    const major = x % 5 === 0;
    g.lineWidth = major ? 3 : 1.5;
    g.beginPath();
    g.moveTo(sx, c.height);
    g.lineTo(sx, c.height - (major ? 40 : 18));
    g.stroke();
    if (major && x >= 0 && x <= 90) g.fillText(String(x).padStart(2, "0"), sx + 6, 8);
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  return { tex, width: unitsWide };
}

function edges(geo: THREE.BufferGeometry, color: string, opacity: number): THREE.LineSegments {
  return new THREE.LineSegments(
    new THREE.EdgesGeometry(geo, 20),
    new THREE.LineBasicMaterial({ color, transparent: true, opacity }),
  );
}

export interface Body {
  group: THREE.Group;
  mesh: THREE.Mesh;
}

function body(material: THREE.Material): Body {
  // origin at the middle of the feet, like the game's pos
  const geo = new RoundedBoxGeometry(0.8, 1.6, 0.8, 3, 0.14);
  geo.translate(0, 0.8, 0);
  const mesh = new THREE.Mesh(geo, material);
  mesh.castShadow = true;
  const group = new THREE.Group();
  group.add(mesh);
  return { group, mesh };
}

export function trailLine(points: number[], color: string, dashed: boolean): Line2 {
  const geo = new LineGeometry();
  geo.setPositions(points);
  const mat = new LineMaterial({
    color,
    linewidth: 2.4,
    worldUnits: false,
    transparent: true,
    opacity: 0.95,
    dashed,
    dashSize: 0.45,
    gapSize: 0.28,
  });
  const line = new Line2(geo, mat);
  if (dashed) line.computeLineDistances();
  line.frustumCulled = false;
  return line;
}

export interface World {
  scene: THREE.Scene;
  sun: THREE.DirectionalLight;
  ferry: THREE.Group;
  coins: THREE.Mesh[];
  player: Body;
  ghosts: { base: Body; head: Body };
  impact: THREE.Mesh;
  measure: THREE.Group;
  materials: THREE.Material[];
  dispose: () => void;
}

export function buildWorld(p: Palette): World {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(p.ground);
  scene.fog = new THREE.Fog(p.ground, 34, 78);
  const disposables: { dispose: () => void }[] = [];
  const keep = <T extends { dispose: () => void }>(x: T) => (disposables.push(x), x);

  scene.add(new THREE.HemisphereLight(0xffffff, new THREE.Color(p.hairline), 1.25));
  const sun = new THREE.DirectionalLight(0xfff6e8, 1.9);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.camera.left = -34;
  sun.shadow.camera.right = 34;
  sun.shadow.camera.top = 26;
  sun.shadow.camera.bottom = -26;
  sun.shadow.camera.near = 1;
  sun.shadow.camera.far = 120;
  sun.shadow.bias = -0.0004;
  sun.shadow.normalBias = 0.03;
  sun.shadow.radius = 4;
  scene.add(sun, sun.target);

  const plateMat = keep(new THREE.MeshStandardMaterial({ color: p.plate, roughness: 0.62, metalness: 0 }));
  const ferryMat = keep(new THREE.MeshStandardMaterial({ color: p.plate, roughness: 0.5, metalness: 0 }));

  // platforms: the real collision boxes on top, a pillar under each down to the floor plate
  let ferry = new THREE.Group();
  for (const plat of LEVEL.platforms) {
    const sx = plat.max[0] - plat.min[0];
    const sz = plat.max[2] - plat.min[2];
    const top = plat.max[1];
    const isFerry = Boolean(plat.move);
    const bottom = isFerry ? plat.min[1] : FLOOR_Y;
    const sy = top - bottom;
    const geo = keep(new THREE.BoxGeometry(sx, sy, sz));
    const mesh = new THREE.Mesh(geo, isFerry ? ferryMat : plateMat);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    const group = new THREE.Group();
    group.add(mesh, edges(keep(geo), isFerry ? p.accent : p.ink, isFerry ? 0.7 : 0.22));
    // top face rule: a hairline inset along the front edge, like a plate's scale
    const lip = new THREE.Mesh(
      keep(new THREE.BoxGeometry(sx, 0.02, 0.06)),
      keep(new THREE.MeshBasicMaterial({ color: isFerry ? p.accent : p.line })),
    );
    lip.position.set(0, sy / 2 + 0.011, sz / 2 - 0.25);
    group.add(lip);
    group.position.set((plat.min[0] + plat.max[0]) / 2, bottom + sy / 2, (plat.min[2] + plat.max[2]) / 2);
    scene.add(group);
    if (isFerry) ferry = group;
  }

  // the measured wall behind the level and the floor plate at the kill plane
  const wallW = SPAN.to - SPAN.from;
  const wallH = 34;
  const wallTex = keep(gridTexture(p, 5));
  wallTex.repeat.set(wallW / 5, wallH / 5);
  const wall = new THREE.Mesh(
    keep(new THREE.PlaneGeometry(wallW, wallH)),
    keep(new THREE.MeshStandardMaterial({ map: wallTex, roughness: 0.95 })),
  );
  wall.position.set((SPAN.from + SPAN.to) / 2, FLOOR_Y + wallH / 2, WALL_Z);
  wall.receiveShadow = true;
  scene.add(wall);

  const ruler = rulerTexture(p);
  keep(ruler.tex);
  const rulerMesh = new THREE.Mesh(
    keep(new THREE.PlaneGeometry(ruler.width, 1.2)),
    keep(new THREE.MeshBasicMaterial({ map: ruler.tex, transparent: true, depthWrite: false })),
  );
  rulerMesh.position.set((SPAN.from + SPAN.to) / 2, 7.6, WALL_Z + 0.02);
  scene.add(rulerMesh);

  const floorTex = keep(gridTexture(p, 5));
  floorTex.repeat.set(wallW / 5, 24 / 5);
  const floor = new THREE.Mesh(
    keep(new THREE.PlaneGeometry(wallW, 24)),
    keep(new THREE.MeshStandardMaterial({ map: floorTex, roughness: 0.95 })),
  );
  floor.rotation.x = -Math.PI / 2;
  floor.position.set((SPAN.from + SPAN.to) / 2, FLOOR_Y, WALL_Z + 12);
  floor.receiveShadow = true;
  scene.add(floor);

  // the goal: a slit of indigo light between two posts
  const g = LEVEL.goal;
  const gx = (g.min[0] + g.max[0]) / 2;
  const gh = g.max[1] - g.min[1];
  const slit = new THREE.Mesh(
    keep(new THREE.PlaneGeometry(0.16, gh)),
    keep(new THREE.MeshBasicMaterial({ color: p.accent, transparent: true, opacity: 0.9, side: THREE.DoubleSide })),
  );
  slit.position.set(gx, g.min[1] + gh / 2, 0);
  scene.add(slit);
  const postGeo = keep(new THREE.BoxGeometry(0.14, gh + 0.4, 0.14));
  const postMat = keep(new THREE.MeshStandardMaterial({ color: p.ink, roughness: 0.4 }));
  for (const side of [-1, 1]) {
    const post = new THREE.Mesh(postGeo, postMat);
    post.position.set(gx, g.min[1] + (gh + 0.4) / 2, side * (g.max[2] - g.min[2]) * 0.5);
    post.castShadow = true;
    scene.add(post);
  }

  const coinGeo = keep(new THREE.TorusGeometry(0.32, 0.075, 10, 28));
  const coinMat = keep(new THREE.MeshStandardMaterial({ color: p.amber, roughness: 0.35, metalness: 0.15 }));
  const coins = LEVEL.coins.map((c) => {
    const m = new THREE.Mesh(coinGeo, coinMat);
    m.position.set(c[0], c[1], c[2]);
    m.castShadow = true;
    scene.add(m);
    return m;
  });

  const playerMat = keep(new THREE.MeshStandardMaterial({ color: p.ink, roughness: 0.45 }));
  const ghostMat = (color: string) =>
    keep(new THREE.MeshStandardMaterial({ color, roughness: 0.5, transparent: true, opacity: 0.55, depthWrite: false }));
  const player = body(playerMat);
  const ghosts = { base: body(ghostMat(p.accent)), head: body(ghostMat(p.broken)) };
  ghosts.base.mesh.castShadow = false;
  ghosts.head.mesh.castShadow = false;
  scene.add(player.group, ghosts.base.group, ghosts.head.group);

  // where the head ghost hits the floor plate
  const impact = new THREE.Mesh(
    keep(new THREE.RingGeometry(0.5, 0.62, 40)),
    keep(new THREE.MeshBasicMaterial({ color: p.broken, transparent: true, opacity: 0.9, depthWrite: false })),
  );
  impact.rotation.x = -Math.PI / 2;
  impact.visible = false;
  scene.add(impact);

  const measure = new THREE.Group();
  measure.visible = false;
  scene.add(measure);

  return {
    scene,
    sun,
    ferry,
    coins,
    player,
    ghosts,
    impact,
    measure,
    materials: [plateMat, ferryMat],
    dispose: () => disposables.forEach((d) => d.dispose()),
  };
}

/** Straight measured segments: a bracket over the gap and ticks where each build comes down. */
export function measureLines(points: number[][], color: string): Line2[] {
  return points.map((pts) => trailLine(pts, color, false));
}

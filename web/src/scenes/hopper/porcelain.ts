// The Hopper level's own material: porcelain read as a spectrograph plate.
// MeshStandardMaterial plus three patches, so lights, shadows and fog stay three's.
//  1. Measured ink: a notebook grid in world units and a ruler hung off the front
//     lip, baked into the top faces, so the diorama reads as a measuring instrument.
//  2. Spectral glaze: where a glaze thins at an edge it shows a thin film. The film
//     samples the spectrum ramp, weighted by Fresnel so it only catches at grazing
//     angles, like light dispersing through a slit. Low strength: an edge, not a rainbow.
//  3. Micro grain: static world-space speckle so large faces are not flat CG.
// Nothing here moves with time; the sheen changes only with the view, so a reduced
// motion still frame is complete.
import * as THREE from "three";
import type { Palette } from "./world";

type PorcelainPalette = Pick<Palette, "plate" | "line" | "faint" | "accent" | "amber" | "broken">;

export interface PorcelainOptions {
  roughness: number;
  /** a texture that already carries the grid (wall, floor): they get the grain only */
  map?: THREE.Texture;
  /** half extents of a box: turns on the edge glaze and the ink on its top face */
  box?: [number, number, number];
  /** the group position when the ink must ride along with the mesh (the ferry); omit to measure in the world */
  ride?: THREE.Vector3;
  /** spectrum stops, violet to vermilion; read from the design tokens when omitted */
  ramp?: string[];
}

const SHEEN = 0.42; // peak share of the film colour at the very edge, at a grazing angle
const GRAIN = 0.022; // albedo speckle, plus or minus half of this
const PROGRAM_KEY = "noether-porcelain-1";

/** The spectrum ramp from the tokens (--spec-1..5), which exist only in the browser. */
function spectrumRamp(p: PorcelainPalette): string[] {
  const token = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return [p.accent, token("--spec-2"), token("--spec-3"), p.amber, p.broken];
}

const VERT_PARS = /* glsl */ `
uniform vec3 uAnchor;
uniform float uRide;
varying vec3 vMeasure;
varying vec3 vLocal;
varying vec3 vFaceN;
`;

// vMeasure is where ink and grain are looked up: the world, or the mesh itself when it rides
const VERT_MAIN = /* glsl */ `
vec3 pcWorld = (modelMatrix * vec4(transformed, 1.0)).xyz;
vMeasure = mix(pcWorld, position + uAnchor, uRide);
vLocal = position;
vFaceN = normal;
`;

const FRAG_PARS = /* glsl */ `
uniform vec3 uHalf;
uniform float uInk;
uniform float uSheen;
uniform float uGrain;
uniform vec3 uInkLine;
uniform vec3 uInkFaint;
uniform vec3 uRamp[5];
varying vec3 vMeasure;
varying vec3 vLocal;
varying vec3 vFaceN;

// a hairline every 'period' units, 'px' pixels wide, melting away once cells fall under ~3 px
float pcRule(float c, float period, float px) {
  float x = c / period;
  float aa = max(fwidth(x), 1e-5);
  float d = abs(fract(x - 0.5) - 0.5) / aa;
  return (1.0 - clamp(d - 0.5 * px + 0.5, 0.0, 1.0)) * (1.0 - smoothstep(0.28, 0.5, aa));
}

// a tick of length 'len' hanging back from the lip, soft-ended by the pixel footprint
float pcBand(float depth, float aa, float len) {
  return (1.0 - smoothstep(len - aa, len + aa, depth)) * smoothstep(-aa, aa, depth);
}

float pcHash(vec3 p) {
  p = fract(p * 0.1031);
  p += dot(p, p.zyx + 31.32);
  return fract((p.x + p.y) * p.z);
}

vec3 pcSpectrum(float t) {
  vec3 c = uRamp[0];
  c = mix(c, uRamp[1], clamp(t * 4.0, 0.0, 1.0));
  c = mix(c, uRamp[2], clamp(t * 4.0 - 1.0, 0.0, 1.0));
  c = mix(c, uRamp[3], clamp(t * 4.0 - 2.0, 0.0, 1.0));
  return mix(c, uRamp[4], clamp(t * 4.0 - 3.0, 0.0, 1.0));
}
`;

// grain first, then the ink, both before lighting so shadows fall on them
const FRAG_INK = /* glsl */ `
float pcCells = 7.0;
float pcFade = 1.0 - smoothstep(0.35, 0.9, length(fwidth(vMeasure)) * pcCells);
diffuseColor.rgb *= 1.0 + uGrain * pcFade * (pcHash(floor(vMeasure * pcCells)) - 0.5);

float pcTop = step(0.5, vFaceN.y) * uInk;
float pcMinor = max(pcRule(vMeasure.x, 1.0, 1.0), pcRule(vMeasure.z, 1.0, 1.0));
float pcMajor = max(pcRule(vMeasure.x, 5.0, 1.4), pcRule(vMeasure.z, 5.0, 1.4));
float pcDepth = (uHalf.z - 0.25) - vLocal.z;
float pcAaZ = max(fwidth(pcDepth), 1e-4);
float pcTick = max(
  max(pcRule(vMeasure.x, 0.5, 1.0) * pcBand(pcDepth, pcAaZ, 0.45), pcRule(vMeasure.x, 1.0, 1.0) * pcBand(pcDepth, pcAaZ, 0.8)),
  pcRule(vMeasure.x, 5.0, 1.6) * pcBand(pcDepth, pcAaZ, 1.3)
);
vec3 pcInk = mix(diffuseColor.rgb, uInkLine, pcMinor * 0.85);
pcInk = mix(pcInk, uInkFaint, max(pcMajor * 0.4, pcTick * 0.7));
diffuseColor.rgb = mix(diffuseColor.rgb, pcInk, pcTop);
`;

// after lighting: tint the lit result so the film dims with the shadow it sits in
const FRAG_SHEEN = /* glsl */ `
float pcNdv = clamp(dot(normal, normalize(vViewPosition)), 0.0, 1.0);
float pcFres = pow(1.0 - pcNdv, 2.5);
vec3 pcGap = uHalf - abs(vLocal) + abs(vFaceN) * 1000.0;
float pcEdge = max(min(pcGap.x, min(pcGap.y, pcGap.z)), 0.0);
float pcBandW = 0.8;
float pcRim = 1.0 - smoothstep(0.0, pcBandW, pcEdge);
float pcWobble = 0.5 + 0.5 * sin(vMeasure.x * 0.9 + sin(vMeasure.z * 0.7) * 1.3 + vMeasure.y * 0.5);
float pcThick = clamp(pcEdge / pcBandW * 0.95 + (1.0 - pcFres) * 0.1 + (pcWobble - 0.5) * 0.3, 0.0, 1.0);
vec3 pcFilm = pcSpectrum(pcThick);
pcFilm /= max(max(pcFilm.r, pcFilm.g), pcFilm.b);
outgoingLight = mix(outgoingLight, outgoingLight * pcFilm, uSheen * pcFres * pcRim * sqrt(pcRim));
`;

function inject(src: string, hook: string, code: string, before = false): string {
  if (!src.includes(hook)) throw new Error(`porcelain: ${hook} is missing from three's shader`);
  return src.replace(hook, () => (before ? code + hook : hook + code));
}

/** Patch the vertex and fragment source of a MeshStandardMaterial program. Exported for the test. */
export function patchPorcelain(vertexShader: string, fragmentShader: string): { vertexShader: string; fragmentShader: string } {
  let v = inject(vertexShader, "#include <common>", VERT_PARS);
  v = inject(v, "#include <begin_vertex>", VERT_MAIN);
  let f = inject(fragmentShader, "#include <common>", FRAG_PARS);
  f = inject(f, "#include <color_fragment>", FRAG_INK);
  f = inject(f, "#include <opaque_fragment>", FRAG_SHEEN, true);
  return { vertexShader: v, fragmentShader: f };
}

export function porcelain(p: PorcelainPalette, opts: PorcelainOptions): THREE.MeshStandardMaterial {
  const mat = new THREE.MeshStandardMaterial({
    color: opts.map ? 0xffffff : p.plate,
    ...(opts.map && { map: opts.map }),
    roughness: opts.roughness,
    metalness: 0,
  });
  const half = opts.box ?? [0, 0, 0];
  const uniforms = {
    uAnchor: { value: opts.ride ?? new THREE.Vector3() },
    uRide: { value: opts.ride ? 1 : 0 },
    uHalf: { value: new THREE.Vector3(...half) },
    uInk: { value: opts.box ? 1 : 0 },
    uSheen: { value: opts.box ? SHEEN : 0 },
    uGrain: { value: GRAIN },
    uInkLine: { value: new THREE.Color(p.line) },
    uInkFaint: { value: new THREE.Color(p.faint) },
    uRamp: { value: (opts.ramp ?? spectrumRamp(p)).map((c) => new THREE.Color(c)) },
  };
  mat.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, uniforms);
    Object.assign(shader, patchPorcelain(shader.vertexShader, shader.fragmentShader));
  };
  mat.customProgramCacheKey = () => PROGRAM_KEY;
  return mat;
}

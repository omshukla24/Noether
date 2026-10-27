// Every duration, ease, lerp and runway on the site lives here.
// Instrument-calm: lines settle, only the break snaps.

export const EASE = {
  emergence: 'expo.out', // things arriving
  emergenceCss: 'cubic-bezier(0.16, 1, 0.3, 1)',
  orbital: 'power4.inOut', // travel between two resting states (camera moves)
  orbitalCss: 'cubic-bezier(0.83, 0, 0.17, 1)',
  settle: 'power3.out', // a spectral line locking onto its twin
  snap: 'expo.inOut', // the fracture, used once per break
  exit: 'power2.in',
};

export const DURATION = { micro: 0.3, base: 0.9, cinematic: 1.35 };

export const LENIS = { duration: 1.15, wheelMultiplier: 0.92, touchMultiplier: 1.1 };

export const REVEAL = { yPercent: 118, duration: 1.05, stagger: 0.035, start: 'top 88%', blur: 14 };

// Runways in viewport heights, matching the scene script.
export const RUNWAY = { gap: 3.0, slit: 0.6, darkroom: 2.0, collapse: 2.4, reprove: 1.7 };

// Beats of The Collapse, as fractions of its pinned scroll (0 = plates tilt in, 1 = seal set).
export const COLLAPSE = {
  drift: [0.08, 0.58], // head lines travel from scattered to their base twins
  driftWindow: 0.24, // how much of the scroll one line takes to settle
  tear: [0.6, 0.72], // the silent line dashes and drops
  thread: [0.74, 0.9], // the vermilion thread draws to the source line
  seal: [0.9, 0.98], // the round seal sets
  scatterX: 0.1, // plate widths a head line starts off its twin
  scatterY: 0.07,
  tearDrop: 0.1, // plate heights the torn line falls
  tearShift: 0.035, // plate widths it slips sideways
};

// The slit closes over the first half of its scroll and disperses over the second.
export const SLIT = { close: [0, 0.5], spread: [0.45, 1], minWidthPx: 4 };

// Darkroom: the branch plates fan out between these scroll fractions.
export const DARKROOM = { fan: [0.08, 0.7] };

// Judge drag: pixels past which a release counts as a drop, the spring, and the tilt per pixel.
export const JUDGE = { dropDistance: 120, springDuration: 1.1, tilt: 0.045 };

export const HOPPER_VIEW = {
  cameraLerp: 0.085, // follow cam, frame-rate independent (see damp in math.js)
  trailPoints: 900,
  squash: 0.18,
  fov: 30,
};

export const PERF = { dprMax: 1.75, dprDegraded: 1.25, degradeFrameMs: 22, sampleFrames: 90 };

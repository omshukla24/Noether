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

// Runways in viewport heights, one per scroll-driven section.
export const RUNWAY = { gap: 3.0, slit: 0.6, darkroom: 2.0, collapse: 2.4, reprove: 1.2 };

export const HOPPER_VIEW = {
  cameraLerp: 0.085, // follow cam, frame-rate independent (see damp in math.js)
  trailPoints: 900,
  squash: 0.18,
  fov: 30,
};

export const PERF = { dprMax: 1.75, dprDegraded: 1.25, degradeFrameMs: 22, sampleFrames: 90 };

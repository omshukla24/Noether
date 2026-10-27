// One shared promise per heavy scene chunk, so the preloader can count the
// download and the sections that use it do not fetch it twice.
// The chunk (three.js and the Hopper level, about 145 KB gzipped) is requested only once the page has
// painted and the main thread is idle, so it never competes with the first paint or with hydration.
let hopper: Promise<typeof import("./hopper/scene")> | null = null;

const IDLE_TIMEOUT_MS = 1200;

// Resolves in the task after the next frame, so the first paint is never behind the chunk request.
export const nextFrame = () => new Promise<void>((resolve) => requestAnimationFrame(() => setTimeout(resolve)));

const whenIdle = () =>
  new Promise<void>((resolve) => {
    if ("requestIdleCallback" in window) window.requestIdleCallback(() => resolve(), { timeout: IDLE_TIMEOUT_MS });
    else setTimeout(resolve, 200);
  });

export const loadHopper = () =>
  (hopper ??= nextFrame()
    .then(whenIdle)
    .then(() => import("./hopper/scene")));

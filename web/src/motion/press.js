// Press feedback for every control: a short dip on press, a spring back on release.
// It animates the independent `scale` property, so it never fights GSAP's transforms, and each new
// animation starts from the scale the last one left, so a press can interrupt a spring at any point.
import { prefersReducedMotion } from './env.js';

const TOUCHABLE = 'button, a[href], [role="button"], summary';
const DIP = { scale: '0.965', duration: 110, easing: 'cubic-bezier(0.22, 0.61, 0.36, 1)' };
// a lightly damped spring sampled into linear(): one overshoot, settled by ~70 %
const SPRING = {
  scale: '1',
  duration: 620,
  easing:
    'linear(0, 0.009, 0.035 2.1%, 0.141, 0.281 6.7%, 0.723 12.9%, 0.938 16.7%, 1.017, 1.077, 1.121, 1.149 24.3%, 1.159, 1.163, 1.161, 1.154 29.9%, 1.129 32.8%, 1.051 39.6%, 1.017 43.1%, 0.991, 0.977 51%, 0.974 53.8%, 0.975 57.1%, 0.997 69.8%, 1.003 76.9%, 1)',
};

export function initPress(root = document) {
  if (prefersReducedMotion()) return () => {};
  const running = new WeakMap();
  let pressed = null;

  const go = (el, { scale, duration, easing }) => {
    const from = getComputedStyle(el).scale;
    running.get(el)?.cancel();
    running.set(el, el.animate([{ scale: from === 'none' ? '1' : from }, { scale }], { duration, easing, fill: 'forwards' }));
  };
  const press = (e) => {
    const el = e.target instanceof Element ? e.target.closest(TOUCHABLE) : null;
    if (!el || (e.type === 'keydown' && (e.repeat || (e.key !== 'Enter' && e.key !== ' ')))) return;
    pressed = el;
    go(el, DIP);
  };
  const release = () => {
    if (pressed) go(pressed, SPRING);
    pressed = null;
  };

  const on = [['pointerdown', press], ['keydown', press], ['pointerup', release], ['pointercancel', release], ['keyup', release], ['focusout', release]];
  on.forEach(([type, fn]) => root.addEventListener(type, fn, true));
  return () => on.forEach(([type, fn]) => root.removeEventListener(type, fn, true));
}

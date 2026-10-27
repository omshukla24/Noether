// Endless marquee that speeds up and skews with scroll velocity, and flips
// direction when the reader scrolls back up. Items are cloned to fill 2x width.
import { gsap } from 'gsap';
import { prefersReducedMotion } from './env.js';
import { clamp } from './math.js';
import { scrollVelocity } from './scroll.js';

export function initMarquees(root = document) {
  if (prefersReducedMotion()) return () => {};
  const ticks = [];

  root.querySelectorAll('[data-marquee]').forEach((el) => {
    const track = el.querySelector('[data-marquee-track]');
    const first = track?.firstElementChild;
    if (!first) return;
    while (track.scrollWidth < el.offsetWidth * 2 + first.offsetWidth) {
      const clone = first.cloneNode(true);
      clone.setAttribute('aria-hidden', 'true');
      track.append(clone);
    }
    const unit = () => track.children[1].offsetLeft - track.children[0].offsetLeft;
    const baseSpeed = parseFloat(el.dataset.speed) || 60; // px per second
    const setX = gsap.quickSetter(track, 'x', 'px');
    const setSkew = gsap.quickSetter(track, 'skewX', 'deg');
    let x = 0;
    let direction = 1;

    const tick = (_time, deltaMs) => {
      const velocity = scrollVelocity();
      if (Math.abs(velocity) > 0.5) direction = Math.sign(velocity);
      const speed = baseSpeed + Math.min(Math.abs(velocity) * 40, 900);
      const width = unit();
      x = (((x - direction * speed * (deltaMs / 1000)) % width) - width) % width;
      setX(x);
      setSkew(clamp(-velocity * 0.12, -7, 7));
    };
    gsap.ticker.add(tick);
    ticks.push(tick);
  });

  return () => ticks.forEach((tick) => gsap.ticker.remove(tick));
}

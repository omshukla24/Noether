// Preloader driven by real work, not a fake timer: fonts, marked images and any
// extra promises (a WebGL scene, a video) each move the counter. It is a status
// chip and a top rule over a page that is already readable, so a slow asset can
// never hold the reader back; the hard cap only ends the counter.
import { gsap } from 'gsap';
import { EASE } from './config.js';
import { prefersReducedMotion } from './env.js';
import { padPercent } from './math.js';

const HARD_CAP_MS = 4000;

/**
 * @param {HTMLElement | null} el
 * @param {{ tasks?: Promise<unknown>[], minMs?: number }} [options]
 */
export function runPreloader(el, { tasks = [], minMs = 700 } = {}) {
  if (!el) return Promise.resolve();
  const bar = el.querySelector('[data-preload-bar]');
  const pct = el.querySelector('[data-preload-pct]');
  const word = el.querySelector('[data-preload-word]');
  const words = (el.dataset.words || 'LOADING').split('|');
  const reduced = prefersReducedMotion();

  const images = [...document.querySelectorAll('img[data-preload]')].map((img) => img.decode().catch(() => {}));
  const jobs = [document.fonts.ready, ...images, ...tasks].map((job) => Promise.resolve(job).catch(() => {}));
  const shown = { v: 0 };
  let done = 0;

  const render = () => {
    el.style.setProperty('--p', shown.v.toFixed(3));
    if (bar) bar.style.transform = `scaleX(${shown.v})`;
    if (pct) pct.textContent = padPercent(shown.v);
    if (word) word.textContent = words[Math.min(words.length - 1, Math.floor(shown.v * words.length))];
  };
  const advance = () => {
    done += 1;
    gsap.to(shown, { v: (done / jobs.length) * 0.9, duration: 0.6, ease: EASE.settle, onUpdate: render, overwrite: 'auto' });
  };
  jobs.forEach((job) => job.then(advance));
  render();

  const settled = Promise.all(jobs);
  const capped = Promise.race([settled, new Promise((r) => setTimeout(r, HARD_CAP_MS))]);
  const minimum = new Promise((r) => setTimeout(r, reduced ? 0 : minMs));

  return Promise.all([capped, minimum]).then(() => new Promise((resolve) => {
    const finish = () => {
      el.remove();
      resolve();
    };
    if (reduced) {
      gsap.to(el, { autoAlpha: 0, duration: 0.3, onComplete: finish });
      return;
    }
    gsap.timeline({ onComplete: finish })
      .to(shown, { v: 1, duration: 0.4, ease: EASE.settle, onUpdate: render })
      .to(el.querySelector('[data-preload-inner]'), { y: 8, autoAlpha: 0, duration: 0.4, ease: EASE.exit })
      .to(el, { autoAlpha: 0, duration: 0.3, ease: EASE.exit }, '-=0.1');
  }));
}

"use client";

import { useEffect, useRef } from "react";
import { prefersReducedMotion } from "@/motion/env.js";

interface RouteCountProps {
  value: number;
  decimals?: number;
  prefix?: string;
  suffix?: string;
}

const format = (n: number, decimals: number) => n.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
const RUN_MS = 1100;

// A tabular number that counts up the first time it is seen. The server prints the final value, so
// it is correct without script and in reduced motion; the count is a flourish and always lands on it.
export function RouteCount({ value, decimals = 0, prefix = "", suffix = "" }: RouteCountProps) {
  const el = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const node = el.current;
    if (!node || prefersReducedMotion()) return;
    let frame = 0;
    let settle = 0;
    const show = (n: number) => {
      node.textContent = `${prefix}${format(n, decimals)}${suffix}`;
    };
    const io = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return;
      io.disconnect();
      const t0 = performance.now();
      const step = (now: number) => {
        const p = Math.min(1, (now - t0) / RUN_MS);
        show(value * (1 - Math.pow(1 - p, 4)));
        if (p < 1) frame = requestAnimationFrame(step);
      };
      show(0);
      frame = requestAnimationFrame(step);
      settle = window.setTimeout(() => show(value), RUN_MS + 300);
    }, { threshold: 0.6 });
    io.observe(node);
    return () => {
      io.disconnect();
      cancelAnimationFrame(frame);
      window.clearTimeout(settle);
      show(value);
    };
  }, [value, decimals, prefix, suffix]);

  return (
    <span ref={el} className="tabular" suppressHydrationWarning>
      {prefix}
      {format(value, decimals)}
      {suffix}
    </span>
  );
}

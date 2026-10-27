"use client";

import { useEffect, useRef, type RefObject } from "react";
import type { Input } from "@/hopper/sim";
import type { HopperScene } from "./scene";

const KEYS: Record<string, [keyof Input, number]> = {
  ArrowLeft: ["x", -1],
  KeyA: ["x", -1],
  ArrowRight: ["x", 1],
  KeyD: ["x", 1],
  ArrowUp: ["z", -1],
  KeyW: ["z", -1],
  ArrowDown: ["z", 1],
  KeyS: ["z", 1],
  Space: ["jump", 1],
};

/**
 * Keyboard and touch input for a Hopper level, live only while `target` has focus so Space still
 * scrolls the page everywhere else. Escape hands the focus back.
 */
export function useHopperControls(
  target: RefObject<HTMLElement | null>,
  scene: RefObject<HopperScene | null>,
  onPlaying: (on: boolean) => void,
) {
  useEffect(() => {
    const el = target.current;
    if (!el) return;
    const held = new Set<string>();
    const push = () => {
      const input: Input = { x: 0, z: 0, jump: false };
      held.forEach((code) => {
        const [axis, v] = KEYS[code];
        if (axis === "jump") input.jump = true;
        else input[axis] = Math.max(-1, Math.min(1, input[axis] + v));
      });
      scene.current?.setInput(input);
    };
    const onDown = (e: KeyboardEvent) => {
      if (e.code === "Escape") {
        el.blur();
        return;
      }
      if (!KEYS[e.code]) return;
      e.preventDefault();
      held.add(e.code);
      push();
    };
    const onUp = (e: KeyboardEvent) => {
      if (!KEYS[e.code]) return;
      held.delete(e.code);
      push();
    };
    const onFocus = () => {
      onPlaying(true);
      scene.current?.setPlaying(true);
    };
    const onBlur = () => {
      held.clear();
      push();
      onPlaying(false);
      scene.current?.setPlaying(false);
    };
    el.addEventListener("keydown", onDown);
    el.addEventListener("keyup", onUp);
    el.addEventListener("focus", onFocus);
    el.addEventListener("blur", onBlur);
    return () => {
      el.removeEventListener("keydown", onDown);
      el.removeEventListener("keyup", onUp);
      el.removeEventListener("focus", onFocus);
      el.removeEventListener("blur", onBlur);
    };
  }, [target, scene, onPlaying]);

  const pad = useRef<Input>({ x: 0, z: 0, jump: false });
  /** pointer handlers for one on-screen button of the touch pad */
  return (axis: keyof Input, v: number, onStart: () => void) => {
    const set = (on: boolean) => {
      pad.current = { ...pad.current, [axis]: axis === "jump" ? on : on ? v : 0 };
      scene.current?.setInput(pad.current);
    };
    return {
      onPointerDown: (e: React.PointerEvent) => {
        e.preventDefault();
        scene.current?.setPlaying(true);
        onStart();
        set(true);
      },
      onPointerUp: () => set(false),
      onPointerLeave: () => set(false),
    };
  };
}

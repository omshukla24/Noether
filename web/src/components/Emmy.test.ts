import { describe, expect, it } from "vitest";
import { spells } from "./Emmy";

function typeOut(text: string) {
  let typed = "";
  let hits = 0;
  for (const key of text) {
    const step = spells(typed, key);
    typed = step.hit ? "" : step.typed;
    if (step.hit) hits += 1;
  }
  return hits;
}

describe("easter egg word", () => {
  it("fires once the four letters are typed in a row, in any case", () => {
    expect(typeOut("emmy")).toBe(1);
    expect(typeOut("xxEMMYxx")).toBe(1);
    expect(typeOut("emmyemmy")).toBe(2);
  });

  it("ignores near misses", () => {
    expect(typeOut("emm")).toBe(0);
    expect(typeOut("emmmy")).toBe(0);
    expect(typeOut("e m m y")).toBe(0);
    expect(typeOut("emyy")).toBe(0);
  });
});

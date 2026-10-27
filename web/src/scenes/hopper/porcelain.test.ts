import * as THREE from "three";
import { describe, expect, it } from "vitest";
import { patchPorcelain, porcelain } from "./porcelain";

const palette = { plate: "#FCFBF7", line: "#DEDBD1", faint: "#8C8A82", accent: "#4B3FE4", amber: "#E4B23A", broken: "#D93A22" };
const ramp = ["#4B3FE4", "#2E7BE4", "#16A6B6", "#E4B23A", "#D93A22"];
const { vertexShader, fragmentShader } = THREE.ShaderLib.physical;

describe("porcelain material", () => {
  it("patches three's standard program and keeps every original chunk", () => {
    const out = patchPorcelain(vertexShader, fragmentShader);
    expect(out.vertexShader).toContain("vMeasure = mix(pcWorld");
    expect(out.fragmentShader).toContain("pcSpectrum(pcThick)");
    expect(out.fragmentShader).toContain("diffuseColor.rgb = mix(diffuseColor.rgb, pcInk, pcTop)");
    for (const chunk of ["lights_fragment_begin", "shadowmap_pars_fragment", "opaque_fragment", "fog_fragment"]) {
      expect(out.fragmentShader).toContain(`#include <${chunk}>`);
    }
    // the sheen reads the lit colour, so it has to come before the colour leaves the lighting stage
    expect(out.fragmentShader.indexOf("pcFres")).toBeLessThan(out.fragmentShader.indexOf("#include <opaque_fragment>"));
  });

  it("fails loudly when three renames a chunk it hooks into", () => {
    expect(() => patchPorcelain(vertexShader, fragmentShader.replace("#include <opaque_fragment>", ""))).toThrow(/opaque_fragment/);
  });

  it("turns the ink and the edge glaze on for boxes only", () => {
    const shader = { uniforms: {} as Record<string, { value: unknown }>, vertexShader, fragmentShader };
    porcelain(palette, { roughness: 0.6, box: [2, 3, 4], ramp }).onBeforeCompile(shader as never, {} as never);
    expect(shader.uniforms.uInk.value).toBe(1);
    expect(shader.uniforms.uSheen.value).toBeGreaterThan(0);
    expect((shader.uniforms.uRamp.value as THREE.Color[]).length).toBe(5);

    const flat = { uniforms: {} as Record<string, { value: unknown }>, vertexShader, fragmentShader };
    porcelain(palette, { roughness: 0.9, ramp }).onBeforeCompile(flat as never, {} as never);
    expect(flat.uniforms.uInk.value).toBe(0);
    expect(flat.uniforms.uSheen.value).toBe(0);
  });
});

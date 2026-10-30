import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { parseAction, parseCaps, parseExitCodes, pyString, workflowSecrets } from "./action";

const read = (...parts: string[]) => readFileSync(join(__dirname, "..", "..", ...parts), "utf8");

describe("parseAction", () => {
  it("reads every input, output and step of the real action.yml", () => {
    const spec = parseAction(read("src", "content", "action.yml"));
    expect(spec.inputs.map((i) => i.name)).toEqual(["nebius-api-key", "nebius-project-id", "tavily-api-key", "fail-on-broken", "fix"]);
    expect(spec.inputs[0]).toEqual({
      name: "nebius-api-key",
      description: "Nebius Token Factory API key (store it as a repository secret).",
      required: true,
      default: null,
    });
    expect(spec.inputs.find((i) => i.name === "tavily-api-key")).toMatchObject({ required: false, default: "" });
    expect(spec.inputs.find((i) => i.name === "fail-on-broken")).toMatchObject({ required: false, default: "true" });
    expect(spec.outputs).toEqual([{ name: "verdict", description: "CONSERVED, BROKEN or INCONCLUSIVE." }]);
    expect(spec.steps[0]).toBe("actions/setup-python@v5");
    expect(spec.steps.at(-1)).toBe("Gate on the verdict");
    expect(spec.command).toBe('python -m noether check --pr "$PR_URL" --runner contree --out runs $flags');
    expect(spec.artifact).toBe("noether-proof-bundle");
  });

  it("handles CRLF and quoted values, and ignores nested step keys", () => {
    const yml = [
      "inputs:",
      "  a:",
      '    description: "quoted: yes"',
      "    required: false",
      '    default: "1"',
      "outputs:",
      "  out:",
      "    description: plain",
      "runs:",
      "  steps:",
      "    - name: One",
      "      uses: x/y@v1",
      "    - uses: z/w@v2",
      "      run: python -m noether check --pr u",
      "    - uses: actions/upload-artifact@v4",
      "      with:",
      "        name: kept",
    ].join("\r\n");
    const spec = parseAction(yml);
    expect(spec.inputs).toEqual([{ name: "a", description: "quoted: yes", required: false, default: "1" }]);
    expect(spec.outputs).toEqual([{ name: "out", description: "plain" }]);
    expect(spec.steps).toEqual(["One", "z/w@v2", "actions/upload-artifact@v4"]);
    expect(spec.command).toBe("python -m noether check --pr u");
    expect(spec.artifact).toBe("kept");
  });

  it("fails loudly when the shape it reads is gone", () => {
    expect(() => parseAction("name: x\n")).toThrow(/action.yml/);
  });
});

describe("workflowSecrets", () => {
  it("pairs each secret in the example workflow with its input", () => {
    expect(workflowSecrets(read("src", "content", "noether.yml"))).toEqual([
      { input: "nebius-api-key", secret: "NEBIUS_API_KEY" },
      { input: "nebius-project-id", secret: "NEBIUS_PROJECT_ID" },
    ]);
  });
});

describe("python constants", () => {
  it("reads the run caps from pipeline.py", () => {
    const caps = parseCaps(read("py", "noether", "pipeline.py"));
    expect(caps).toMatchObject({ max_invariants: expect.any(Number), max_probes: expect.any(Number), max_run_tokens: expect.any(Number), fix: true });
    expect(parseCaps("@dataclass\nclass Caps:\n    max_run_tokens: int = 250_000\n    fix: bool = False\n\nx = 1\n")).toEqual({
      max_run_tokens: 250000,
      fix: false,
    });
    expect(() => parseCaps("x = 1")).toThrow();
  });

  it("reads the exit codes from cli.py and the image from runner.py", () => {
    expect(parseExitCodes(read("py", "noether", "cli.py"))).toEqual({ CONSERVED: 0, BROKEN: 1, INCONCLUSIVE: 2 });
    expect(pyString(read("py", "noether", "runner.py"), "NODE_IMAGE")).toMatch(/^docker\.io\/library\/node:/);
    expect(() => pyString("A = 1", "A")).toThrow();
  });
});

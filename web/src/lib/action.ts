// The /action page is read off the files the Action runs, at build time: action.yml (copied into
// src/content by `npm run sync:noether`) and the vendored package in web/py/noether. Each reader throws when
// the shape it expects is gone, so a change to those files fails the build instead of leaving the page wrong.

export interface ActionInput {
  name: string;
  description: string;
  required: boolean;
  default: string | null;
}

export interface ActionOutput {
  name: string;
  description: string;
}

export interface ActionSpec {
  inputs: ActionInput[];
  outputs: ActionOutput[];
  /** Each step's name, or what it uses when it has none, in run order. */
  steps: string[];
  /** The noether command line the check step runs. */
  command: string;
  /** Name of the uploaded proof bundle artifact. */
  artifact: string;
}

const unquote = (value: string) => (value.startsWith('"') ? (JSON.parse(value) as string) : value);

// shortcut: reads only the block YAML action.yml is written in (two-space indents, one-line values); a real
// YAML parser if the file ever needs flow maps or multi-line descriptions.
export function parseAction(yml: string): ActionSpec {
  const fields: Record<"inputs" | "outputs", Record<string, Record<string, string>>> = { inputs: {}, outputs: {} };
  const steps: string[] = [];
  let section = "";
  let entry: Record<string, string> | null = null;
  for (const line of yml.split(/\r?\n/)) {
    const top = /^([\w-]+):/.exec(line);
    if (top) {
      section = top[1];
      entry = null;
      continue;
    }
    if (section === "inputs" || section === "outputs") {
      const name = /^ {2}([\w-]+):\s*$/.exec(line);
      const field = /^ {4}([\w-]+):\s*(.*?)\s*$/.exec(line);
      if (name) fields[section][name[1]] = entry = {};
      else if (field && entry) entry[field[1]] = unquote(field[2]);
    } else if (section === "runs") {
      const step = /^ {4}- (?:name|uses): (.+)$/.exec(line);
      if (step) steps.push(step[1].trim());
    }
  }

  const inputs = Object.entries(fields.inputs).map(([name, f]) => ({
    name,
    description: f.description ?? "",
    required: f.required === "true",
    default: f.default ?? null,
  }));
  const outputs = Object.entries(fields.outputs).map(([name, f]) => ({ name, description: f.description ?? "" }));
  const command = /python -m noether check .*/.exec(yml)?.[0].trim();
  const artifact = /uses: actions\/upload-artifact@\S+\s+with:\s+name: (\S+)/.exec(yml)?.[1];
  if (!inputs.length || !outputs.length || !steps.length || !command || !artifact) {
    throw new Error("action.yml no longer has the inputs, outputs, steps, check command and artifact this page reads");
  }
  return { inputs, outputs, steps, command, artifact };
}

/** Which repository secret the example workflow hands to which input. */
export function workflowSecrets(workflow: string): { input: string; secret: string }[] {
  return [...workflow.matchAll(/([\w-]+): \$\{\{ secrets\.(\w+) \}\}/g)].map(([, input, secret]) => ({ input, secret }));
}

/** Defaults of the `Caps` dataclass in noether/pipeline.py, e.g. { max_invariants: 12, fix: true }. */
export function parseCaps(py: string): Record<string, number | boolean> {
  const body = /^class Caps:\n((?: {4}.*\n)+)/m.exec(py.replace(/\r\n/g, "\n"))?.[1];
  if (!body) throw new Error("noether/pipeline.py has no Caps dataclass");
  const caps: Record<string, number | boolean> = {};
  for (const [, name, type, value] of body.matchAll(/^ {4}(\w+): (int|bool) = ([\w]+)/gm)) {
    caps[name] = type === "bool" ? value === "True" : Number(value.replace(/_/g, ""));
  }
  return caps;
}

/** `EXIT_CODES` in noether/cli.py: verdict -> process exit code. */
export function parseExitCodes(py: string): Record<string, number> {
  const literal = /^EXIT_CODES = (\{[^}]*\})/m.exec(py)?.[1];
  if (!literal) throw new Error("noether/cli.py has no EXIT_CODES");
  return JSON.parse(literal) as Record<string, number>;
}

/** A module-level string constant, e.g. NODE_IMAGE in noether/runner.py. */
export function pyString(py: string, name: string): string {
  const value = new RegExp(`^${name} = "([^"]*)"`, "m").exec(py)?.[1];
  if (value === undefined) throw new Error(`no string constant ${name}`);
  return value;
}

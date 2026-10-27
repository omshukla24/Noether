import { readFileSync } from "node:fs";
import path from "node:path";

// The head build's physics.js, read at build time so the source panel shows the file as it is.
export const HEAD_PHYSICS = readFileSync(path.join(process.cwd(), "src/hopper/head/physics.js"), "utf8");

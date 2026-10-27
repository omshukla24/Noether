import { readFileSync } from "node:fs";
import { join } from "node:path";
import { ImageResponse } from "next/og";
import { RUN } from "@/lib/run";

export const alt = "Noether: a sealed proof of what a pull request changed, and what it did not announce.";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

// Colours come from the design tokens file, so the card cannot drift from the site.
function tokens(): Record<string, string> {
  const css = readFileSync(join(process.cwd(), "src", "styles", "tokens.css"), "utf8");
  return Object.fromEntries([...css.matchAll(/--([\w-]+):\s*(#[0-9A-Fa-f]{6})/g)].map((m) => [m[1], m[2]]));
}

async function googleFont(family: string, weight: number, italic: boolean, text: string): Promise<ArrayBuffer | null> {
  "use cache";
  try {
    const axis = italic ? `ital,wght@1,${weight}` : `wght@${weight}`;
    const css = await (await fetch(`https://fonts.googleapis.com/css2?family=${family}:${axis}&text=${encodeURIComponent(text)}`)).text();
    const url = css.match(/src: url\((.+?)\) format\('(?:opentype|truetype)'\)/)?.[1];
    return url ? await (await fetch(url)).arrayBuffer() : null;
  } catch {
    return null;
  }
}

export default async function OpenGraphImage() {
  const t = tokens();
  const brk = RUN.breaks[0];
  const where = `${brk.file}:${brk.line}`;
  const hash = `${RUN.sha256.slice(0, 16)}...`;
  const word = RUN.verdict;
  const [serif, mono] = await Promise.all([
    googleFont("STIX+Two+Text", 500, false, `${word}${RUN.pr.title}`),
    googleFont("IBM+Plex+Mono", 400, false, `${where}${hash}NOETHER SEALED RUN sha256 BASE HEAD ·`),
  ]);
  const fonts = [
    ...(serif ? [{ name: "Stix", data: serif, weight: 500 as const, style: "normal" as const }] : []),
    ...(mono ? [{ name: "Plex", data: mono, weight: 400 as const, style: "normal" as const }] : []),
  ];
  const lines = RUN.invariants.filter((i) => i.base === "pass");
  const verdictColour = word === "BROKEN" ? t.broken : word === "CONSERVED" ? t.accent : t.ink;

  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", background: t.ground, padding: 64, fontFamily: "Plex" }}>
        <div style={{ display: "flex", flexDirection: "column", justifyContent: "space-between", width: 640 }}>
          <div style={{ display: "flex", color: t.muted, fontSize: 22, letterSpacing: 3 }}>NOETHER · SEALED RUN</div>
          <div style={{ display: "flex", flexDirection: "column" }}>
            <div style={{ display: "flex", fontFamily: "Stix", fontSize: 150, lineHeight: 1, color: verdictColour, letterSpacing: -4 }}>{word}</div>
            <div style={{ display: "flex", fontFamily: "Stix", fontSize: 34, lineHeight: 1.2, color: t.ink, marginTop: 28 }}>{RUN.pr.title}</div>
            <div style={{ display: "flex", fontSize: 28, color: t["broken-ink"], marginTop: 24 }}>{where}</div>
          </div>
          <div style={{ display: "flex", color: t.muted, fontSize: 20 }}>sha256 {hash}</div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", flexGrow: 1, marginLeft: 48, borderLeft: `2px solid ${t.line}`, paddingLeft: 48 }}>
          <div style={{ display: "flex", justifyContent: "space-between", width: 340, color: t.muted, fontSize: 18, letterSpacing: 3, marginBottom: 28 }}>
            <span>BASE</span>
            <span>HEAD</span>
          </div>
          {lines.map((inv) => {
            const flipped = inv.kind === "silent";
            return (
              <div key={inv.name} style={{ display: "flex", flexDirection: "column", marginBottom: 30 }}>
                <div style={{ display: "flex", height: 0, borderTop: `4px solid ${t.accent}`, width: 340 }} />
                <div
                  style={{
                    display: "flex",
                    height: 0,
                    marginTop: 8,
                    width: flipped ? 290 : 340,
                    marginLeft: flipped ? 50 : 0,
                    borderTop: flipped ? `4px dashed ${t.broken}` : `4px solid ${t.accent}`,
                    opacity: flipped ? 1 : 0.5,
                  }}
                />
              </div>
            );
          })}
        </div>
      </div>
    ),
    { ...size, fonts },
  );
}

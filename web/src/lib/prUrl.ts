// The same rule as noether/live.py: https, github.com, /owner/repo/pull/N and nothing else.
const PR = /^https:\/\/github\.com\/([A-Za-z0-9][A-Za-z0-9-]{0,38})\/([A-Za-z0-9._-]{1,100})\/pull\/([1-9][0-9]{0,8})\/?$/;

export interface PullRef {
  owner: string;
  repo: string;
  number: number;
}

export function parsePullUrl(raw: string): PullRef | null {
  const text = raw.trim();
  if (text.length > 200) return null;
  const m = PR.exec(text);
  if (!m || m[2] === "." || m[2] === ".." || m[2].endsWith(".git")) return null;
  return { owner: m[1], repo: m[2], number: Number(m[3]) };
}

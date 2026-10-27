import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { RemoteRun } from "@/components/run/RemoteRun";
import { RunView } from "@/components/run/RunView";
import { LIVE_RUN_ID, listRunIds, loadRun } from "@/lib/runs";

export function generateStaticParams() {
  return listRunIds().map((id) => ({ id }));
}

const clip = (text: string, max: number) => (text.length <= max ? text : `${text.slice(0, max - 1).trimEnd()}…`);

export async function generateMetadata({ params }: PageProps<"/runs/[id]">): Promise<Metadata> {
  const { id } = await params;
  const bundle = loadRun(id);
  const canonical = `/runs/${id}`;
  if (!bundle) {
    return {
      title: "Sealed run",
      description: "A sealed Noether proof bundle: the pinned checks, what flipped on the head, the judge's call and the re-proved fix, with its sha256 verified in your browser.",
      alternates: { canonical },
      robots: { index: false },
    };
  }
  return {
    title: `${bundle.verdict}: ${clip(bundle.pr.title, 60)}`,
    description: clip(`Sealed proof for ${bundle.repo}. ${bundle.verdict}. ${bundle.reason}`, 155),
    alternates: { canonical },
  };
}

// Ids built into the site render here at build time; any other id is looked up in the API by the browser.
export default async function RunPage({ params }: PageProps<"/runs/[id]">) {
  const { id } = await params;
  const bundle = loadRun(id);
  if (bundle) return <RunView bundle={bundle} />;
  if (!LIVE_RUN_ID.test(id)) notFound();
  return <RemoteRun id={id} />;
}

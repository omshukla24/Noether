import type { Metadata } from "next";
import Link from "next/link";
import { Block, PlainPage } from "@/components/plain/PlainPage";

export const metadata: Metadata = {
  title: "FAQ",
  description:
    "Which pull requests Noether can check, how long a run takes, what the verdicts mean, what a verdict cannot promise, and how to check a seal yourself.",
  alternates: { canonical: "/faq" },
};

export default function FaqPage() {
  return (
    <PlainPage
      kicker="FAQ"
      title="Questions a reviewer asks first."
      updated="30 October 2026"
      lede="Short answers, taken from what the service does today."
    >
      <Block n={1} title="Which pull requests can I check?">
        <p>Public GitHub pull requests of Node.js projects. Noether installs the repository&apos;s dependencies with npm in a Node 24 sandbox and runs checks with <code>node --test</code>. A private repository is refused, and a project without a package.json cannot be run.</p>
      </Block>

      <Block n={2} title="How long does a run take, and what does it cost me?">
        <p>About a minute for a small pull request. A run is stopped after 270 seconds. It is free; to keep the cost bounded, one address may start 3 live runs per hour and the service accepts a fixed number per day. The replay of the sealed Hopper run is a real earlier run and never counts against that.</p>
      </Block>

      <Block n={3} title="What do the verdicts mean?">
        <ul>
          <li><strong>BROKEN</strong>: a behaviour that held on the base commit fails on the head, and the pull request does not announce the change.</li>
          <li><strong>CONSERVED</strong>: every pinned behaviour still holds on the head.</li>
          <li><strong>INCONCLUSIVE</strong>: nothing could be pinned, or the run could not finish. The reason is always given and nothing is claimed.</li>
        </ul>
      </Block>

      <Block n={4} title="Can a CONSERVED verdict be wrong?">
        <p>Yes. Only behaviours that were pinned, and green twice on the base, are compared, and a language model writes the checks. A break nobody pinned stays invisible, and two runs of the same pull request can pin different checks. The <Link href="/evals">benchmark</Link> lists the catches, the misses and the false alarms.</p>
      </Block>

      <Block n={5} title="What is a seal, and how do I check one?">
        <p>Each finished run is stored as one JSON bundle with its sha256. Every <Link href="/runs/hopper">run page</Link> re-hashes the bundle in your browser and compares it with the recorded hash. Download the JSON from the same page to hash it yourself.</p>
      </Block>

      <Block n={6} title="Who sees my code?">
        <p>For a live run, GitHub, Nebius (models and sandbox) and the server that hosts the site. The <Link href="/privacy">privacy page</Link> lists each one and what it receives.</p>
      </Block>

      <Block n={7} title="Can I run it on my own repository?">
        <p>Yes, as a GitHub Action with two Nebius secrets. The <Link href="/action">Action page</Link> has the workflow file, every input and output, and when it fails a job.</p>
      </Block>
    </PlainPage>
  );
}

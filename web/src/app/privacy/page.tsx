import type { Metadata } from "next";
import { Block, PlainPage, plain } from "@/components/plain/PlainPage";

export const metadata: Metadata = {
  title: "Privacy",
  description:
    "What Noether stores when you check a pull request, who sees the code, how long it is kept, and why this site sets no cookies and runs no trackers.",
  alternates: { canonical: "/privacy" },
};

export default function PrivacyPage() {
  return (
    <PlainPage
      kicker="Privacy"
      title="What is kept, and who sees it."
      updated="30 October 2026"
      lede="Noether reads a public pull request, runs its code in a sandbox and seals the result. This page says what that touches, written from how the service actually works."
    >
      <Block n={1} title="Cookies and trackers">
        <p>This site sets no cookies, loads no analytics and runs no trackers. It keeps nothing about you in your browser: the cockpit and the run pages store no settings, and no consent banner is shown because there is nothing to consent to.</p>
        <p>Fonts are served from this site. The pages are hosted on Amazon Web Services (EC2), which, as the host, processes ordinary request logs (address, user agent, time) to deliver and protect the site.</p>
      </Block>

      <Block n={2} title="What a live run stores">
        <p>Checking a pull request seals one proof bundle and stores it as <code>runs/&lt;id&gt;.json</code> on the server&apos;s disk. It holds the pull request URL and title, the repository and the two commit hashes, the intent Nemotron read, every pinned check with its code and result, the judge&apos;s reasons, the located line and the proposed fix, the sandbox snapshot ids, the model calls with their token counts, the run&apos;s timeline and the sha256 seal.</p>
        <p>Anyone who has the link to a run can open it. Bundles are kept until the repository owner removes them; there is no automatic expiry yet. To have a run removed, open an issue on the project repository with its id.</p>
        <p>The replay of the sealed Hopper run sends nothing anywhere: it reads a file that ships with the site.</p>
      </Block>

      <Block n={3} title="Limits and your address">
        <p>To cap cost, the API allows a few live runs per hour from one address and a fixed number per day overall. It counts them in a small file per day in the same store. The file holds a salted hash of the address and the time of each run, never the address itself.</p>
      </Block>

      <Block n={4} title="Who sees the pull request code">
        <p>Only public repositories are read; a private one is refused. For a live run, the code of the pull request goes to these services, and only to them:</p>
        <table className={plain.table}>
          <thead><tr><th scope="col">Service</th><th scope="col">What it receives</th></tr></thead>
          <tbody>
            <tr><td>GitHub</td><td>Requests for the pull request, its changed files and the neighbouring files, read through the public API.</td></tr>
            <tr><td>Nebius Token Factory</td><td>The pull request text, its diff and the relevant source, sent to the Nemotron models that read intent, write the pinned checks, judge flips and propose the fix.</td></tr>
            <tr><td>Nebius Sandboxes</td><td>The repository at the base and head commits. Its code, and the pinned checks, run inside an isolated sandbox that also installs the repository&apos;s dependencies from their package registry.</td></tr>
            <tr><td>Amazon Web Services</td><td>Hosting of the site and the API (EC2), and the server&apos;s disk for the stored bundles and the daily counters.</td></tr>
            <tr><td>Tavily</td><td>Only when a pull request bumps a dependency and a search key is set: the package name and its two versions, to find its changelog.</td></tr>
          </tbody>
        </table>
        <p>Do not point Noether at a pull request whose code you do not want those services to read.</p>
      </Block>

      <Block n={5} title="Who is responsible">
        <p>Noether is a project by Om Shukla. Questions and removal requests go through the project repository on GitHub. This policy follows the laws of India.</p>
      </Block>
    </PlainPage>
  );
}

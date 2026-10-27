import type { Metadata } from "next";
import { Block, PlainPage } from "@/components/plain/PlainPage";

export const metadata: Metadata = {
  title: "Terms",
  description:
    "The terms for using Noether: public repositories only, what a verdict does and does not promise, limits on live runs, liability, and governing law in India.",
  alternates: { canonical: "/terms" },
};

export default function TermsPage() {
  return (
    <PlainPage
      kicker="Terms"
      title="What a verdict promises, and what it does not."
      updated="27 October 2026"
      lede="By using Noether you agree to these terms. They are short because the service is small and free."
    >
      <Block n={1} title="The service">
        <p>Noether checks one public GitHub pull request at a time. It pins how the code behaved before the change, runs those checks again after it in a sandbox, and reports what flipped. It is free: there are no orders, payments or refunds.</p>
      </Block>

      <Block n={2} title="What you may submit">
        <p>Only pull requests of public repositories, and only code you are allowed to run and to have analysed by the services listed in the privacy page. Do not submit pull requests meant to attack the sandbox, to exhaust the limits, or to extract anything other than a verdict. Runs that do so may be stopped without notice.</p>
      </Block>

      <Block n={3} title="What a verdict means">
        <p>CONSERVED means that every behaviour Noether pinned held on the head commit. It is not a guarantee that nothing else changed: only behaviours that were pinned and green twice on the base are compared, and the pinned checks are written by a language model.</p>
        <p>BROKEN means a pinned behaviour held on the base, failed on the head, and the judge found the pull request did not announce it. INCONCLUSIVE means the run could not finish, for example because a limit was reached, and nothing is claimed either way. A proposed fix is shown only when the sandbox re-proved it, and you remain responsible for reviewing it before it is merged.</p>
        <p>Models can be wrong, and runs are not deterministic: two runs of the same pull request may pin different checks.</p>
      </Block>

      <Block n={4} title="Limits">
        <p>A live run is stopped after 270 seconds, and the number of runs per address per hour and in total per day is capped. When a limit is reached the service says so and seals nothing.</p>
      </Block>

      <Block n={5} title="Availability and changes">
        <p>The service is provided as it is, without a promise that it will be available, accurate or free of errors. It may change or stop at any time, and these terms may be updated here; the date above shows the latest change.</p>
      </Block>

      <Block n={6} title="Liability">
        <p>To the extent the law allows, the author is not liable for loss arising from using Noether or relying on a verdict, including a break it did not find. The source code is released under the licence in the project repository.</p>
      </Block>

      <Block n={7} title="Governing law">
        <p>These terms are governed by the laws of India, and disputes are for the courts of India.</p>
      </Block>
    </PlainPage>
  );
}

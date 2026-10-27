import { Collapse } from "@/components/home/Collapse";
import { Darkroom } from "@/components/home/Darkroom";
import { Hero } from "@/components/home/Hero";
import { Judge } from "@/components/home/Judge";
import { PrCard } from "@/components/home/PrCard";
import { Preloader } from "@/components/home/Preloader";
import { Reprove } from "@/components/home/Reprove";
import { Route } from "@/components/home/Route";
import { Seal } from "@/components/home/Seal";
import { Slit } from "@/components/home/Slit";
import { StoryMotion } from "@/components/home/StoryMotion";
import { collapseLines, droppedLines } from "@/lib/collapse";
import { darkroomPlates } from "@/lib/darkroom";
import { COYOTE_FRAMES, TERMINAL_SPEED } from "@/hopper/fixed/physics.js";
import { HEAD_PHYSICS } from "@/lib/headSource";
import { judgeCase } from "@/lib/judge";
import { RUN, RUN_INTENDED } from "@/lib/run";
import { parseDiff, sliceAround } from "@/lib/story";

const SOURCE_RADIUS = 6;

// The home page tells one sealed run in order: observe, pin, expose, measure, judge, re-prove, route, seal.
export default function Home() {
  const lines = collapseLines(RUN);
  const dropped = droppedLines(RUN, lines);
  const { plates, seconds } = darkroomPlates(RUN);
  const found = RUN.breaks[0];
  const cases = [
    judgeCase(RUN_INTENDED, "intended", "20261027-025352-edb700.json"),
    judgeCase(RUN, "silent", "hopper.json"),
  ].filter((c) => c !== null);

  return (
    <>
      <Preloader />
      <Hero ownSuitePassed={RUN.own_suite.base?.passed ?? 0} />
      <PrCard />
      <Slit lines={lines.length} />
      <Darkroom plates={plates} seconds={seconds} />
      <Collapse
        lines={lines}
        dropped={dropped}
        source={sliceAround(HEAD_PHYSICS, found.line, SOURCE_RADIUS)}
        file={found.file}
        breakLine={found.line}
        why={found.why}
        baseSha={RUN.base.sha.slice(0, 7)}
        headSha={RUN.head.sha.slice(0, 7)}
        verdict={RUN.verdict}
      />
      <Judge cases={cases} announced={RUN.intent?.intended_changes ?? []} />
      <Reprove
        diff={parseDiff(found.fix!.diff)}
        file={found.fix!.file}
        line={found.line}
        invariant={found.invariant}
        greenOthers={RUN.invariants.filter((i) => i.name !== found.invariant && i.head === "pass").length}
        suitePassed={RUN.own_suite.head?.passed ?? 0}
        kept={{ coyote: COYOTE_FRAMES, terminal: TERMINAL_SPEED }}
      />
      <Route />
      <Seal />
      <StoryMotion />
    </>
  );
}

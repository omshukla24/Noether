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
import { RUN } from "@/lib/run";

// The home page tells one sealed run in order: observe, pin, expose, measure, judge, re-prove, route, seal.
export default function Home() {
  return (
    <>
      <Preloader />
      <Hero ownSuitePassed={RUN.own_suite.base?.passed ?? 0} />
      <PrCard />
      <Slit />
      <Darkroom />
      <Collapse />
      <Judge />
      <Reprove />
      <Route />
      <Seal />
    </>
  );
}

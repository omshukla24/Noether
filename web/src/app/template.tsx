import { ViewTransition } from "react";

// A template remounts on every navigation, so enter and exit fire here: the old page closes to the slit
// and the next one opens out of it. Styles live in globals.css under "page slit".
export default function Template({ children }: { children: React.ReactNode }) {
  return (
    <ViewTransition enter="slit" exit="slit" default="none">
      {children}
    </ViewTransition>
  );
}

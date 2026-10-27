import type { Metadata } from "next";
import { EmmyRoute } from "@/components/Emmy";

export const metadata: Metadata = {
  title: "1915",
  description: "To every differentiable symmetry, a conserved quantity.",
  robots: { index: false },
  alternates: { canonical: "/1915" },
};

export default function Page1915() {
  return <EmmyRoute />;
}

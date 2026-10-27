import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, Libre_Franklin, STIX_Two_Text } from "next/font/google";
import { SmoothScroll } from "@/components/SmoothScroll";
import { Nav } from "@/components/Nav";
import { Footer } from "@/components/Footer";
import { Emmy } from "@/components/Emmy";
import "../styles/tokens.css";
import "./globals.css";

const display = STIX_Two_Text({
  variable: "--nf-display",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  style: ["normal", "italic"],
  display: "swap",
});

const body = Libre_Franklin({
  variable: "--nf-body",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
});

const mono = IBM_Plex_Mono({
  variable: "--nf-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
  display: "swap",
});

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: "Noether: proof that a pull request changed only what it says", template: "%s · Noether" },
  description:
    "Noether pins how your code behaves before a pull request, re-runs it after in a Nebius sandbox, and shows the one behaviour change nobody announced, with a re-proved fix.",
  alternates: { canonical: "/" },
  openGraph: { type: "website", siteName: "Noether", url: "/" },
  twitter: { card: "summary_large_image" },
};

export const viewport: Viewport = { themeColor: "#F5F3ED" };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable} ${mono.variable}`}>
      <body>
        <a className="skip" href="#main">Skip to content</a>
        <SmoothScroll />
        <Nav />
        <main id="main">{children}</main>
        <Footer />
        <Emmy />
      </body>
    </html>
  );
}

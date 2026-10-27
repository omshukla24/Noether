import type { MetadataRoute } from "next";
import { listRunIds } from "@/lib/runs";
import { SITE_URL } from "@/lib/site";

// Every real route, as an absolute URL: the pages, and each sealed run that ships with the site.
export default function sitemap(): MetadataRoute.Sitemap {
  const pages = ["/", "/check", "/privacy", "/terms"];
  return [...pages, ...listRunIds().map((id) => `/runs/${id}`)].map((path) => ({
    url: `${SITE_URL}${path === "/" ? "" : path}`,
  }));
}

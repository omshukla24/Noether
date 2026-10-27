import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  // The three stylesheets are 15 KB in all: inlining them removes the CSS request round trip from first paint.
  experimental: { inlineCss: true },
};

export default nextConfig;

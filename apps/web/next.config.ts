import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Phase 39: a minimal, self-contained server bundle
  // (.next/standalone) for the Docker image — copies in only the
  // production node_modules a build actually traced as used, instead
  // of the whole node_modules tree.
  output: "standalone",
};

export default nextConfig;

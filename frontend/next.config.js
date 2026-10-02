/** @type {import('next').NextConfig} */
const nextConfig = {
  // Keep concurrent dev/test servers from overwriting each other's output.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  ...(process.env.NEXT_DIST_DIR === ".next-playwright"
    ? { typescript: { tsconfigPath: "tsconfig.playwright.json" } }
    : {}),
  // Retain more App Router entries in dev so revisiting routes doesn't force
  // another compile after the default five-route buffer has been displaced.
  onDemandEntries: {
    maxInactiveAge: 10 * 60 * 1000,
    pagesBufferLength: 32,
  },
  experimental: {
    optimizePackageImports: ["framer-motion", "lucide-react"],
  },
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;

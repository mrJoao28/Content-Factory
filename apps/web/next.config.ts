import type { NextConfig } from "next";
import path from "node:path";
const config: NextConfig = { devIndicators: false, poweredByHeader: false, outputFileTracingRoot: path.resolve(process.cwd()), turbopack: { root: path.resolve(process.cwd()) }, experimental: { cpus: 1 } };
export default config;

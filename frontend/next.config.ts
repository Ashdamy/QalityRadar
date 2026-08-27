import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Este proyecto vive anidado dentro de otra carpeta que tiene su propio
  // package-lock.json. Sin fijar la raiz, Turbopack la infiere hacia arriba
  // y avisa de que ignora ese lockfile ajeno.
  turbopack: {
    root: path.resolve(__dirname),
  },
};

export default nextConfig;

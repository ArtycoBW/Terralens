import { copyFile, mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// Next.js must serve the v6 worker together with its relative shared module.
// https://maplibre.org/maplibre-gl-js/docs/#installation
const packageRoot = dirname(
  createRequire(import.meta.url).resolve("maplibre-gl/package.json"),
);
const destination = fileURLToPath(
  new URL("../public/maplibre/", import.meta.url),
);
await mkdir(destination, { recursive: true });
for (const file of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"]) {
  await copyFile(join(packageRoot, "dist", file), join(destination, file));
}
await copyFile(
  join(packageRoot, "LICENSE.txt"),
  join(destination, "LICENSE.txt"),
);

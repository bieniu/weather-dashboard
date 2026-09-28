// Copies the browser bundles of the runtime dependencies from node_modules into
// frontend/vendor/, so the page serves them same-origin (CSP script-src 'self',
// service-worker precache, no CDN at runtime). Dependabot bumps package.json;
// `npm run vendor` refreshes the copies and `npm run vendor:check` (CI and
// pre-commit) fails when the copies are stale.
import { copyFileSync, existsSync, mkdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const targetDir = join(root, "frontend", "vendor");

const BUNDLES = [
  ["chart.js/dist/chart.umd.min.js", "chart.umd.min.js"],
  [
    "chartjs-adapter-date-fns/dist/chartjs-adapter-date-fns.bundle.min.js",
    "chartjs-adapter-date-fns.bundle.min.js",
  ],
];

const check = process.argv.includes("--check");
let stale = 0;
let missing = 0;

for (const [source, target] of BUNDLES) {
  const from = join(root, "node_modules", source);
  const to = join(targetDir, target);
  if (!existsSync(from)) {
    console.error(`missing ${from} (run "npm ci" first)`);
    missing += 1;
    continue;
  }
  if (check) {
    if (!existsSync(to) || !readFileSync(from).equals(readFileSync(to))) {
      console.error(`stale: frontend/vendor/${target} (run "npm run vendor")`);
      stale += 1;
    }
    continue;
  }
  mkdirSync(targetDir, { recursive: true });
  copyFileSync(from, to);
  console.log(`vendored frontend/vendor/${target}`);
}

if (missing > 0) process.exit(2);
if (stale > 0) process.exit(1);

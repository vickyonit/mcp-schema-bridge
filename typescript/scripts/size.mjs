// Fails if the minified + gzipped ESM bundle exceeds the budget (rules data included).
import { buildSync } from "esbuild";
import { gzipSync } from "node:zlib";

const BUDGET = 30 * 1024;
const out = buildSync({ entryPoints: ["dist/index.js"], bundle: true, minify: true, platform: "node", format: "esm", write: false, external: ["node:crypto"] });
const size = gzipSync(out.outputFiles[0].contents).length;
console.log(`min+gz: ${(size / 1024).toFixed(1)} KB (budget ${BUDGET / 1024} KB)`);
if (size > BUDGET) process.exit(1);

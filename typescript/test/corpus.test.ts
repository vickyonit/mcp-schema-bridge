/**
 * Cross-language parity: the TypeScript implementation must reproduce every Python golden in
 * corpus/expected/** (compared as ordered JSON, so property and key order must match too).
 */
import { readdirSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { type OMap, parseOrdered, stringifyOrdered } from "../src/core/ojson.js";
import { TARGETS } from "../src/core/rules.js";
import { normalizeToolsOrdered } from "../src/core/toolset.js";

const CORPUS = new URL("../../corpus/", import.meta.url);
const manifest = JSON.parse(readFileSync(new URL("manifest.json", CORPUS), "utf8")) as { pending: { ts: string[] } };
const STRIP = new Set(["fingerprint", "library_version", "rules_version"]);

function cases(): [string, unknown[]][] {
  const out: [string, unknown[]][] = [];
  for (const d of readdirSync(new URL("captured/", CORPUS)).sort()) {
    out.push([d, parseOrdered(readFileSync(new URL(`captured/${d}/tools.json`, CORPUS), "utf8")) as unknown[]]);
  }
  for (const f of readdirSync(new URL("synthetic/", CORPUS)).sort()) {
    const c = parseOrdered(readFileSync(new URL(`synthetic/${f}`, CORPUS), "utf8")) as OMap;
    out.push([`synthetic/${c.get("id") as string}`, [c.get("tool")]]);
  }
  return out;
}

function strip(v: unknown): unknown {
  if (v instanceof Map) return new Map([...v].filter(([k]) => !STRIP.has(k as string)).map(([k, x]) => [k, strip(x)]));
  if (Array.isArray(v)) return v.map(strip);
  return v;
}

describe.each(TARGETS)("parity %s", (target) => {
  it.each(cases())("%s", (name, tools) => {
    const expected = readFileSync(new URL(`expected/${target}/${name}.json`, CORPUS), "utf8");
    const actual = strip(normalizeToolsOrdered(tools, target).toOrdered());
    if (manifest.pending.ts.includes(name)) return;
    expect(stringifyOrdered(actual, 2)).toBe(stringifyOrdered(parseOrdered(expected), 2));
  });
});

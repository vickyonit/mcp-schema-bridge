/**
 * Cross-language parity: the TypeScript implementation must reproduce every Python golden in
 * corpus/expected/** (compared as ordered JSON, so property and key order must match too),
 * including toolset budgets, options and argument round-trips.
 */
import { readdirSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { type OMap, parseOrdered, stringifyOrdered, toPlain } from "../src/core/ojson.js";
import { type NormalizeOptions } from "../src/core/options.js";
import { type Repair, denormalizeArgs } from "../src/core/reverse.js";
import { TARGETS } from "../src/core/rules.js";
import { normalizeToolsOrdered } from "../src/core/toolset.js";

const CORPUS = new URL("../../corpus/", import.meta.url);
const manifest = JSON.parse(readFileSync(new URL("manifest.json", CORPUS), "utf8")) as { pending: { ts: string[] } };
const STRIP = new Set(["fingerprint", "library_version", "rules_version"]);

interface Case { name: string; tools: unknown[]; meta: OMap | null }

function cases(): Case[] {
  const out: Case[] = [];
  for (const d of readdirSync(new URL("captured/", CORPUS)).sort()) {
    out.push({ name: d, tools: parseOrdered(readFileSync(new URL(`captured/${d}/tools.json`, CORPUS), "utf8")) as unknown[], meta: null });
  }
  for (const f of readdirSync(new URL("synthetic/", CORPUS)).sort()) {
    const c = parseOrdered(readFileSync(new URL(`synthetic/${f}`, CORPUS), "utf8")) as OMap;
    out.push({ name: `synthetic/${c.get("id") as string}`, tools: (c.get("tools") as unknown[] | undefined) ?? [c.get("tool")], meta: c });
  }
  return out;
}

const camel = (s: string): string => s.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase());
function options(meta: OMap | null): NormalizeOptions {
  const raw = (meta?.get("options") as OMap | undefined) ?? new Map<string, unknown>();
  const o: Record<string, unknown> = {};
  for (const [k, v] of raw) {
    o[camel(k)] = v instanceof Map ? Object.fromEntries([...(v as OMap)].map(([a, b]) => [camel(a), b])) : v;
  }
  return o as NormalizeOptions;
}

function strip(v: unknown): unknown {
  if (v instanceof Map) return new Map([...v].filter(([k]) => !STRIP.has(k as string)).map(([k, x]) => [k, strip(x)]));
  if (Array.isArray(v)) return v.map(strip);
  return v;
}

describe.each(TARGETS)("parity %s", (target) => {
  it.each(cases().map((c) => [c.name, c] as const))("%s", (name, c) => {
    if (manifest.pending.ts.includes(name)) return;
    const expected = readFileSync(new URL(`expected/${target}/${name}.json`, CORPUS), "utf8");
    const res = normalizeToolsOrdered(c.tools, target, options(c.meta));
    const actual = strip(res.toOrdered()) as OMap;
    const args = c.meta?.get("args") as unknown[] | undefined;
    if (args) {
      const repairs = ((c.meta?.get("repairs") as string[] | undefined) ?? []) as Repair[];
      actual.set("args", res.tools.flatMap((t) => args.map((a) => {
        const d = denormalizeArgs(t, toPlain(a), { repairs });
        return new Map<string, unknown>([["tool", t.name], ["input", a], ["output", d.args], ["warnings", d.warnings.map((w) => w.rule)]]);
      })));
    }
    expect(stringifyOrdered(actual, 2)).toBe(stringifyOrdered(parseOrdered(expected), 2));
  });
});

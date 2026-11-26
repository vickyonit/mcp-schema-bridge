/** Differential fuzzing against the Python reference (input produced by scripts/parity_fuzz.py). */
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { type OMap, parseOrdered, stringifyOrdered } from "../src/core/ojson.js";
import { type Target } from "../src/core/rules.js";
import { normalizeToolsOrdered } from "../src/core/toolset.js";

const file = process.env.MSB_FUZZ_FILE;
const STRIP = new Set(["fingerprint", "library_version", "rules_version"]);
const strip = (v: unknown): unknown =>
  v instanceof Map ? new Map([...v].filter(([k]) => !STRIP.has(k as string)).map(([k, x]) => [k, strip(x)])) : Array.isArray(v) ? v.map(strip) : v;

describe.skipIf(!file)("differential fuzz vs Python", () => {
  const lines = file ? readFileSync(file, "utf8").split("\n").filter(Boolean) : [];
  it.each(lines.map((l, i) => [i, l] as const))("case %i", (_i, line) => {
    const c = parseOrdered(line) as OMap;
    const expected = c.get("expected") as OMap;
    let actual: unknown;
    try {
      actual = strip(normalizeToolsOrdered([c.get("tool")], c.get("target") as Target).toOrdered());
    } catch (e) {
      actual = new Map([["error", (e as Error).constructor.name]]);
    }
    expect(stringifyOrdered(actual, 2)).toBe(stringifyOrdered(strip(expected), 2));
  });
});

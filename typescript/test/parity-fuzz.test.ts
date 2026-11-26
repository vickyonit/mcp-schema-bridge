/** Differential fuzzing against the Python reference (input produced by scripts/parity_fuzz.py). */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { type OMap, parseOrdered, stringifyOrdered } from "../src/core/ojson.js";
import { type Target } from "../src/core/rules.js";
import { normalizeToolsOrdered } from "../src/core/toolset.js";

// Committed seeded cases (corpus/fuzz/cases.jsonl) plus, optionally, a fresh file from scripts/parity_fuzz.py.
const files = [fileURLToPath(new URL("../../corpus/fuzz/cases.jsonl", import.meta.url)), ...(process.env.MSB_FUZZ_FILE ? [process.env.MSB_FUZZ_FILE] : [])];
const STRIP = new Set(["fingerprint", "library_version", "rules_version"]);
const strip = (v: unknown): unknown =>
  v instanceof Map ? new Map([...v].filter(([k]) => !STRIP.has(k as string)).map(([k, x]) => [k, strip(x)])) : Array.isArray(v) ? v.map(strip) : v;

describe("differential fuzz vs Python", () => {
  const lines = files.flatMap((f) => readFileSync(f, "utf8").split("\n").filter(Boolean));
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

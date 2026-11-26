import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { scan } from "../src/core/regex-scan.js";

const vectors = JSON.parse(readFileSync(new URL("../../spec/regex-vectors.json", import.meta.url), "utf8")) as {
  vectors: { pattern: string; features: string[] }[];
};

describe("regex feature scanner (shared vectors)", () => {
  it.each(vectors.vectors)("$pattern", ({ pattern, features }) => {
    expect([...scan(pattern)].sort()).toEqual([...features].sort());
  });
});

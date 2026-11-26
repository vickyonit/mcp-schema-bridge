import { describe, expect, it } from "vitest";
import {
  denormalizeArgs, normalizeSchema, normalizeTools, ReverseMismatchError, toSdkPayload, TARGETS,
} from "../src/index.js";

const TOOLS = [
  { name: "search", description: "Search", inputSchema: { type: "object", properties: { q: { type: "string", minLength: 1 }, limit: { type: "integer" } }, required: ["q"] } },
  { name: "meta", inputSchema: { type: "object", properties: { m: { type: "object" } }, required: ["m"] } },
];

describe("public API", () => {
  it("normalizes plain objects and round-trips args (openai-strict)", () => {
    const res = normalizeTools(TOOLS, "openai-strict");
    expect(res.tools.map((t) => t.name)).toEqual(["search"]);
    expect(res.rejected.map((r) => r.name)).toEqual(["meta"]);
    const search = res.tools[0]!;
    expect(search.schema.required).toEqual(["q", "limit"]);
    expect(denormalizeArgs(search, { q: "x", limit: null }).args).toEqual({ q: "x" });
  });

  it("wraps non-object roots and unwraps args", () => {
    const r = normalizeSchema({ type: "string" }, "gemini-json");
    expect(r.schema).toEqual({ type: "object", properties: { value: { type: "string" } }, required: ["value"] });
    expect(denormalizeArgs(r, { value: "x" }).args).toBe("x");
    const w = denormalizeArgs(r, { nope: 1 });
    expect(w.warnings.map((x) => x.rule)).toEqual(["core/reverse-unrecognized-shape"]);
    expect(() => denormalizeArgs(r, { nope: 1 }, { strict: true })).toThrow(/value/);
  });

  it("rejects a mismatched reverse map", () => {
    const r = normalizeSchema({ type: "string" }, "openai");
    expect(() => denormalizeArgs({ ...r, fingerprint: "0".repeat(64) }, {})).toThrow(ReverseMismatchError);
  });

  it("enum case repair is opt-in and unambiguous only", () => {
    const r = normalizeSchema({ type: "object", properties: { k: { type: "string", enum: ["A", "B"] } } }, "openai");
    expect(denormalizeArgs(r, { k: "a" }).args).toEqual({ k: "a" });
    expect(denormalizeArgs(r, { k: "a" }, { repairs: ["enum_case_insensitive"] }).args).toEqual({ k: "A" });
  });

  it("builds SDK payloads with explicit strict", () => {
    const res = normalizeTools(TOOLS.slice(0, 1), "openai-strict");
    expect(toSdkPayload(res, "openai-responses")[0]).toMatchObject({ type: "function", name: "search", strict: true });
    const g = toSdkPayload(normalizeTools(TOOLS.slice(0, 1), "gemini-json"), "genai")[0] as { functionDeclarations: { parametersJsonSchema: unknown }[] };
    expect(g.functionDeclarations[0]!.parametersJsonSchema).toBeTypeOf("object");
    expect(() => toSdkPayload(res, "genai")).toThrow(/provider/);
  });

  it("fingerprints match the Python implementation (same version, rules, input)", () => {
    for (const t of TARGETS) expect(normalizeSchema({ type: "object" }, t).fingerprint).toMatch(/^[0-9a-f]{64}$/);
    // computed by the Python package for the same input/target/version/rules
    expect(normalizeSchema({ type: "object", properties: { a: { type: "string" } } }, "openai-strict").fingerprint).toBe("895482e7d51895eaee9769f7c217cdb58cf0c732e5f648404e395f3dbe601676");
  });
});

describe("ToolsetResult helpers", () => {
  it("get() and summary() match the Python output", () => {
    const res = normalizeTools(TOOLS, "openai-strict");
    expect(res.get("search")?.name).toBe("search");
    expect(res.get("meta")).toBeUndefined();
    const text = res.summary();
    expect(text.startsWith("openai-strict: 1 tool(s) ok, 1 rejected")).toBe(true);
    expect(text).toContain("meta  /properties/m");
    expect(text).toContain("fix: ");
  });
});

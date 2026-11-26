import { describe, expect, it } from "vitest";
import {
  denormalizeArgs, InvalidInputError, LimitExceededError, normalizeSchema, normalizeTools, Report, UnsupportedSchemaError,
} from "../src/index.js";
import { checkValue } from "../src/core/parse.js";
import { pyRepr, pySorted, pyStr } from "../src/core/pyfmt.js";
import { keywordStatus, loadRules } from "../src/core/rules.js";
import { urldefrag, urljoin } from "../src/core/url.js";

describe("python formatting parity", () => {
  it("repr escapes like CPython", () => {
    expect(pyRepr("a\u0001b\\c\t")).toBe("'a\\x01b\\\\c\\t'");
    expect(pyRepr("both ' and \"")).toBe("'both \\' and \"'");
    expect(pyRepr("\u0085")).toBe("'\\x85'");
  });
  it("str of numbers and constants", () => {
    expect(pyStr(0.5)).toBe("0.5");
    expect(pyStr(1e-7)).toBe("1e-07");
    expect(pyStr(null)).toBe("None");
    expect(pyStr(false)).toBe("False");
    expect(pyStr("x")).toBe("x");
  });
  it("sorted uses code points", () => {
    expect(pySorted(["דּ", "😀", "a"])).toEqual(["a", "דּ", "😀"]);
  });
});

describe("url helpers follow urllib", () => {
  it("joins hierarchical and opaque bases", () => {
    expect(urljoin("https://example.com/a/root.json", "item.json")).toBe("https://example.com/a/item.json");
    expect(urljoin("urn:x:root", "item.json")).toBe("item.json");
    expect(urljoin("urn:x:root", "")).toBe("urn:x:root");
    expect(urljoin("", "a")).toBe("a");
    expect(urljoin("https://a/b", "https://[bad")).toBe("https://[bad");
    expect(urldefrag("a#b#c")).toEqual(["a", "b#c"]);
  });
});

describe("input validation", () => {
  it("rejects non-JSON values and bad keys", () => {
    expect(() => checkValue({ f: () => 1 })).toThrow(/not a JSON value/);
    expect(() => checkValue(new Map<unknown, unknown>([[1, 2]]))).toThrow(/keys must be strings/);
    expect(() => checkValue({ "\udc00": 1 })).toThrow(/surrogate/);
    expect(() => checkValue({ a: "😀" })).not.toThrow();
    expect(() => checkValue({ a: { b: 1 } }, { maxNodes: 100, maxDepth: 1 })).toThrow(LimitExceededError);
  });
  it("rejects unsupported dialects and non-string $schema", () => {
    expect(() => normalizeSchema({ $schema: "http://json-schema.org/draft-04/schema#" }, "openai")).toThrow(InvalidInputError);
    expect(() => normalizeSchema({ $schema: 4 }, "openai")).toThrow(/must be a string/);
  });
  it("rejects malformed tools", () => {
    expect(() => normalizeTools([{ name: "x" }], "openai")).toThrow(/inputSchema/);
    expect(() => normalizeTools([{ inputSchema: {} }], "openai")).toThrow(/name/);
    expect(() => normalizeTools([5], "openai")).toThrow(/tool must be an object/);
    expect(() => normalizeTools([{ name: "x", description: 3, inputSchema: {} }], "openai")).toThrow(/description/);
  });
});

describe("options", () => {
  it("raise mode throws on the first fatal entry", () => {
    expect(() => normalizeSchema({ type: "object", properties: { a: { $ref: "https://x/y.json" } } }, "openai", { onUnsupported: "raise" }))
      .toThrow(UnsupportedSchemaError);
  });
  it("output node cap", () => {
    const s = {
      type: "object",
      properties: Object.fromEntries([0, 1, 2, 3, 4].map((i) => [`p${i}`, { $ref: "#/$defs/D", description: "d" }])),
      required: ["p0", "p1", "p2", "p3", "p4"],
      $defs: { D: { type: "object", properties: Object.fromEntries([...Array(10).keys()].map((j) => [`k${j}`, { type: "string" }])), required: [...Array(10).keys()].map((j) => `k${j}`) } },
    };
    expect(() => normalizeSchema(s, "openai-strict", { maxNodes: 80 })).toThrow(/output exceeds max_nodes/);
  });
  it("strict fallback on a single schema", () => {
    const r = normalizeSchema({ type: "object", properties: { m: { type: "object" } }, required: ["m"] }, "anthropic-strict", { strictFallback: true });
    expect([r.target, r.strict]).toEqual(["anthropic", false]);
    expect(r.report.entries.some((e) => e.action === "fallback")).toBe(true);
  });
});

describe("reverse walker", () => {
  const s = {
    type: "object",
    properties: {
      u: { anyOf: [{ $ref: "#/$defs/A" }, { type: "object", properties: { kind: { const: "b" }, z: { type: "integer" } }, required: ["kind"] }] },
      t: { type: "array", prefixItems: [{ type: "object", properties: { x: { type: "string" } } }], items: { type: "object", properties: { y: { type: "string" } } } },
      m: { type: "object", additionalProperties: { type: "object", properties: { q: { type: "integer" } } } },
    },
    $defs: { A: { type: "object", properties: { kind: { const: "a" }, n: { type: "string" } }, required: ["kind", "n"] } },
  };
  it("selects union branches structurally and walks arrays and maps", () => {
    const r = normalizeSchema(s, "openai");
    const args = { u: { kind: "b", z: 1 }, t: [{ x: "1" }, { y: "2" }], m: { k: { q: 1 } } };
    expect(denormalizeArgs(r, args).args).toEqual(args);
    expect(denormalizeArgs(r, undefined).args).toBeUndefined();
  });
  it("removes injected nulls inside matched union branches (openai-strict)", () => {
    const r = normalizeSchema(
      { type: "object", properties: { u: { anyOf: [{ type: "object", properties: { a: { type: "string" }, o: { type: "integer" } }, required: ["a"] }, { type: "string" }] } }, required: ["u"] },
      "openai-strict",
    );
    expect(denormalizeArgs(r, { u: { a: "x", o: null } }).args).toEqual({ u: { a: "x" } });
    expect(denormalizeArgs(r, { u: "s" }).args).toEqual({ u: "s" });
  });
  it("returns args unchanged for rejected schemas", () => {
    const r = normalizeSchema({ type: "object", properties: { a: { $ref: "https://x" } } }, "openai");
    expect(r.schema).toBeNull();
    expect(denormalizeArgs(r, { a: 1 }).args).toEqual({ a: 1 });
  });
  it("rejects a mismatched rules version", () => {
    const r = normalizeSchema({ type: "string" }, "openai");
    expect(() => denormalizeArgs({ ...r, reverse: { ...r.reverse, rulesVersion: "1999.01.01" } }, {})).toThrow(/rules_version/);
  });
});

describe("misc", () => {
  it("report helpers", () => {
    expect(new Report("openai").maxSeverity()).toBeNull();
    expect(new Report("openai").hasFatal()).toBe(false);
    const r = normalizeSchema({ type: "object", properties: { a: { $ref: "https://x" } } }, "openai");
    expect(r.report.hasFatal()).toBe(true);
    expect(r.report.maxSeverity()).toBe("fatal");
  });
  it("rules lookups", () => {
    expect(keywordStatus(loadRules("openai-strict"), "nope")).toBeUndefined();
    expect(keywordStatus(loadRules("openai-strict"), "minimum")).toBe("enforced");
  });
  it("boolean subschemas on strict targets", () => {
    const r = normalizeSchema({ type: "object", properties: { a: { type: "array", items: { type: "string" }, contains: true, not: false } }, required: ["a"] }, "openai-strict");
    expect(r.schema).not.toBeNull();
  });
  it("toJSON gives plain objects", () => {
    const res = normalizeTools([{ name: "a", inputSchema: { type: "object" } }], "openai");
    expect(JSON.parse(JSON.stringify(res))).toMatchObject({ target: "openai", tools: [{ name: "a" }] });
  });
});

import { describe, expect, it } from "vitest";
import { InvalidInputError, LimitExceededError } from "../src/core/errors.js";
import { checkValue } from "../src/core/parse.js";
import { pyQuote, pyRepr, pyStr } from "../src/core/pyfmt.js";
import { Report, type ReportEntry, severityAtLeast } from "../src/core/report.js";
import { keywordKind, loadRules, RULES_VERSION, TARGETS } from "../src/core/rules.js";

const entry = (o: Partial<ReportEntry>): ReportEntry => ({
  rule: "core/x", tid: "T1", tool: null, sourcePath: "", targetPath: null, instancePath: null,
  keyword: "k", action: "dropped", severity: "info", original: null, hinted: false, message: "", ...o,
});

describe("report", () => {
  it("orders severities", () => {
    expect(severityAtLeast("lossy", "reversible")).toBe(true);
    expect(severityAtLeast("info", "lossy")).toBe(false);
  });
  it("sorts totally with UTF-16 ordering", () => {
    const r = new Report("openai", [
      entry({ sourcePath: "/b" }), entry({ tool: "z", sourcePath: "/a" }), entry({ sourcePath: "/דּ" }),
      entry({ sourcePath: "/😀" }), entry({ sourcePath: "/a", keyword: null }),
    ]);
    expect(r.sorted().map((e) => [e.tool, e.sourcePath, e.keyword])).toEqual([
      [null, "/a", null], [null, "/b", "k"], [null, "/😀", "k"], [null, "/דּ", "k"], ["z", "/a", "k"],
    ]);
    expect(r.maxSeverity()).toBe("info");
  });
});

describe("parse", () => {
  it("rejects unsafe integers, non-finite numbers and lone surrogates", () => {
    expect(() => checkValue({ maximum: 2 ** 60 })).toThrow(InvalidInputError);
    expect(() => checkValue({ maximum: Number.POSITIVE_INFINITY })).toThrow(/finite/);
    expect(() => checkValue({ d: "\ud800" })).toThrow(/surrogate/);
  });
  it("enforces limits", () => {
    expect(() => checkValue({ enum: Array.from({ length: 50 }, (_, i) => i) }, { maxNodes: 20, maxDepth: 10 })).toThrow(LimitExceededError);
  });
  it("copies into ordered Maps", () => {
    const v = checkValue({ a: { b: 1 } }) as Map<string, Map<string, number>>;
    expect(v.get("a")!.get("b")).toBe(1);
  });
});

describe("rules", () => {
  it("loads every target", () => {
    for (const t of TARGETS) expect(loadRules(t).target).toBe(t);
    expect(() => loadRules("nope")).toThrow(/unknown target/);
    expect(RULES_VERSION).toMatch(/^\d{4}\.\d{2}\.\d{2}$/);
    expect(keywordKind("x-mcp-header")).toBe("annotation");
    expect(keywordKind("minimum")).toBe("validation");
  });
});

describe("python formatting helpers", () => {
  it("repr", () => {
    expect(pyRepr("a")).toBe("'a'");
    expect(pyRepr("it's")).toBe('"it\'s"');
    expect(pyRepr("a\nb")).toBe("'a\\nb'");
    expect(pyStr(5)).toBe("5");
    expect(pyStr(true)).toBe("True");
    expect(pyQuote("/$defs/a/b%c ü")).toBe("/$defs/a/b%25c%20%C3%BC");
  });
});

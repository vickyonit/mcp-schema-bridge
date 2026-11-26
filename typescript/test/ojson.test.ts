import { describe, expect, it } from "vitest";
import { fromPlain, parseOrdered, stringifyOrdered, toPlain } from "../src/core/ojson.js";

describe("order-preserving JSON", () => {
  it("keeps integer-like keys in document order", () => {
    const v = parseOrdered('{"b":1,"10":2,"2":3,"a":{"z":[1,{"1":null}]}}');
    expect(v).toBeInstanceOf(Map);
    expect([...(v as Map<string, unknown>).keys()]).toEqual(["b", "10", "2", "a"]);
    expect(stringifyOrdered(v)).toBe('{"b":1,"10":2,"2":3,"a":{"z":[1,{"1":null}]}}');
  });

  it("rejects duplicate keys, NaN and malformed input", () => {
    expect(() => parseOrdered('{"a":1,"a":2}')).toThrow(/duplicate key 'a'/);
    expect(() => parseOrdered("NaN")).toThrow(/invalid JSON/);
    expect(() => parseOrdered("{")).toThrow(/invalid JSON/);
  });

  it("round-trips strings with escapes and unicode", () => {
    const s = '{"k":"a\\"b\\\\c\\n\\u0001€😀"}';
    expect(stringifyOrdered(parseOrdered(s))).toBe(s.replace("\\u0001", "\\u0001"));
  });

  it("converts plain objects and back", () => {
    const m = fromPlain({ a: [1, { b: true }] });
    expect(toPlain(m)).toEqual({ a: [1, { b: true }] });
  });

  it("pretty-prints like Python json.dumps(indent=2, ensure_ascii=False)", () => {
    expect(stringifyOrdered(parseOrdered('{"a":[1,{}],"b":{},"c":[]}'), 2)).toBe(
      '{\n  "a": [\n    1,\n    {}\n  ],\n  "b": {},\n  "c": []\n}',
    );
  });
});

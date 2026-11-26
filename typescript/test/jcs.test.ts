import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { canonicalize } from "../src/core/jcs.js";

describe("RFC 8785 JCS", () => {
  it("matches the RFC 8785 §3.2.4 example", () => {
    const source =
      '{"numbers": [333333333.33333329, 1E30, 4.50, 2e-3, 0.000000000000000000000000001],' +
      '"string": "\\u20ac$\\u000F\\u000aA\'\\u0042\\u0022\\u005c\\\\\\"\\/",' +
      '"literals": [null, true, false]}';
    const expected =
      '{"literals":[null,true,false],"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27],' +
      '"string":"€$\\u000f\\nA\'B\\"\\\\\\\\\\"/"}';
    expect(canonicalize(JSON.parse(source))).toBe(expected);
  });

  it("sorts keys by UTF-16 code units", () => {
    const m = new Map<string, number>([["€", 1], ["\r", 2], ["\ufb33", 3], ["1", 4], ["😀", 5], ["\u0080", 6], ["ö", 7]]);
    expect(canonicalize(m)).toBe('{"\\r":2,"1":4,"\u0080":6,"ö":7,"€":1,"😀":5,"\ufb33":3}');
  });

  it.each([
    [0, "0"], [-0, "0"], [5e-324, "5e-324"], [1.7976931348623157e308, "1.7976931348623157e+308"],
    [9007199254740991, "9007199254740991"], [1e21, "1e+21"], [1e20, "100000000000000000000"],
    [0.000001, "0.000001"], [1e-7, "1e-7"], [4.35, "4.35"], [-1.5, "-1.5"], [123e-20, "1.23e-18"],
  ])("formats %d as %s", (v, s) => {
    expect(canonicalize(v)).toBe(s);
  });

  it("rejects non-finite numbers and lone surrogates", () => {
    expect(() => canonicalize(Number.NaN)).toThrow(/finite/);
    expect(() => canonicalize("\ud800")).toThrow(/surrogate/);
  });

  it("escapes control characters", () => {
    expect(canonicalize("\b\t\n\f\r\u0000\u001f")).toBe('"\\b\\t\\n\\f\\r\\u0000\\u001f"');
  });

  it("round-trips any finite double", () => {
    fc.assert(
      fc.property(fc.double({ noNaN: true, noDefaultInfinity: true }), (x) => {
        expect(Number(canonicalize(x))).toBe(Object.is(x, -0) ? 0 : x);
      }),
    );
  });
});

import { describe, expect, it } from "vitest";
import { decodeFragment, escapeToken, join, split, unescapeToken } from "../src/core/pointer.js";

describe("RFC 6901 pointers", () => {
  it.each([["a/b", "a~1b"], ["a~b", "a~0b"], ["~/", "~0~1"], ["~1", "~01"], ["", ""]])("escapes %s", (raw, esc) => {
    expect(escapeToken(raw)).toBe(esc);
    expect(unescapeToken(esc)).toBe(raw);
  });
  it("joins and splits", () => {
    const p = join("", "properties", "a/b", "items");
    expect(p).toBe("/properties/a~1b/items");
    expect(split(p)).toEqual(["properties", "a/b", "items"]);
    expect(split("")).toEqual([]);
    expect(() => split("x")).toThrow(/must start with/);
  });
  it("decodes fragments percent-first", () => {
    expect(decodeFragment("#/$defs/a%25b")).toEqual(["$defs", "a%b"]);
    expect(decodeFragment("#/definitions/x~1y")).toEqual(["definitions", "x/y"]);
    expect(decodeFragment("#")).toEqual([]);
    expect(decodeFragment("#/a%7E0b")).toEqual(["a~b"]);
  });
});

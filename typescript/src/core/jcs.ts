/** RFC 8785 JSON Canonicalization Scheme. Maps are serialized like objects. */

export const MAX_SAFE_INTEGER = 2 ** 53 - 1;

export function canonicalize(value: unknown): string {
  const out: string[] = [];
  write(value, out);
  return out.join("");
}

function write(value: unknown, out: string[]): void {
  if (value === null) out.push("null");
  else if (value === true) out.push("true");
  else if (value === false) out.push("false");
  else if (typeof value === "number") out.push(formatNumber(value));
  else if (typeof value === "string") out.push(quoteString(value));
  else if (Array.isArray(value)) {
    out.push("[");
    value.forEach((v: unknown, i) => {
      if (i) out.push(",");
      write(v, out);
    });
    out.push("]");
  } else if (value instanceof Map) {
    writeObject([...(value as Map<unknown, unknown>).entries()], out);
  } else if (typeof value === "object") {
    writeObject(Object.entries(value as Record<string, unknown>), out);
  } else {
    throw new TypeError(`not JSON-serializable: ${typeof value}`);
  }
}

function writeObject(entries: [unknown, unknown][], out: string[]): void {
  for (const [k] of entries) {
    if (typeof k !== "string") throw new TypeError("object keys must be strings");
  }
  const sorted = (entries as [string, unknown][]).sort(([a], [b]) => utf16Compare(a, b));
  out.push("{");
  sorted.forEach(([k, v], i) => {
    if (i) out.push(",");
    out.push(quoteString(k), ":");
    write(v, out);
  });
  out.push("}");
}

/** Compare by UTF-16 code units (RFC 8785 §3.2.3); JS relational string comparison does exactly this. */
export function utf16Compare(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

const SHORT: Record<number, string> = { 8: "\\b", 9: "\\t", 10: "\\n", 12: "\\f", 13: "\\r", 34: '\\"', 92: "\\\\" };

export function quoteString(s: string): string {
  let out = '"';
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdbff) {
      const n = s.charCodeAt(i + 1);
      if (!(n >= 0xdc00 && n <= 0xdfff)) throw new RangeError("lone surrogate code point in string is not valid I-JSON");
      out += s.slice(i, i + 2);
      i++;
      continue;
    }
    if (c >= 0xdc00 && c <= 0xdfff) throw new RangeError("lone surrogate code point in string is not valid I-JSON");
    const esc = SHORT[c];
    if (esc !== undefined) out += esc;
    else if (c < 0x20) out += "\\u" + c.toString(16).padStart(4, "0");
    else out += s[i];
  }
  return out + '"';
}

/** ECMAScript Number::toString is exactly the RFC 8785 number format. */
export function formatNumber(x: number): string {
  if (!Number.isFinite(x)) throw new RangeError("JSON numbers must be finite (NaN/Infinity are not allowed)");
  if (Object.is(x, -0)) return "0";
  return String(x);
}

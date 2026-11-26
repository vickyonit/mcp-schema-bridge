/**
 * Order-preserving JSON. JavaScript objects enumerate integer-like keys first, which would reorder
 * properties such as "10" and "2"; internally every JSON object is an insertion-ordered Map.
 */
import { formatNumber, quoteString } from "./jcs.js";

export type OMap = Map<string, unknown>;

export class JsonParseError extends Error {
  constructor(
    message: string,
    readonly pointer = "",
  ) {
    super(message);
  }
}

/** Strict parser: objects become Maps; duplicate keys and non-JSON tokens are errors. */
export function parseOrdered(text: string): unknown {
  let i = 0;
  const fail = (msg: string): never => {
    throw new JsonParseError(`invalid JSON: ${msg} at offset ${i}`);
  };
  const ws = () => {
    while (i < text.length && " \t\n\r".includes(text[i]!)) i++;
  };
  const value = (pointer: string): unknown => {
    ws();
    const c = text[i];
    if (c === "{") {
      i++;
      const m: OMap = new Map();
      ws();
      if (text[i] === "}") {
        i++;
        return m;
      }
      for (;;) {
        ws();
        if (text[i] !== '"') fail("expected string key");
        const k = str();
        if (m.has(k)) throw new JsonParseError(`duplicate key '${k}'`, pointer);
        ws();
        if (text[i] !== ":") fail("expected ':'");
        i++;
        m.set(k, value(`${pointer}/${k.replace(/~/g, "~0").replace(/\//g, "~1")}`));
        ws();
        if (text[i] === ",") {
          i++;
          continue;
        }
        if (text[i] === "}") {
          i++;
          return m;
        }
        fail("expected ',' or '}'");
      }
    }
    if (c === "[") {
      i++;
      const a: unknown[] = [];
      ws();
      if (text[i] === "]") {
        i++;
        return a;
      }
      for (;;) {
        a.push(value(`${pointer}/${a.length}`));
        ws();
        if (text[i] === ",") {
          i++;
          continue;
        }
        if (text[i] === "]") {
          i++;
          return a;
        }
        fail("expected ',' or ']'");
      }
    }
    if (c === '"') return str();
    if (text.startsWith("true", i)) return (i += 4), true;
    if (text.startsWith("false", i)) return (i += 5), false;
    if (text.startsWith("null", i)) return (i += 4), null;
    const m = /^-?(0|[1-9]\d*)(\.\d+)?([eE][+-]?\d+)?/.exec(text.slice(i));
    if (!m) return fail("unexpected token");
    i += m[0].length;
    return Number(m[0]);
  };
  const str = (): string => {
    const start = i;
    i++;
    let out = "";
    while (i < text.length) {
      const c = text[i]!;
      if (c === '"') {
        i++;
        return out;
      }
      if (c === "\\") {
        const e = text[i + 1];
        const simple: Record<string, string> = { '"': '"', "\\": "\\", "/": "/", b: "\b", f: "\f", n: "\n", r: "\r", t: "\t" };
        if (e !== undefined && e in simple) {
          out += simple[e];
          i += 2;
          continue;
        }
        if (e === "u" && /^[0-9a-fA-F]{4}$/.test(text.slice(i + 2, i + 6))) {
          out += String.fromCharCode(parseInt(text.slice(i + 2, i + 6), 16));
          i += 6;
          continue;
        }
        fail("bad escape");
      }
      if (c.charCodeAt(0) < 0x20) fail("control character in string");
      out += c;
      i++;
    }
    i = start;
    return fail("unterminated string");
  };
  const v = value("");
  ws();
  if (i !== text.length) fail("trailing data");
  return v;
}

/** Serialize preserving Map insertion order. ``indent`` mimics Python json.dumps(indent=n, ensure_ascii=False). */
export function stringifyOrdered(value: unknown, indent = 0): string {
  const nl = (d: number) => (indent ? "\n" + " ".repeat(indent * d) : "");
  const sep = indent ? ": " : ":";
  const go = (v: unknown, d: number): string => {
    if (v === null || v === undefined) return "null";
    if (v === true) return "true";
    if (v === false) return "false";
    if (typeof v === "number") return formatNumber(v);
    if (typeof v === "string") return quoteString(v);
    if (Array.isArray(v)) {
      if (!v.length) return "[]";
      return "[" + v.map((x) => nl(d + 1) + go(x, d + 1)).join(",") + nl(d) + "]";
    }
    const entries = v instanceof Map ? [...(v as OMap)] : Object.entries(v as Record<string, unknown>);
    if (!entries.length) return "{}";
    return "{" + entries.map(([k, x]) => nl(d + 1) + quoteString(k) + sep + go(x, d + 1)).join(",") + nl(d) + "}";
  };
  return go(value, 0);
}

export function fromPlain(v: unknown): unknown {
  if (Array.isArray(v)) return v.map(fromPlain);
  if (v instanceof Map) return new Map([...(v as OMap)].map(([k, x]) => [k, fromPlain(x)]));
  if (v !== null && typeof v === "object") return new Map(Object.entries(v).map(([k, x]) => [k, fromPlain(x)]));
  return v;
}

export function toPlain(v: unknown): unknown {
  if (Array.isArray(v)) return v.map(toPlain);
  if (v instanceof Map) {
    const o: Record<string, unknown> = {};
    for (const [k, x] of v as OMap) o[k] = toPlain(x);
    return o;
  }
  return v;
}

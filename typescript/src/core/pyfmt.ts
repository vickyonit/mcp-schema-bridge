/** Python-compatible formatting helpers so report messages are byte-identical across languages. */

/** Python repr() of a str. */
export function pyRepr(s: string): string {
  const quote = s.includes("'") && !s.includes('"') ? '"' : "'";
  let out = quote;
  for (const ch of s) {
    const cp = ch.codePointAt(0)!;
    if (ch === "\\") out += "\\\\";
    else if (ch === quote) out += "\\" + quote;
    else if (ch === "\n") out += "\\n";
    else if (ch === "\r") out += "\\r";
    else if (ch === "\t") out += "\\t";
    else if (cp < 0x20 || cp === 0x7f) out += "\\x" + cp.toString(16).padStart(2, "0");
    else if ((cp >= 0x80 && cp < 0xa0) || cp === 0xad) out += "\\x" + cp.toString(16).padStart(2, "0");
    else out += ch;
  }
  return out + quote;
}

/** Python str() of a JSON scalar (as used in f-strings). */
export function pyStr(v: unknown): string {
  if (v === null || v === undefined) return "None";
  if (v === true) return "True";
  if (v === false) return "False";
  if (typeof v === "number") {
    if (Number.isInteger(v)) return String(v);
    const s = String(v);
    return s.includes("e") ? s.replace(/e([+-])(\d)$/, "e$10$2") : s;
  }
  return String(v);
}

/** urllib.parse.quote(s, safe="/~!$&'()*+,;=:@") */
export function pyQuote(s: string): string {
  const safe = /[A-Za-z0-9_.\-~/!$&'()*+,;=:@]/;
  let out = "";
  for (const ch of s) {
    if (safe.test(ch)) out += ch;
    else for (const b of new TextEncoder().encode(ch)) out += "%" + b.toString(16).toUpperCase().padStart(2, "0");
  }
  return out;
}

/** Python sorted() for strings (code point order). */
export function pySorted(xs: Iterable<string>): string[] {
  return [...xs].sort((a, b) => {
    const A = [...a].map((c) => c.codePointAt(0)!);
    const B = [...b].map((c) => c.codePointAt(0)!);
    for (let i = 0; i < Math.min(A.length, B.length); i++) if (A[i] !== B[i]) return A[i]! - B[i]!;
    return A.length - B.length;
  });
}

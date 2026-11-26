/** Purely syntactic ECMA-262 regex feature scanner (never compiles patterns). */

export const LARGE_QUANTIFIER_THRESHOLD = 100;

export function scan(pattern: string): Set<string> {
  const found = new Set<string>();
  const n = pattern.length;
  let i = 0;
  let inClass = false;
  while (i < n) {
    const c = pattern[i]!;
    if (c === "\\" && i + 1 < n) {
      const nxt = pattern[i + 1]!;
      if (!inClass) {
        const namedRef = nxt === "k" && pattern[i + 2] === "<";
        if ("123456789".includes(nxt) || namedRef) found.add("backreference");
        else if (nxt === "b" || nxt === "B") found.add("word_boundary");
      }
      if ((nxt === "p" || nxt === "P") && pattern[i + 2] === "{") found.add("unicode_property");
      i += 2;
      continue;
    }
    if (inClass) {
      if (c === "]") inClass = false;
      i += 1;
      continue;
    }
    if (c === "[") {
      inClass = true;
      i += 1;
      continue;
    }
    if (c === "(" && pattern[i + 1] === "?") {
      const rest = pattern.slice(i + 2, i + 4);
      const first = rest.slice(0, 1);
      if (first === "=" || first === "!" || rest === "<=" || rest === "<!") found.add("lookaround");
      else if (first !== ":" && first !== "<" && first !== "") found.add("inline_flags");
      i += 2;
      continue;
    }
    if (c === "{") {
      const end = pattern.indexOf("}", i);
      if (end !== -1) {
        const parts = pattern.slice(i + 1, end).split(",");
        const numeric =
          parts.length <= 2 && /^\d+$/.test(parts[0]!) && parts.slice(1).every((p) => p === "" || /^\d+$/.test(p));
        if (numeric) {
          if (parts.filter((p) => p !== "").some((p) => Number(p) > LARGE_QUANTIFIER_THRESHOLD)) {
            found.add("large_quantifier");
          }
          i = end + 1;
          continue;
        }
      }
    }
    i += 1;
  }
  return found;
}

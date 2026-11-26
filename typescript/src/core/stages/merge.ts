/** Stage S3 / T7: merge allOf into a single schema (spec/allof-merge.md). Port of merge.py. */
import { type Ctx } from "../context.js";
import { canonicalize } from "../jcs.js";
import { type OMap } from "../ojson.js";
import { pyRepr } from "../pyfmt.js";
import { keywordKind } from "../rules.js";
import { copyTree, iterSubschemas, plainCopy, Seen, SNode, toOrdered } from "../tree.js";

const LOWER = new Set(["minimum", "exclusiveMinimum", "minLength", "minItems", "minProperties", "minContains"]);
const UPPER = new Set(["maximum", "exclusiveMaximum", "maxLength", "maxItems", "maxProperties", "maxContains"]);
const FIRST_WINS_LOSSY = new Set(["pattern", "multipleOf", "format"]);
const SINGLE_SUBSCHEMA_FIRST = new Set(["not", "if", "then", "else", "unevaluatedProperties", "unevaluatedItems", "contentSchema"]);
const SUBSCHEMA_MERGE = new Set(["items", "contains", "propertyNames"]);

const c = (v: unknown): string => canonicalize(v);
const uniq = <T>(xs: T[]): T[] => [...new Set(xs)];

export function mergeAllOf(root: SNode, ctx: Ctx): void {
  if (!ctx.rules.features.merge_allof) return;
  const seen = new Seen();
  for (const tree of [root, ...ctx.defs.values()]) visit(tree, ctx, seen, []);
}

function visit(node: SNode, ctx: Ctx, seen: Seen, stack: SNode[]): void {
  if (seen.has(node)) return;
  seen.add(node);
  for (const [, , child] of [...iterSubschemas(node)]) if (child instanceof SNode) visit(child, ctx, seen, stack);
  const branches = node.get("allOf");
  if (!Array.isArray(branches)) return;
  node.delete("allOf");
  ctx.add("core/allof-merged", "T7", { node, keyword: "allOf", action: "merged", severity: "info", message: "allOf merged into a single schema" });
  const contributors: SNode[] = [snapshot(node)];
  for (const b of branches as unknown[]) {
    if (b === true) continue;
    if (b === false) {
      ctx.add("core/allof-unsatisfiable", "T7", {
        node, keyword: "allOf", action: "rejected", severity: "fatal", message: "allOf contains false; schema is unsatisfiable",
      });
      continue;
    }
    const branch = resolvedCopy(b as SNode, ctx, [...stack, node]);
    if (branch === null) continue;
    visit(branch, ctx, new Seen(), stack);
    contributors.push(snapshot(branch));
    mergeInto(node, branch, ctx);
  }
  reportChanged(node, contributors, ctx);
}

function snapshot(n: SNode): SNode {
  const s = new SNode([...n].map(([k, v]) => [k, toOrdered(v)] as const), n.src);
  s.kwSrc = new Map(n.kwSrc);
  return s;
}

function resolvedCopy(b: SNode, ctx: Ctx, stack: SNode[]): SNode | null {
  if (b.ref === null) return b;
  const target = b.ref;
  if (stack.includes(target)) {
    ctx.add("core/allof-ref-cycle", "T7", {
      node: b, keyword: "$ref", action: "rejected", severity: "fatal", message: "allOf references itself; cannot be merged",
    });
    return null;
  }
  let inlined = copyTree(target);
  if (inlined.ref !== null) {
    const nested = resolvedCopy(inlined, ctx, [...stack, target]);
    if (nested === null) return null;
    inlined = nested;
  }
  const siblings = new SNode([...b].filter(([k]) => k !== "$ref"), b.src);
  if (siblings.size) mergeInto(inlined, siblings, ctx);
  if (inlined.has("allOf")) visit(inlined, ctx, new Seen(), [...stack, target]);
  ctx.add("core/allof-ref-inlined", "T7", {
    node: b, keyword: "$ref", action: "inlined", severity: "info", original: b.get("$ref"),
    message: "$ref inside allOf resolved before merging",
  });
  return inlined;
}

export function mergeInto(dst: SNode, src: SNode, ctx: Ctx): void {
  const sides = [closedNames(dst), closedNames(src)];
  dst.src = uniq([...dst.src, ...src.src]);
  if (src.ref !== null && dst.ref === null && !dst.has("$ref")) dst.ref = src.ref;
  for (const [kw, v] of src) {
    if (kw === "$ref") {
      if (!dst.has("$ref")) {
        dst.set("$ref", v);
        dst.ref = src.ref;
      } else if (dst.ref !== src.ref) {
        ctx.add("core/allof-two-refs", "T7", {
          node: dst, keyword: "$ref", action: "dropped", severity: "lossy", sourcePath: src.src[0] ?? "", original: v,
          message: "two different $ref in one allOf; second dropped",
        });
      }
      continue;
    }
    if (kw === "enum" || kw === "const") continue;
    if (!dst.has(kw)) {
      dst.set(kw, v instanceof SNode ? copyTree(v) : plainCopy(v));
      dst.kwSrc.set(kw, src.origins(kw));
      continue;
    }
    mergeKeyword(dst, src, kw, ctx);
    dst.kwSrc.set(kw, uniq([...dst.origins(kw), ...src.origins(kw)]));
  }
  if (src.has("enum") || src.has("const")) {
    if (dst.has("enum") || dst.has("const")) mergeEnumConst(dst, src, ctx);
    else {
      for (const kw of ["enum", "const"]) {
        if (src.has(kw)) {
          dst.set(kw, plainCopy(src.get(kw)));
          dst.kwSrc.set(kw, src.origins(kw));
        }
      }
    }
  }
  applyAdditionalProperties(dst, sides, ctx);
}

const types = (v: unknown): string[] => (typeof v === "string" ? [v] : [...(v as string[])]);

function mergeKeyword(dst: SNode, src: SNode, kw: string, ctx: Ctx): void {
  const a = dst.get(kw);
  const b = src.get(kw);
  const srcPath = src.src[0] ?? "";
  if (kw === "properties") {
    const pa = a as OMap;
    for (const [name, sb] of b as OMap) pa.set(name, pa.has(name) ? mergeSchemas(pa.get(name), sb, ctx) : copyTree(sb));
  } else if (kw === "required") {
    dst.set(kw, uniq([...(a as string[]), ...(b as string[])]));
  } else if (kw === "type") {
    const ta = types(a);
    const tb = types(b);
    const out = ta.filter((t) => tb.includes(t));
    if (ta.includes("integer") && tb.includes("number") && !out.includes("integer")) out.push("integer");
    if (ta.includes("number") && tb.includes("integer") && !out.includes("integer")) out.push("integer");
    if (!out.length) {
      ctx.add("core/allof-unsatisfiable", "T7", {
        node: dst, keyword: "type", action: "rejected", severity: "fatal", original: b, message: "allOf branches have disjoint types",
      });
      return;
    }
    dst.set(kw, out.length === 1 ? out[0] : out);
  } else if (LOWER.has(kw)) {
    dst.set(kw, (b as number) > (a as number) ? b : a);
  } else if (UPPER.has(kw)) {
    dst.set(kw, (b as number) < (a as number) ? b : a);
  } else if (kw === "uniqueItems") {
    dst.set(kw, Boolean(a) || Boolean(b));
  } else if (FIRST_WINS_LOSSY.has(kw)) {
    if (c(a) !== c(b)) {
      ctx.add(`core/allof-conflicting-${kw.toLowerCase()}`, "T7", {
        node: dst, keyword: kw, action: "dropped", severity: "lossy", sourcePath: srcPath, original: b, hint: true,
        message: `two different ${kw} values; kept the first`,
      });
    }
  } else if (SINGLE_SUBSCHEMA_FIRST.has(kw)) {
    if (c(a) !== c(b)) {
      ctx.add("core/allof-conflicting-subschema", "T7", {
        node: dst, keyword: kw, action: "dropped", severity: "lossy", sourcePath: srcPath, original: toOrdered(b),
        message: `${kw} in several allOf branches; kept the first`,
      });
    }
  } else if (SUBSCHEMA_MERGE.has(kw)) {
    dst.set(kw, mergeSchemas(a, b, ctx));
  } else if (kw === "prefixItems") {
    const la = a as unknown[];
    const lb = b as unknown[];
    const merged = la.slice(0, Math.min(la.length, lb.length)).map((x, i) => mergeSchemas(x, lb[i], ctx));
    merged.push(...(la.length > lb.length ? la.slice(lb.length) : lb.slice(la.length)).map((x) => copyTree(x)));
    dst.set(kw, merged);
  } else if (kw === "anyOf" || kw === "oneOf") {
    const la = a as unknown[];
    const lb = b as unknown[];
    if (la.length * lb.length > ctx.opts.maxNodes) {
      ctx.add("core/allof-distribution-too-large", "T7", {
        node: dst, keyword: kw, action: "rejected", severity: "fatal", message: "allOf of unions is too large to distribute",
      });
      return;
    }
    const product = unionProduct(la, lb, dst, ctx, "T7");
    if (!product.length) return;
    dst.set(kw, product);
  } else if (kw === "additionalProperties") {
    if (a === false || b === false) dst.set(kw, false);
    else if (a === true) dst.set(kw, copyTree(b));
    else if (b !== true) dst.set(kw, mergeSchemas(a, b, ctx));
  } else if (kw === "description") {
    if (a !== b) dst.set(kw, `${String(a)}\n\n${String(b)}`);
  } else if (kw === "dependentRequired") {
    const da = a as Map<string, string[]>;
    for (const [k, v] of b as Map<string, string[]>) da.set(k, uniq([...(da.get(k) ?? []), ...v]));
  } else if (kw === "dependentSchemas" || kw === "patternProperties") {
    const da = a as OMap;
    for (const [k, v] of b as OMap) da.set(k, da.has(k) ? mergeSchemas(da.get(k), v, ctx) : copyTree(v));
  } else if (c(a) !== c(b)) {
    const annotation = keywordKind(kw) === "annotation";
    ctx.add("core/allof-first-wins", "T7", {
      node: dst, keyword: kw, action: annotation ? "merged" : "dropped", severity: annotation ? "info" : "lossy",
      sourcePath: srcPath, original: toOrdered(b), message: `${kw} differs between allOf branches; kept the first`,
    });
  }
}

function mergeEnumConst(dst: SNode, src: SNode, ctx: Ctx): void {
  const side = (n: SNode): [string, unknown[], string[]] | null => {
    if (n.has("const")) return ["const", [n.get("const")], n.origins("const")];
    if (n.has("enum")) return ["enum", [...(n.get("enum") as unknown[])], n.origins("enum")];
    return null;
  };
  const sa = side(dst);
  const sb = side(src);
  if (sa === null || sb === null) return;
  const keysB = new Set(sb[1].map(c));
  const out = sa[1].filter((x) => keysB.has(c(x)));
  if (!out.length) {
    ctx.add("core/allof-unsatisfiable", "T7", {
      node: dst, keyword: sb[0], action: "rejected", severity: "fatal", message: "allOf enum/const values do not intersect",
    });
    return;
  }
  let finalKw: string;
  let finalVal: unknown[];
  if (sa[0] === "const" || sb[0] === "const") {
    dst.delete("enum");
    dst.set("const", out[0]);
    finalKw = "const";
    finalVal = [out[0]];
  } else {
    dst.set("enum", out);
    finalKw = "enum";
    finalVal = out;
  }
  dst.kwSrc.delete("enum");
  dst.kwSrc.delete("const");
  dst.kwSrc.set(finalKw, uniq([...sa[2], ...sb[2]]));
  for (const [kw, vals, origins] of [sa, sb]) {
    if (kw !== finalKw || c(vals) !== c(finalVal)) {
      for (const origin of origins) {
        ctx.add("core/allof-value-merged", "T7", {
          node: dst, keyword: kw, action: "merged", severity: "info", sourcePath: origin,
          original: kw === "const" ? vals[0] : vals, message: `${kw} intersected with other allOf branches`,
        });
      }
    }
  }
}

export function unionProduct(left: unknown[], right: unknown[], node: SNode, ctx: Ctx, tid: string): unknown[] {
  const out: unknown[] = [];
  const usedL = new Set<number>();
  const usedR = new Set<number>();
  left.forEach((a, i) => {
    right.forEach((b, j) => {
      const m = tryMerge(copyTree(a), b, ctx);
      if (m !== null) {
        out.push(m);
        usedL.add(i);
        usedR.add(j);
      }
    });
  });
  for (const [side, used] of [[left, usedL], [right, usedR]] as const) {
    side.forEach((branch, k) => {
      if (!used.has(k) && branch instanceof SNode) {
        for (const src of branch.src.length ? branch.src : [""]) {
          ctx.add("core/unsatisfiable-branch-removed", tid, {
            node, keyword: null, action: "narrowed", severity: "info", sourcePath: src,
            message: "a union branch that can never match was removed",
          });
        }
      }
    });
  }
  if (!out.length) {
    ctx.add("core/unsatisfiable-union", tid, {
      node, keyword: "anyOf", action: "rejected", severity: "fatal", message: "no union branch is satisfiable",
    });
  }
  return out;
}

export function tryMerge(a: unknown, b: unknown, ctx: Ctx): unknown {
  const sub = ctx.sub();
  const out = mergeSchemas(a, b, sub);
  if (sub.fatal || out === false) return null;
  ctx.entries.push(...sub.entries);
  return out;
}

export function mergeSchemas(a: unknown, b: unknown, ctx: Ctx): unknown {
  if (a === true) return copyTree(b);
  if (b === true) return a;
  if (a === false || b === false) return false;
  const snaps = [snapshot(a as SNode), snapshot(b as SNode)];
  const out = copyTree(a as SNode);
  mergeInto(out, b as SNode, ctx);
  reportChanged(out, snaps, ctx);
  return out;
}

function closedNames(n: SNode): Set<string> | null {
  if (n.get("additionalProperties") !== false) return null;
  return new Set([...((n.get("properties") as OMap | undefined) ?? new Map()).keys()]);
}

function applyAdditionalProperties(dst: SNode, sides: (Set<string> | null)[], ctx: Ctx): void {
  const props = dst.get("properties");
  if (!(props instanceof Map)) return;
  const closed = sides.filter((x): x is Set<string> => x !== null);
  if (!closed.length) return;
  const allow = closed.reduce((acc, names) => new Set([...acc].filter((x) => names.has(x))));
  const p = props as OMap;
  const required = new Set((dst.get("required") as string[] | undefined) ?? []);
  for (const name of [...p.keys()].filter((n) => !allow.has(n))) {
    if (required.has(name)) {
      ctx.add("core/allof-unsatisfiable", "T7", {
        node: dst, keyword: "required", action: "rejected", severity: "fatal", original: name,
        message: `property ${pyRepr(name)} is required but forbidden by additionalProperties: false`,
      });
      continue;
    }
    const removed = p.get(name);
    p.delete(name);
    ctx.add("core/allof-property-forbidden", "T7", {
      node: dst, keyword: null, action: "narrowed", severity: "info", original: name,
      sourcePath: removed instanceof SNode && removed.src.length ? removed.src[0]! : "",
      message: `property ${pyRepr(name)} removed: forbidden by additionalProperties: false in another branch`,
    });
  }
}

export function reportChanged(final: SNode, contributors: SNode[], ctx: Ctx): void {
  for (const src of contributors) {
    for (const [kw, v] of src) {
      if (keywordKind(kw) !== "validation" || !final.has(kw) || FIRST_WINS_LOSSY.has(kw) || kw === "required") continue;
      if (c(final.get(kw)) !== c(v)) {
        for (const origin of src.origins(kw)) {
          ctx.add("core/allof-value-merged", "T7", {
            node: final, keyword: kw, action: "merged", severity: "info", sourcePath: origin, original: v,
            message: `${kw} combined with other allOf branches`,
          });
        }
      }
    }
  }
}

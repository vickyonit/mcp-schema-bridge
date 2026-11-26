/** Stage S6: union shaping (T8, T5, const->enum, T4, T9). Port of unions.py. */
import { type Ctx } from "../context.js";
import { canonicalize } from "../jcs.js";
import { type OMap } from "../ojson.js";
import { keywordKind, keywordStatus } from "../rules.js";
import { copyTree, iterSubschemas, Seen, SNode, toOrdered } from "../tree.js";
import { unionProduct } from "./merge.js";

export const TYPE_KEYWORDS: Record<string, readonly string[]> = {
  string: ["minLength", "maxLength", "pattern", "format", "contentEncoding", "contentMediaType"],
  number: ["minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf"],
  integer: ["minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf"],
  array: ["items", "prefixItems", "minItems", "maxItems", "uniqueItems", "contains", "minContains", "maxContains", "unevaluatedItems"],
  object: ["properties", "required", "additionalProperties", "patternProperties", "propertyNames", "minProperties", "maxProperties", "dependentRequired", "dependentSchemas", "unevaluatedProperties"],
  boolean: [],
  null: [],
};

export function jsonType(v: unknown): string {
  if (v === null) return "null";
  if (typeof v === "boolean") return "boolean";
  if (typeof v === "number") return Number.isInteger(v) ? "integer" : "number";
  if (typeof v === "string") return "string";
  if (Array.isArray(v)) return "array";
  return "object";
}

export function unionsStage(root: SNode, ctx: Ctx): void {
  const seen = new Seen();
  for (const tree of [root, ...ctx.defs.values()]) visit(tree, ctx, seen);
}

function visit(node: SNode, ctx: Ctx, seen: Seen): void {
  if (seen.has(node)) return;
  seen.add(node);
  for (const [, , child] of [...iterSubschemas(node)]) if (child instanceof SNode) visit(child, ctx, seen);
  const f = ctx.rules.features;
  if (node.has("oneOf") && !f.oneof) t8(node, ctx);
  if (ctx.rules.strict || f.enum_values === "primitive") t5Type(node, ctx);
  constToEnum(node, ctx);
  if (!f.multi_type_arrays) t4(node, ctx);
  if (!f.anyof_validation_siblings && node.has("anyOf")) t9(node, ctx);
  for (const b of (node.get("anyOf") as unknown[] | undefined) ?? []) if (b instanceof SNode && !seen.has(b)) visit(b, ctx, seen);
}

// --- T8 ---------------------------------------------------------------------------------------

function typeSet(b: unknown): Set<string> | null {
  if (!(b instanceof SNode) || b.ref !== null) return null;
  const t = b.get("type");
  if (t === undefined) return b.has("const") ? new Set([jsonType(b.get("const"))]) : null;
  const s = new Set(typeof t === "string" ? [t] : (t as string[]));
  if (s.has("number")) s.add("integer");
  return s;
}

function values(b: unknown): Set<string> | null {
  if (!(b instanceof SNode)) return null;
  if (b.has("const")) return new Set([canonicalize(b.get("const"))]);
  if (b.has("enum")) return new Set((b.get("enum") as unknown[]).map((v) => canonicalize(v)));
  return null;
}

function pairwiseDisjoint(sets: (Set<string> | null)[]): boolean {
  if (sets.some((s) => s === null)) return false;
  const seen = new Set<string>();
  for (const s of sets as Set<string>[]) {
    for (const x of s) if (seen.has(x)) return false;
    for (const x of s) seen.add(x);
  }
  return true;
}

function discriminated(branches: unknown[]): boolean {
  if (!branches.every((b) => b instanceof SNode)) return false;
  let common: Set<string> | null = null;
  for (const b of branches as SNode[]) {
    const props = (b.get("properties") as OMap | undefined) ?? new Map<string, unknown>();
    const req = new Set((b.get("required") as string[] | undefined) ?? []);
    const keys = new Set([...props].filter(([k, v]) => req.has(k) && values(v) !== null).map(([k]) => k));
    common = common === null ? keys : new Set([...(common as Set<string>)].filter((k) => keys.has(k)));
  }
  for (const k of common ?? []) {
    if (pairwiseDisjoint((branches as SNode[]).map((b) => values((b.get("properties") as OMap).get(k))))) return true;
  }
  return false;
}

export function disjoint(branches: unknown[]): boolean {
  return pairwiseDisjoint(branches.map(typeSet)) || pairwiseDisjoint(branches.map(values)) || discriminated(branches);
}

function t8(node: SNode, ctx: Ctx): void {
  const origins = node.origins("oneOf");
  const branches = node.get("oneOf") as unknown[];
  node.delete("oneOf");
  node.kwSrc.delete("oneOf");
  const exclusive = disjoint(branches);
  if (node.has("anyOf")) {
    const existing = node.get("anyOf") as unknown[];
    node.delete("anyOf");
    node.set("anyOf", unionProduct(existing, branches, node, ctx, "T9"));
  } else {
    node.set("anyOf", branches);
  }
  for (const origin of origins) {
    ctx.add("core/oneof-to-anyof", "T8", {
      node, keyword: "oneOf", action: "rewritten", severity: exclusive ? "info" : "lossy", sourcePath: origin,
      message: "oneOf rewritten to anyOf" + (exclusive ? "; branches are disjoint so meaning is unchanged" : "; exclusivity is no longer enforced"),
    });
  }
}

// --- T5 / const->enum -------------------------------------------------------------------------

function t5Type(node: SNode, ctx: Ctx): void {
  if (node.has("type") || (!node.has("enum") && !node.has("const")) || node.ref !== null) return;
  const kw = node.has("const") ? "const" : "enum";
  const vals: unknown[] = kw === "const" ? [node.get("const")] : [...(node.get("enum") as unknown[])];
  if (ctx.rules.features.enum_values === "primitive" && vals.some((v) => v instanceof Map || Array.isArray(v))) {
    ctx.add("core/non-primitive-enum", "T5", {
      node, keyword: kw, action: "dropped", severity: "lossy", original: toOrdered(node.get(kw)), hint: true,
      message: "target only allows primitive enum/const values",
    });
    node.delete(kw);
    return;
  }
  const byType = new Map<string, unknown[]>();
  const anyNumber = vals.some((x) => jsonType(x) === "number");
  for (const v of vals) {
    let t = jsonType(v);
    if (t === "integer" && anyNumber) t = "number";
    byType.set(t, [...(byType.get(t) ?? []), v]);
  }
  const nonNull = [...byType.keys()].filter((t) => t !== "null");
  if (nonNull.length <= 1) {
    const types = [...nonNull, ...(byType.has("null") ? ["null"] : [])];
    if (!types.length) return;
    node.set("type", types.length === 1 ? types[0] : types);
    ctx.add("core/enum-type-inferred", "T5", {
      node, keyword: "type", action: "rewritten", severity: "info", message: `type inferred from ${kw} values`,
    });
    return;
  }
  if (node.has("anyOf")) return;
  node.delete(kw);
  const branches = [...byType].map(([t, vs]) =>
    t !== "null" ? new SNode([["type", t], ["enum", vs]], node.src) : new SNode([["type", "null"]], node.src),
  );
  node.set("anyOf", branches);
  for (const b of branches) b.kwSrc.set("enum", node.origins(kw));
  ctx.add("core/mixed-enum-split", "T5", {
    node, keyword: kw, action: "rewritten", severity: "info", original: vals,
    message: `${kw} with mixed value types split into one typed enum per type`,
  });
}

function unsupported(ctx: Ctx, kw: string): boolean {
  const s = keywordStatus(ctx.rules, kw);
  return s === "stripped" || s === "rejected" || (s === undefined && !ctx.rules.keepsUnknownKeywords);
}

function constToEnum(node: SNode, ctx: Ctx): void {
  if (!node.has("const") || node.has("enum")) return;
  if (!unsupported(ctx, "const") || unsupported(ctx, "enum")) return;
  const rebuilt = [...node].map(([k, v]) => (k === "const" ? (["enum", [v]] as const) : ([k, v] as const)));
  const origins = node.origins("const");
  node.clear();
  for (const [k, v] of rebuilt) node.set(k, v);
  node.kwSrc.set("enum", origins);
  for (const origin of origins) {
    ctx.add("core/const-to-enum", "T5", {
      node, keyword: "const", action: "rewritten", severity: "info", sourcePath: origin,
      original: (node.get("enum") as unknown[])[0],
      message: "const rewritten to an equivalent single-value enum (const is not enforced by the target)",
    });
  }
}

// --- T4 ---------------------------------------------------------------------------------------

function t4(node: SNode, ctx: Ctx): void {
  const t = node.get("type");
  if (!Array.isArray(t)) return;
  let types = [...new Set(t as string[])];
  const nonNull = types.filter((x) => x !== "null");
  if (nonNull.includes("integer") && nonNull.includes("number")) {
    nonNull.splice(nonNull.indexOf("integer"), 1);
    types = types.filter((x) => x !== "integer");
  }
  if (nonNull.length <= 1) {
    const newT: unknown = types.length === 1 ? types[0] : types;
    if (canonicalize(newT) !== canonicalize(t)) {
      node.set("type", newT);
      ctx.add("core/integer-number-collapsed", "T4", {
        node, keyword: "type", action: "rewritten", severity: "info", original: t, message: "integer is subsumed by number",
      });
    }
    return;
  }
  const specific = new Set(types.flatMap((ty) => TYPE_KEYWORDS[ty] ?? []));
  const valuesKw = node.has("const") ? "const" : node.has("enum") ? "enum" : null;
  const vals: unknown[] | null = valuesKw === null ? null : valuesKw === "const" ? [node.get("const")] : [...(node.get("enum") as unknown[])];
  const branches: SNode[] = [];
  for (const ty of types) {
    const b = new SNode([["type", ty]], node.src);
    for (const k of TYPE_KEYWORDS[ty] ?? []) {
      if (node.has(k)) {
        const v = node.get(k);
        b.set(k, v instanceof SNode ? copyTree(v) : v);
        b.kwSrc.set(k, node.origins(k));
      }
    }
    if (vals !== null) {
      const vs = vals.filter((v) => jsonType(v) === ty || (ty === "number" && jsonType(v) === "integer"));
      if (!vs.length) continue;
      b.set("enum", vs);
      b.kwSrc.set("enum", node.origins(valuesKw!));
    }
    branches.push(b);
  }
  if (valuesKw !== null) {
    for (const origin of node.origins(valuesKw)) {
      ctx.add("core/multi-type-split", "T4", {
        node, keyword: valuesKw, action: "rewritten", severity: "info", sourcePath: origin, original: vals,
        message: `${valuesKw} values partitioned into the typed anyOf branches`,
      });
    }
  }
  for (const k of [...specific, "type", ...(valuesKw ? [valuesKw] : [])]) node.delete(k);
  if (node.has("anyOf")) {
    const existing = node.get("anyOf") as unknown[];
    node.delete("anyOf");
    node.set("anyOf", unionProduct(branches, existing, node, ctx, "T9"));
  } else {
    node.set("anyOf", branches);
  }
  ctx.add("core/multi-type-split", "T4", {
    node, keyword: "type", action: "rewritten", severity: "info", original: t,
    message: "multi-type array rewritten as anyOf with type-specific keywords per branch",
  });
}

// --- T9 ---------------------------------------------------------------------------------------

function t9(node: SNode, ctx: Ctx): void {
  const moving = [...node.keys()].filter(
    (k) => k !== "anyOf" && ["validation", "applicator", "unknown"].includes(keywordKind(k)) && !k.startsWith("x-"),
  );
  if (!moving.length) return;
  const base = new SNode(moving.map((k) => [k, node.get(k)] as const), node.src);
  base.kwSrc = new Map(moving.map((k) => [k, node.origins(k)]));
  const fresh = unionProduct([base], node.get("anyOf") as unknown[], node, ctx, "T9");
  for (const k of moving) node.delete(k);
  node.set("anyOf", fresh);
  for (const b of fresh) if (b instanceof SNode) visit(b, ctx, new Seen());
  ctx.add("core/anyof-siblings-distributed", "T9", {
    node, keyword: "anyOf", action: "rewritten", severity: "info", message: "keywords next to anyOf distributed into each branch",
  });
}

/** Stage S11 / T18: per-schema limits, property keys and arrays without items. Port of validate.py. */
import { type Ctx } from "../context.js";
import { LimitExceededError } from "../errors.js";
import { type OMap } from "../ojson.js";
import { join } from "../pointer.js";
import { pyRepr } from "../pyfmt.js";
import { iterSubschemas, Seen, SNode } from "../tree.js";

const cpLen = (s: string): number => [...s].length;

export function validateTree(root: SNode, ctx: Ctx): void {
  const pattern = ctx.rules.propertyKeyPattern ? new RegExp(ctx.rules.propertyKeyPattern, "u") : null;
  const seen = new Seen();
  const visit = (node: SNode): void => {
    if (seen.has(node)) return;
    seen.add(node);
    const props = node.get("properties");
    if (pattern !== null && props instanceof Map) {
      for (const [key, child] of props as OMap) {
        if (!pattern.test(key)) {
          ctx.add(ctx.ruleId("property-key-invalid"), "T18", {
            node, keyword: "properties", action: "rejected", severity: "fatal",
            sourcePath: child instanceof SNode && child.src.length ? child.src[0]! : join(node.src[0] ?? "", "properties", key),
            original: key,
            message: `property name ${pyRepr(key)} does not match ${ctx.rules.propertyKeyPattern!} (renaming arrives in v0.2)`,
          });
        }
      }
    }
    const t = node.get("type");
    const isArray = t === "array" || (Array.isArray(t) && t.includes("array"));
    if (ctx.rules.features.array_items_required && isArray && !node.has("items") && !node.has("prefixItems")) {
      if (ctx.rules.strict) {
        ctx.add(ctx.ruleId("array-items-missing"), "T18", {
          node, keyword: "items", action: "rejected", severity: "fatal", message: "array without items cannot be expressed in strict mode",
        });
      } else {
        node.set("items", new SNode([], []));
        ctx.add(ctx.ruleId("array-items-added"), "T18", {
          node, keyword: "items", action: "rewritten", severity: "info", message: "array without items: added the equivalent items: {}",
        });
      }
    }
    for (const [, , child] of [...iterSubschemas(node)]) if (child instanceof SNode) visit(child);
  };
  for (const tree of [root, ...ctx.defs.values()]) visit(tree);
}

export function countNodes(v: unknown): number {
  let n = 1;
  if (v instanceof Map) for (const x of (v as OMap).values()) n += countNodes(x);
  else if (Array.isArray(v)) for (const x of v as unknown[]) n += countNodes(x);
  return n;
}

export function checkOutput(schema: OMap, ctx: Ctx): void {
  const n = countNodes(schema);
  if (n > ctx.opts.maxNodes) throw new LimitExceededError(`output exceeds max_nodes=${ctx.opts.maxNodes} (${n} nodes)`);
  const limits = ctx.rules.limits;
  if (!Object.keys(limits).length) return;
  const s = stats(schema);
  const over = (name: string, value: number, what: string): void => {
    const limit = limits[name];
    if (limit !== undefined && value > limit) {
      ctx.add(ctx.ruleId("limit-" + name.replace(/_/g, "-")), "T18", {
        node: null, keyword: null, action: "rejected", severity: "fatal", sourcePath: "", original: value,
        message: `${what} is ${value}; the target allows at most ${limit}`,
      });
    }
  };
  over("max_properties", s.properties, "total number of object properties");
  over("max_nesting_depth", s.depth, "object nesting depth");
  over("max_total_string_chars", s.chars, "total length of property/definition names and enum/const values");
  over("max_enum_values", s.enumValues, "total number of enum values");
  const threshold = limits.large_enum_threshold;
  if (threshold !== undefined) {
    over("max_large_enum_chars", s.largeEnumCount > threshold ? s.largeEnumChars : 0, `total length of a string enum with more than ${threshold} values`);
  }
}

function stats(schema: OMap) {
  const s = { properties: 0, depth: 0, chars: 0, enumValues: 0, largeEnumChars: 0, largeEnumCount: 0 };
  const visit = (node: unknown, depth: number): void => {
    if (!(node instanceof Map)) return;
    const d = node as OMap;
    const level = d.has("properties") ? depth + 1 : depth;
    s.depth = Math.max(s.depth, level);
    const props = (d.get("properties") as OMap | undefined) ?? new Map<string, unknown>();
    s.properties += props.size;
    for (const k of props.keys()) s.chars += cpLen(k);
    for (const k of ((d.get("$defs") as OMap | undefined) ?? new Map<string, unknown>()).keys()) s.chars += cpLen(k);
    const en = d.get("enum");
    if (Array.isArray(en)) {
      s.enumValues += en.length;
      const strs = en.filter((v): v is string => typeof v === "string");
      for (const v of strs) s.chars += cpLen(v);
      if (strs.length > s.largeEnumCount) {
        s.largeEnumCount = strs.length;
        s.largeEnumChars = strs.reduce((a, v) => a + cpLen(v), 0);
      }
    }
    const c = d.get("const");
    if (typeof c === "string") s.chars += cpLen(c);
    for (const [k, v] of d) {
      if (["properties", "$defs", "patternProperties", "dependentSchemas"].includes(k)) {
        for (const sub of (v as OMap).values()) visit(sub, level);
      } else if (["anyOf", "oneOf", "allOf", "prefixItems"].includes(k) && Array.isArray(v)) {
        for (const sub of v) visit(sub, level);
      } else if (v instanceof Map && !["default", "const", "examples"].includes(k)) {
        visit(v, level);
      }
    }
  };
  visit(schema, 0);
  return s;
}

/** Stage S2: dialect-independent canonical form (equivalent rewrites, reported as info). */
import { type Ctx } from "../context.js";
import { type OMap } from "../ojson.js";
import { join } from "../pointer.js";
import { iterSubschemas, Seen, SNode } from "../tree.js";

const BOOL_KEEP = new Set(["additionalProperties", "items", "unevaluatedProperties", "unevaluatedItems", "additionalItems"]);
const D7_KEEP_WITH_REF = new Set(["$ref", "$comment"]);

export function canonicalizeTree(root: SNode, ctx: Ctx, dialect: string): void {
  const seen = new Seen();
  for (const tree of [root, ...ctx.defs.values()]) visit(tree, ctx, dialect, seen);
}

function visit(node: SNode, ctx: Ctx, dialect: string, seen: Seen): void {
  if (seen.has(node)) return;
  seen.add(node);
  if (dialect === "draft-07" && node.has("$ref")) dropDraft07RefSiblings(node, ctx);
  tupleItems(node, ctx);
  dependencies(node, ctx);
  nullable(node, ctx);
  if (!ctx.rules.features.boolean_subschemas) booleans(node, ctx);
  for (const [, , child] of [...iterSubschemas(node)]) if (child instanceof SNode) visit(child, ctx, dialect, seen);
}

function dropDraft07RefSiblings(node: SNode, ctx: Ctx): void {
  for (const kw of [...node.keys()].filter((k) => !D7_KEEP_WITH_REF.has(k))) {
    ctx.add("core/draft07-ref-sibling-ignored", "T3", {
      node, keyword: kw, action: "dropped", severity: "info", original: node.get(kw),
      message: "draft-07 ignores keywords next to $ref",
    });
    node.delete(kw);
  }
}

function rebuild(node: SNode, entries: [string, unknown][]): void {
  node.clear();
  for (const [k, v] of entries) node.set(k, v);
}

function tupleItems(node: SNode, ctx: Ctx): void {
  if (!Array.isArray(node.get("items"))) return;
  const tail = node.get("additionalItems");
  node.delete("additionalItems");
  const out: [string, unknown][] = [];
  for (const [k, v] of node) {
    if (k === "items") {
      out.push(["prefixItems", v]);
      if (tail !== undefined) out.push(["items", tail]);
    } else out.push([k, v]);
  }
  rebuild(node, out);
  ctx.add("core/tuple-items-to-prefix-items", "T3", {
    node, keyword: "items", action: "rewritten", severity: "info",
    message: "array-form items rewritten to prefixItems (2020-12)",
  });
}

function dependencies(node: SNode, ctx: Ctx): void {
  const deps = node.get("dependencies");
  if (!(deps instanceof Map)) return;
  const req: OMap = new Map();
  const sch: OMap = new Map();
  for (const [k, v] of deps as OMap) (Array.isArray(v) ? req : sch).set(k, v);
  const out: [string, unknown][] = [];
  for (const [k, v] of node) {
    if (k === "dependencies") {
      if (req.size) out.push(["dependentRequired", req]);
      if (sch.size) out.push(["dependentSchemas", sch]);
    } else out.push([k, v]);
  }
  rebuild(node, out);
  ctx.add("core/dependencies-split", "T3", {
    node, keyword: "dependencies", action: "rewritten", severity: "info",
    message: "draft-07 dependencies split into dependentRequired / dependentSchemas",
  });
}

function nullable(node: SNode, ctx: Ctx): void {
  if (!node.has("nullable")) return;
  const flag = node.get("nullable");
  node.delete("nullable");
  const t = node.get("type");
  if (flag === true && t !== undefined) {
    const types = typeof t === "string" ? [t] : [...(t as unknown[])];
    if (!types.includes("null")) {
      types.push("null");
      ctx.add("core/openapi-nullable", "T3", {
        node, keyword: "type", action: "rewritten", severity: "info", original: t,
        message: "null added to the type array (OpenAPI nullable)",
      });
    }
    node.set("type", types);
  }
  ctx.add("core/openapi-nullable", "T3", {
    node, keyword: "nullable", action: flag === true ? "rewritten" : "dropped", severity: "info", original: flag,
    message: "OpenAPI nullable folded into the JSON Schema type array",
  });
}

function booleans(node: SNode, ctx: Ctx): void {
  for (const [kw, key, child] of [...iterSubschemas(node)]) {
    if (typeof child !== "boolean" || (key === null && BOOL_KEEP.has(kw))) continue;
    const base = node.src[0] ?? "";
    const ptr = key === null ? join(base, kw) : join(base, kw, key);
    const fresh = child ? new SNode([], [ptr]) : new SNode([["not", new SNode([], [])]], [ptr]);
    if (key === null) node.set(kw, fresh);
    else setChild(node.get(kw), key, fresh);
    ctx.add("core/boolean-subschema", "T3", {
      node: fresh, keyword: child ? null : "not", action: "rewritten", severity: "info", sourcePath: ptr,
      original: child, message: "boolean subschema rewritten as an equivalent object schema",
    });
  }
}

export function setChild(container: unknown, key: string | number, value: unknown): void {
  if (Array.isArray(container)) container[key as number] = value;
  else (container as Map<string, unknown>).set(key as string, value);
}

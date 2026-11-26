/** Stage S8 / T11: optional properties -> required + nullable. Port of optional.py. */
import { type Ctx } from "../context.js";
import { type OMap } from "../ojson.js";
import { pyRepr } from "../pyfmt.js";
import { iterSubschemas, Seen, SNode } from "../tree.js";

export function acceptsNull(s: unknown, seen: ReadonlySet<SNode> = new Set()): boolean {
  if (typeof s === "boolean") return s;
  if (!(s instanceof SNode)) return true;
  if (s.ref !== null) {
    if (seen.has(s.ref)) return false;
    if (!acceptsNull(s.ref, new Set([...seen, s.ref]))) return false;
  }
  const t = s.get("type");
  if (t !== undefined && !(t === "null" || (Array.isArray(t) && t.includes("null")))) return false;
  if (s.has("const") && s.get("const") !== null) return false;
  if (s.has("enum") && !(s.get("enum") as unknown[]).includes(null)) return false;
  for (const kw of ["anyOf", "oneOf"]) {
    if (s.has(kw) && !(s.get(kw) as unknown[]).some((b) => acceptsNull(b, seen))) return false;
  }
  return ((s.get("allOf") as unknown[] | undefined) ?? []).every((b) => acceptsNull(b, seen));
}

export function optionalStage(root: SNode, ctx: Ctx): void {
  if (!ctx.rules.features.all_required) return;
  const seen = new Seen();
  for (const tree of [root, ...ctx.defs.values()]) visit(tree, ctx, seen);
}

function visit(node: SNode, ctx: Ctx, seen: Seen): void {
  if (seen.has(node)) return;
  seen.add(node);
  for (const [, , child] of [...iterSubschemas(node)]) if (child instanceof SNode) visit(child, ctx, seen);
  const props = node.get("properties");
  if (!(props instanceof Map) || !props.size) return;
  const p = props as OMap;
  const required = [...((node.get("required") as string[] | undefined) ?? [])];
  const missing = [...p.keys()].filter((n) => !required.includes(n));
  if (!missing.length) return;
  for (const name of missing) {
    const sub = p.get(name);
    if (acceptsNull(sub) && sub instanceof SNode && sub.has("default") && sub.get("default") === null) {
      ctx.add(ctx.ruleId("optional-nullable-default-null"), "T11a", {
        node: sub, keyword: "required", action: "rewritten", severity: "reversible", sourcePath: srcOf(sub, node),
        message: `optional property ${pyRepr(name)} defaults to null, so omitting it and sending null are equivalent; null is removed again by denormalize_args`,
      });
      node.ops.push(new Map<string, unknown>([["op", "drop_injected_null"], ["property", name]]));
      continue;
    }
    if (acceptsNull(sub)) {
      ctx.add(ctx.ruleId("optional-nullable-ambiguous"), "T11b", {
        node: sub instanceof SNode ? sub : node, keyword: "required", action: "rewritten", severity: "lossy",
        sourcePath: srcOf(sub, node),
        message: `optional property ${pyRepr(name)} already accepts null; once required, 'omitted' and 'null' can no longer be distinguished`,
      });
      continue;
    }
    p.set(name, injectNull(sub, name, node, ctx));
    node.ops.push(new Map<string, unknown>([["op", "drop_injected_null"], ["property", name]]));
  }
  node.set("required", [...required, ...missing]);
}

const srcOf = (sub: unknown, parent: SNode): string =>
  sub instanceof SNode && sub.src.length ? sub.src[0]! : (parent.src[0] ?? "");

function entry(ctx: Ctx, node: SNode, keyword: string, name: string, original: unknown = null): void {
  for (const origin of node.origins(keyword)) {
    ctx.add(ctx.ruleId("optional-to-nullable"), "T11a", {
      node, keyword, action: "rewritten", severity: "reversible", original, sourcePath: origin,
      message: `optional property ${pyRepr(name)} made required and nullable; null is removed again by denormalize_args`,
    });
  }
}

function injectNull(sub: unknown, name: string, parent: SNode, ctx: Ctx): unknown {
  if (!(sub instanceof SNode) || sub.ref !== null || (!sub.has("type") && !sub.has("anyOf"))) {
    const wrapper = new SNode([["anyOf", [sub, new SNode([["type", "null"]], [])]]], []);
    if (sub instanceof SNode && sub.ref !== null) {
      for (const k of ["description", "title"]) {
        if (sub.has(k)) {
          wrapper.set(k, sub.get(k));
          sub.delete(k);
        }
      }
    }
    ctx.add(ctx.ruleId("optional-to-nullable"), "T11a", {
      node: wrapper, keyword: "anyOf", action: "rewritten", severity: "reversible", sourcePath: srcOf(sub, parent),
      message: `optional property ${pyRepr(name)} made required and nullable (anyOf with null); null is removed again by denormalize_args`,
    });
    return wrapper;
  }
  if (sub.has("anyOf") && !sub.has("type")) {
    (sub.get("anyOf") as unknown[]).push(new SNode([["type", "null"]], []));
    entry(ctx, sub, "anyOf", name);
    return sub;
  }
  const t = sub.get("type");
  const types = typeof t === "string" ? [t] : [...(t as string[])];
  if (!types.includes("null")) {
    sub.set("type", [...types, "null"]);
    entry(ctx, sub, "type", name, t);
  }
  if (sub.has("enum") && !(sub.get("enum") as unknown[]).includes(null)) {
    const original = [...(sub.get("enum") as unknown[])];
    sub.set("enum", [...original, null]);
    entry(ctx, sub, "enum", name, original);
  }
  if (sub.has("const")) {
    const c = sub.get("const");
    sub.delete("const");
    sub.set("enum", [c, null]);
    entry(ctx, sub, "const", name, c);
  }
  return sub;
}

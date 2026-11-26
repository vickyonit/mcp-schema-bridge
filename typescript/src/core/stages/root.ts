/** Stage S5 / T14: make the root a plain object the target accepts. */
import { type Ctx } from "../context.js";
import { pySorted } from "../pyfmt.js";
import { SNode, walk } from "../tree.js";

function typeSet(node: SNode): Set<string> | null {
  const t = node.get("type");
  if (t === undefined) return null;
  if (typeof t === "string") return new Set([t]);
  return new Set((t as unknown[]).filter((x): x is string => typeof x === "string"));
}

export function applyRoot(root: SNode, ctx: Ctx): SNode {
  const f = ctx.rules.features;
  let types = typeSet(root);
  const hasUnion = root.has("anyOf") || root.has("oneOf");
  const objectish = types !== null && types.has("object");
  if (types !== null && types.has("object") && types.size > 1) {
    root.set("type", "object");
    ctx.add("core/root-type-narrowed", "T14", {
      node: root, keyword: "type", action: "narrowed", severity: "info", original: pySorted(types),
      message: "MCP tool arguments are always objects; non-object root types removed",
    });
    types = new Set(["object"]);
  }
  const nonObject = types !== null && !types.has("object");
  const unionRoot = hasUnion && types === null && !root.has("properties");
  const needsWrap = nonObject || (unionRoot && !f.root_union) || (hasUnion && objectish && !f.root_anyof_with_object);
  if (needsWrap) return wrap(root, ctx);
  if (types === null && f.root_type_object_required && !unionRoot) {
    root.set("type", "object");
    ctx.add("core/root-type-object-added", "T14", {
      node: root, keyword: "type", action: "narrowed", severity: "info",
      message: "root declared no type; added type: object (MCP tool arguments are objects)",
    });
  }
  return root;
}

function wrap(root: SNode, ctx: Ctx): SNode {
  let referenced = false;
  for (const d of [root, ...ctx.defs.values()]) for (const [, n] of walk(d)) if (n.ref === root) referenced = true;
  let inner: SNode = root;
  if (referenced) {
    const name = uniqueName("__root", ctx);
    ctx.defs.set(name, root);
    inner = new SNode([["$ref", "#"]], [], root);
  }
  const wrapper = new SNode(
    [["type", "object"], ["properties", new Map([["value", inner]])], ["required", ["value"]]],
    [],
  );
  wrapper.ops.push(new Map([["op", "unwrap_root"]]));
  ctx.add("core/root-wrapped", "T14", {
    node: root, keyword: "type", action: "wrapped", severity: "reversible",
    message: "root is not a plain object for this target; wrapped as {value: ...}",
  });
  return wrapper;
}

export function uniqueName(base: string, ctx: Ctx): string {
  let name = base;
  let i = 1;
  while (ctx.defs.has(name)) name = `${base}_${i++}`;
  return name;
}

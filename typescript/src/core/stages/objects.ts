/** Stage S7 / T10: close objects on strict targets. Port of objects.py. */
import { type Ctx } from "../context.js";
import { keywordKind } from "../rules.js";
import { iterSubschemas, Seen, SNode, toOrdered } from "../tree.js";

const OBJECT_HINTS = ["properties", "additionalProperties", "patternProperties", "propertyNames", "required"];
const VALUE_POSITIONS = new Set(["properties", "items", "prefixItems", "anyOf", "oneOf"]);

export function isObjectSchema(node: SNode): boolean {
  const t = node.get("type");
  if (t !== undefined) return t === "object" || (Array.isArray(t) && t.includes("object"));
  return OBJECT_HINTS.some((k) => node.has(k));
}

export function isAny(node: SNode): boolean {
  if (node.ref !== null) return false;
  return ![...node.keys()].some((k) => ["validation", "applicator", "core", "unknown"].includes(keywordKind(k)));
}

const nonEmpty = (v: unknown): boolean => v instanceof Map && v.size > 0;

export function closeObjects(root: SNode, ctx: Ctx): void {
  if (!ctx.rules.features.close_objects) return;
  const seen = new Seen();
  closeRoot(root, ctx);
  seen.add(root);
  for (const tree of [root, ...ctx.defs.values()]) visit(tree, ctx, seen, null);
}

function closeRoot(root: SNode, ctx: Ctx): void {
  if (!isObjectSchema(root) && root.get("type") !== undefined) return;
  const extra = root.get("additionalProperties");
  if (nonEmpty(root.get("properties"))) {
    close(root, ctx);
    return;
  }
  if (root.has("patternProperties") || extra instanceof Map || extra === true) {
    rejectOpen(root, ctx);
    return;
  }
  if (!root.has("properties")) root.set("properties", new Map());
  if (extra !== false) {
    root.set("additionalProperties", false);
    ctx.add("core/parameterless-tool-closed", "T10", {
      node: root, keyword: "additionalProperties", action: "narrowed", severity: "info",
      message: "tool declares no parameters; closed as {type: object, properties: {}, additionalProperties: false}",
    });
  }
}

function visit(node: SNode, ctx: Ctx, seen: Seen, position: string | null): void {
  const first = !seen.has(node);
  seen.add(node);
  if (first) {
    if (position !== null && VALUE_POSITIONS.has(position) && isAny(node)) {
      ctx.add("core/any-value-unsupported", "T10", {
        node, keyword: null, action: "rejected", severity: "fatal",
        message: "a schema that accepts any value cannot be expressed in strict mode",
      });
    } else if (isObjectSchema(node)) {
      if (nonEmpty(node.get("properties")) || (node.has("properties") && node.get("additionalProperties") === false)) close(node, ctx);
      else rejectOpen(node, ctx);
    }
  }
  for (const [kw, , child] of [...iterSubschemas(node)]) if (child instanceof SNode && !seen.has(child)) visit(child, ctx, seen, kw);
}

function close(node: SNode, ctx: Ctx): void {
  const extra = node.get("additionalProperties");
  if (extra === false) return;
  node.set("additionalProperties", false);
  ctx.add("core/object-closed", "T10", {
    node, keyword: "additionalProperties", action: "narrowed", severity: extra === undefined ? "info" : "lossy",
    original: extra === undefined ? null : toOrdered(extra),
    message: "strict mode requires additionalProperties: false" + (extra === undefined ? "" : "; additional keys are no longer allowed"),
  });
}

function rejectOpen(node: SNode, ctx: Ctx): void {
  const extra = node.get("additionalProperties");
  ctx.add("core/open-object-unsupported", "T10", {
    node, keyword: "additionalProperties", action: "rejected", severity: "fatal",
    original: extra === undefined ? null : toOrdered(extra),
    message: "an object without declared properties (a map) cannot be expressed in strict mode",
  });
}

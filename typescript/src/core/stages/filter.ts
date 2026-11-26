/** Stage S9: keyword filter (T1, T12, T13, T15, T16). Port of filter.py. */
import { type Ctx } from "../context.js";
import { pyRepr, pySorted, pyStr } from "../pyfmt.js";
import { scan } from "../regex-scan.js";
import { type Severity } from "../report.js";
import { keywordKind, keywordStatus } from "../rules.js";
import { iterSubschemas, Seen, SNode, toOrdered } from "../tree.js";

const ALWAYS_KEEP = new Set(["$ref", "type", "properties", "required", "items", "anyOf", "description", "title"]);

export function filterStage(root: SNode, ctx: Ctx): void {
  const seen = new Seen();
  for (const tree of [root, ...ctx.defs.values()]) visit(tree, ctx, seen);
}

function visit(node: SNode, ctx: Ctx, seen: Seen): void {
  if (seen.has(node)) return;
  seen.add(node);
  integerExclusiveBounds(node, ctx);
  for (const kw of [...node.keys()]) if (node.has(kw)) filterKeyword(node, kw, ctx);
  for (const [, , child] of [...iterSubschemas(node)]) if (child instanceof SNode) visit(child, ctx, seen);
}

function supported(ctx: Ctx, kw: string): boolean {
  const s = keywordStatus(ctx.rules, kw);
  if (s === "enforced" || s === "accepted") return true;
  if (s === undefined) return ctx.rules.keepsUnknownKeywords;
  return false;
}

function slug(ctx: Ctx, kw: string): string {
  const s = keywordStatus(ctx.rules, kw);
  return s === "stripped" ? "keyword-not-enforced" : s === "rejected" ? "keyword-rejected" : "keyword-unsupported";
}

function drop(node: SNode, kw: string, ctx: Ctx, o: { tid: string; rule: string; severity: Severity; hint: boolean; message: string }): void {
  const value = toOrdered(node.get(kw));
  for (const origin of node.origins(kw)) {
    ctx.add(o.rule, o.tid, {
      node, keyword: kw, action: "dropped", severity: o.severity, sourcePath: origin, original: value, hint: o.hint, message: o.message,
    });
  }
  node.delete(kw);
  node.kwSrc.delete(kw);
}

function filterKeyword(node: SNode, kw: string, ctx: Ctx): void {
  if (ALWAYS_KEEP.has(kw)) return;
  const rules = ctx.rules;
  const kind = keywordKind(kw);
  if (supported(ctx, kw)) {
    if (kw === "format") checkFormat(node, ctx);
    else if (kw === "pattern" && rules.patternForbiddenFeatures.size) {
      const bad = [...scan(node.get("pattern") as string)].filter((f) => rules.patternForbiddenFeatures.has(f));
      if (bad.length) {
        drop(node, kw, ctx, {
          tid: "T16", rule: ctx.ruleId("pattern-unsupported"), severity: "lossy", hint: true,
          message: `pattern uses features the target rejects: ${pySorted(bad).join(", ")}`,
        });
      }
    } else if (kw === "minItems" && rules.features.min_items_values !== null) {
      clampMinItems(node, ctx);
    } else if ((kw === "enum" || kw === "const") && rules.features.enum_values === "primitive") {
      const vals = kw === "const" ? [node.get("const")] : (node.get("enum") as unknown[]);
      if (vals.some((v) => v instanceof Map || Array.isArray(v))) {
        drop(node, kw, ctx, {
          tid: "T12", rule: ctx.ruleId("non-primitive-enum"), severity: "lossy", hint: true,
          message: "target only allows primitive enum/const values",
        });
      }
    }
    return;
  }
  if (kw === "default") {
    drop(node, kw, ctx, {
      tid: "T13", rule: ctx.ruleId("default-dropped"), severity: "info", hint: true,
      message: "default is not supported by the target; kept as a description hint",
    });
    return;
  }
  if (kw === "format") {
    drop(node, kw, ctx, { tid: "T15", rule: ctx.ruleId("format-unsupported"), severity: "lossy", hint: true, message: "format is not supported by the target" });
    return;
  }
  if (kind === "annotation" || kind === "unknown" || kind === "core") {
    drop(node, kw, ctx, { tid: "T1", rule: "core/annotation-dropped", severity: "info", hint: false, message: `${kw} is not supported by the target` });
    return;
  }
  const how = keywordStatus(rules, kw) === "stripped" ? "not enforced" : "not supported";
  drop(node, kw, ctx, {
    tid: "T12", rule: ctx.ruleId(slug(ctx, kw)), severity: "lossy", hint: true,
    message: `${kw} is ${how} by the target; kept as a description hint`,
  });
}

function checkFormat(node: SNode, ctx: Ctx): void {
  const fmt = node.get("format");
  const { formatsAllowed: allowed, formatsEnforced: enforced } = ctx.rules;
  const ok = typeof fmt === "string" && (allowed === null || allowed.has(fmt)) && (!enforced.size || enforced.has(fmt));
  if (!ok) {
    drop(node, "format", ctx, {
      tid: "T15", rule: ctx.ruleId("format-unsupported"), severity: "lossy", hint: true,
      message: `format ${typeof fmt === "string" ? pyRepr(fmt) : pyStr(fmt)} is not enforced by the target`,
    });
  }
}

function clampMinItems(node: SNode, ctx: Ctx): void {
  const allowed = ctx.rules.features.min_items_values!;
  const v = node.get("minItems") as number;
  if (allowed.includes(v)) return;
  const below = allowed.filter((a) => a <= v);
  const best = below.length ? Math.max(...below) : Math.min(...allowed);
  for (const origin of node.origins("minItems")) {
    ctx.add(ctx.ruleId("min-items-clamped"), "T12", {
      node, keyword: "minItems", action: "rewritten", severity: "lossy", sourcePath: origin, original: v, hint: true,
      message: `minItems ${pyStr(v)} is not supported; clamped to ${best}`,
    });
  }
  node.set("minItems", best);
}

function isIntegerTyped(node: SNode): boolean {
  const t = node.get("type");
  const types = typeof t === "string" ? [t] : ((t as string[] | undefined) ?? []);
  return types.includes("integer") && types.every((x) => x === "integer" || x === "null");
}

function integerExclusiveBounds(node: SNode, ctx: Ctx): void {
  if (!isIntegerTyped(node)) return;
  for (const [ex, inc, delta] of [["exclusiveMinimum", "minimum", 1], ["exclusiveMaximum", "maximum", -1]] as const) {
    if (!node.has(ex) || supported(ctx, ex) || !supported(ctx, inc)) continue;
    const v = node.get(ex);
    if (typeof v !== "number" || !Number.isInteger(v)) continue;
    let bound = Math.trunc(v) + delta;
    const origins = node.origins(ex);
    const previous = node.get(inc);
    if (previous !== undefined) {
      const prev = previous as number;
      bound = delta > 0 ? (prev > bound ? prev : bound) : prev < bound ? prev : bound;
      if (bound !== prev) {
        for (const origin of node.origins(inc)) {
          ctx.add(ctx.ruleId("integer-exclusive-bound"), "T12", {
            node, keyword: inc, action: "merged", severity: "info", sourcePath: origin, original: previous,
            message: `${inc} tightened by ${ex}`,
          });
        }
      }
      node.kwSrc.set(inc, [...new Set([...node.origins(inc), ...origins])]);
    } else {
      node.kwSrc.set(inc, origins);
    }
    node.set(inc, bound);
    node.delete(ex);
    for (const origin of origins) {
      ctx.add(ctx.ruleId("integer-exclusive-bound"), "T12", {
        node, keyword: ex, action: "rewritten", severity: "info", sourcePath: origin, original: v,
        message: `${ex} ${pyStr(v)} rewritten as the equivalent ${inc} ${bound} for integers`,
      });
    }
  }
}

/** normalizeSchema: runs stages S0..S12 for one schema. Port of pipeline.py. */
import { createHash } from "node:crypto";
import { Ctx } from "./context.js";
import { buildEntries, emit } from "./emit.js";
import { canonicalize } from "./jcs.js";
import { type OMap } from "./ojson.js";
import { type NormalizeOptions, resolveOptions } from "./options.js";
import { checkValue } from "./parse.js";
import { Report, type ReportEntry } from "./report.js";
import { type NormalizeResult } from "./result.js";
import { loadRules, RULES_VERSION, type Target } from "./rules.js";
import { canonicalizeTree } from "./stages/canonicalize.js";
import { filterStage } from "./stages/filter.js";
import { hintsStage } from "./stages/hints.js";
import { inlineStage } from "./stages/inline.js";
import { mergeAllOf } from "./stages/merge.js";
import { closeObjects } from "./stages/objects.js";
import { optionalStage } from "./stages/optional.js";
import { resolve } from "./stages/resolve.js";
import { applyRoot } from "./stages/root.js";
import { unionsStage } from "./stages/unions.js";
import { checkOutput, validateTree } from "./stages/validate.js";
import { build, SNode } from "./tree.js";
import { VERSION } from "./version.js";

export function fingerprint(original: unknown, target: string): string {
  const payload = new Map<string, unknown>([
    ["original", original],
    ["library_version", VERSION],
    ["rules_version", RULES_VERSION],
    ["target", target],
  ]);
  return createHash("sha256").update(canonicalize(payload), "utf8").digest("hex");
}

export interface InternalArgs {
  tool?: string | null;
  fingerprintOf?: unknown;
}

/** Normalize one schema given as ordered JSON (Maps) or a plain object. */
export function normalizeSchemaOrdered(schema: unknown, target: Target, opts: NormalizeOptions = {}, args: InternalArgs = {}): NormalizeResult {
  const rules = loadRules(target);
  const o = resolveOptions(opts);
  const value = checkValue(schema, { maxNodes: o.maxNodes, maxDepth: o.maxDepth });
  const tool = args.tool ?? null;
  const ctx = new Ctx(rules, o, tool);
  const built = build(value);
  let root = built instanceof SNode ? built : new SNode([], [""]);
  const dialect = resolve(root, ctx);
  canonicalizeTree(root, ctx, dialect);
  mergeAllOf(root, ctx);
  inlineStage(root, ctx);
  root = applyRoot(root, ctx);
  unionsStage(root, ctx);
  closeObjects(root, ctx);
  optionalStage(root, ctx);
  filterStage(root, ctx);
  hintsStage(root, ctx);
  validateTree(root, ctx);
  const out = emit(root, ctx);
  if (out.schema !== null) {
    checkOutput(out.schema, ctx);
    if (ctx.fatal) {
      out.schema = null;
      out.entries = buildEntries(ctx, out.pointers);
    }
  }
  if (out.schema === null && o.strictFallback && rules.fallbackTarget !== null) {
    const fb = normalizeSchemaOrdered(schema, rules.fallbackTarget, opts, args);
    const demoted: ReportEntry = {
      rule: `${target}/strict-fallback`, tid: "T17", tool, sourcePath: "", targetPath: null, instancePath: null,
      keyword: null, action: "fallback", severity: "lossy", original: null, hinted: false,
      message: `schema could not be made strict; demoted to ${rules.fallbackTarget} (not grammar-constrained)`,
    };
    return { ...fb, report: new Report(fb.target, [...out.entries, demoted, ...fb.report.entries]) };
  }
  const fp = fingerprint(args.fingerprintOf !== undefined ? checkValue(args.fingerprintOf, { maxNodes: Infinity, maxDepth: Infinity }) : value, target);
  return {
    target,
    strict: rules.strict,
    schemaOrdered: out.schema as OMap | null,
    report: new Report(target, out.entries),
    reverse: { fingerprint: fp, rulesVersion: RULES_VERSION, target, ops: out.ops },
    fingerprint: fp,
    libraryVersion: VERSION,
    rulesVersion: RULES_VERSION,
    provenance: out.provenance,
  };
}

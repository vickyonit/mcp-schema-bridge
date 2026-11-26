/** normalizeTools: a whole MCP toolset for one target, including per-request budgets (T17). */
import { InvalidInputError } from "./errors.js";
import { fromPlain, type OMap, toPlain } from "./ojson.js";
import { type NormalizeOptions, resolveOptions } from "./options.js";
import { normalizeSchemaOrdered } from "./pipeline.js";
import { pyRepr } from "./pyfmt.js";
import { type Action, entryToOrdered, Report, type ReportEntry, type Severity } from "./report.js";
import { type NormalizeResult, type ReverseMap, reverseToOrdered } from "./result.js";
import { loadRules, RULES_VERSION, type Target } from "./rules.js";
import { VERSION } from "./version.js";

export interface NormalizedTool {
  readonly name: string;
  readonly description: string | null;
  readonly target: string;
  readonly strict: boolean;
  /** Normalized schema as a plain object (what you send to the provider). */
  readonly schema: Record<string, unknown>;
  /** The same schema with exact key order preserved (integer-like property names stay in place). */
  readonly schemaOrdered: OMap;
  readonly reverse: ReverseMap;
  readonly fingerprint: string;
}

export interface Rejection {
  readonly name: string;
  readonly target: string;
  readonly reasons: readonly ReportEntry[];
}

export function toolToOrdered(t: NormalizedTool): OMap {
  return new Map<string, unknown>([
    ["name", t.name],
    ["description", t.description],
    ["target", t.target],
    ["strict", t.strict],
    ["schema", t.schemaOrdered],
    ["reverse", reverseToOrdered(t.reverse)],
    ["fingerprint", t.fingerprint],
  ]);
}

export class ToolsetResult {
  readonly libraryVersion = VERSION;
  readonly rulesVersion = RULES_VERSION;
  constructor(
    readonly target: string,
    readonly tools: NormalizedTool[],
    readonly rejected: Rejection[],
    readonly report: Report,
  ) {}

  /** Insertion-ordered representation (identical to the Python `to_dict()`). */
  toOrdered(): OMap {
    return new Map<string, unknown>([
      ["target", this.target],
      ["library_version", this.libraryVersion],
      ["rules_version", this.rulesVersion],
      ["tools", this.tools.map(toolToOrdered)],
      ["rejected", this.rejected.map((r) => new Map<string, unknown>([["name", r.name], ["target", r.target], ["reasons", r.reasons.map(entryToOrdered)]]))],
      ["report", this.report.toOrdered(this.libraryVersion, this.rulesVersion)],
    ]);
  }

  toJSON(): unknown {
    return toPlain(this.toOrdered());
  }
}

function checkTool(t: unknown, i: number): [string, string | null, OMap, OMap] {
  if (!(t instanceof Map)) throw new InvalidInputError("tool must be an object", `/${i}`);
  const tool = t as OMap;
  const name = tool.get("name");
  if (typeof name !== "string" || !name) throw new InvalidInputError("tool name must be a non-empty string", `/${i}/name`);
  const desc = tool.get("description");
  if (desc !== undefined && desc !== null && typeof desc !== "string") {
    throw new InvalidInputError("tool description must be a string", `/${i}/description`);
  }
  const schema = tool.get("inputSchema");
  if (!(schema instanceof Map)) throw new InvalidInputError("tool inputSchema must be an object", `/${i}/inputSchema`);
  return [name, (desc as string | undefined) ?? null, schema as OMap, tool];
}

function reason(rule: string, tool: string, message: string, o: { action?: Action; severity?: Severity; original?: unknown } = {}): ReportEntry {
  return {
    rule, tid: rule.includes("name") ? "T18" : "T17", tool, sourcePath: "", targetPath: null, instancePath: null,
    keyword: null, action: o.action ?? "rejected", severity: o.severity ?? "fatal", original: o.original ?? null, hinted: false, message,
  };
}

function toTool(name: string, desc: string | null, r: NormalizeResult): NormalizedTool {
  return {
    name, description: desc, target: r.target, strict: r.strict,
    schema: toPlain(r.schemaOrdered) as Record<string, unknown>, schemaOrdered: r.schemaOrdered!,
    reverse: r.reverse, fingerprint: r.fingerprint,
  };
}

/** Normalize a toolset given as ordered JSON (Maps) or plain objects. */
export function normalizeToolsOrdered(tools: readonly unknown[], target: Target, opts: NormalizeOptions = {}): ToolsetResult {
  const rules = loadRules(target);
  const parsed = tools.map((t, i) => checkTool(fromPlain(t), i));
  const nameRe = new RegExp(rules.toolNamePattern, "u");
  const accepted: [NormalizedTool, OMap][] = [];
  const rejected: Rejection[] = [];
  const entries: ReportEntry[] = [];
  const seenNames = new Set<string>();
  for (const [name, desc, schema, raw] of parsed) {
    if (seenNames.has(name)) {
      const r = reason("core/duplicate-tool-name", name, `duplicate tool name ${pyRepr(name)}`, { original: name });
      rejected.push({ name, target, reasons: [r] });
      entries.push(r);
      continue;
    }
    seenNames.add(name);
    if (!nameRe.test(name)) {
      const r = reason(`${target}/tool-name-invalid`, name,
        `tool name ${pyRepr(name)} does not match ${rules.toolNamePattern} (renaming arrives in v0.2)`, { original: name });
      rejected.push({ name, target, reasons: [r] });
      entries.push(r);
      continue;
    }
    const result = normalizeSchemaOrdered(schema, target, opts, { tool: name, fingerprintOf: raw });
    entries.push(...result.report.entries);
    if (result.schemaOrdered === null) {
      rejected.push({ name, target, reasons: result.report.entries.filter((e) => e.severity === "fatal") });
      continue;
    }
    accepted.push([toTool(name, desc, result), raw]);
  }
  const final = Object.keys(rules.requestLimits).length
    ? applyBudgets(accepted, rules.requestLimits, opts, target, rejected, entries)
    : accepted.map(([t]) => t);
  return new ToolsetResult(target, final, rejected, new Report(target, entries));
}

export function usage(schema: OMap): [number, number] {
  let optional = 0;
  let unions = 0;
  const visit = (node: unknown): void => {
    if (!(node instanceof Map)) return;
    const d = node as OMap;
    const props = (d.get("properties") as OMap | undefined) ?? new Map<string, unknown>();
    const required = new Set((d.get("required") as string[] | undefined) ?? []);
    for (const [k, sub] of props) {
      if (!required.has(k)) optional++;
      if (sub instanceof Map) {
        const t = (sub as OMap).get("type");
        if ((sub as OMap).has("anyOf") || (Array.isArray(t) && t.length > 1)) unions++;
      }
    }
    for (const [k, v] of d) {
      if (k === "properties" || k === "$defs") for (const sub of (v as OMap).values()) visit(sub);
      else if ((k === "anyOf" || k === "prefixItems") && Array.isArray(v)) for (const sub of v) visit(sub);
      else if (k === "items") visit(v);
    }
  };
  visit(schema);
  return [optional, unions];
}

function applyBudgets(accepted: [NormalizedTool, OMap][], limits: Readonly<Record<string, number>>, opts: NormalizeOptions,
  target: Target, rejected: Rejection[], entries: ReportEntry[]): NormalizedTool[] {
  const o = resolveOptions(opts);
  const reserved = o.reservedBudget ?? {};
  let used: Record<string, number> = { tools: reserved.strictTools ?? 0, optional: reserved.optionalParams ?? 0, union: reserved.unionParams ?? 0 };
  const caps: Record<string, number | undefined> = { tools: limits.max_strict_tools, optional: limits.max_optional_params, union: limits.max_union_params };
  const rules = loadRules(target);
  const out: NormalizedTool[] = [];
  let overflow = false;
  for (const [t, raw] of accepted) {
    if (!t.strict) {
      out.push(t);
      continue;
    }
    const [opt, uni] = usage(t.schemaOrdered);
    const nxt: Record<string, number> = { tools: used.tools! + 1, optional: used.optional! + opt, union: used.union! + uni };
    const keys = ["tools", "optional", "union"];
    const fits = !overflow && keys.every((k) => caps[k] === undefined || nxt[k]! <= caps[k]!);
    if (fits) {
      used = nxt;
      out.push(t);
      continue;
    }
    overflow = true;
    const over = keys.filter((k) => caps[k] !== undefined && nxt[k]! > caps[k]!);
    const r = reason(`${target}/request-budget-exceeded`, t.name,
      `per-request strict budget exceeded (${(over.length ? over : ["earlier overflow"]).join(", ")}); this tool and all later strict tools are affected`,
      { original: new Map(keys.map((k) => [k, nxt[k]])) });
    entries.push(r);
    if (o.strictFallback && rules.fallbackTarget) {
      const fb = normalizeSchemaOrdered(raw.get("inputSchema"), rules.fallbackTarget, opts, { tool: t.name, fingerprintOf: raw });
      entries.push(...fb.report.entries);
      entries.push(reason(`${target}/strict-fallback`, t.name, `tool demoted to ${rules.fallbackTarget} (not grammar-constrained)`, { action: "fallback", severity: "lossy" }));
      if (fb.schemaOrdered === null) rejected.push({ name: t.name, target, reasons: [r] });
      else out.push(toTool(t.name, t.description, fb));
    } else {
      rejected.push({ name: t.name, target, reasons: [r] });
    }
  }
  return out;
}

/** mcp-schema-bridge: normalize MCP tool schemas for Gemini, OpenAI and Anthropic. */
import { toPlain } from "./core/ojson.js";
import { type NormalizeOptions } from "./core/options.js";
import { normalizeSchemaOrdered } from "./core/pipeline.js";
import { type NormalizeResult as InternalResult } from "./core/result.js";
import { type Target } from "./core/rules.js";
import { normalizeToolsOrdered, type ToolsetResult } from "./core/toolset.js";

export { type Api, toSdkPayload } from "./adapters.js";
export { InvalidInputError, LimitExceededError, ReverseMismatchError, SchemaBridgeError, UnsupportedSchemaError } from "./core/errors.js";
export { parseOrdered, stringifyOrdered } from "./core/ojson.js";
export type { Budget, NormalizeOptions } from "./core/options.js";
export { Report, type ReportEntry, SEVERITIES, type Severity, severityAtLeast } from "./core/report.js";
export type { ReverseMap } from "./core/result.js";
export { type DenormalizeResult, denormalizeArgs, type Repair } from "./core/reverse.js";
export { RULES_VERSION, TARGETS, type Target } from "./core/rules.js";
export { type NormalizedTool, type Rejection, ToolsetResult } from "./core/toolset.js";
export { VERSION } from "./core/version.js";

export interface NormalizeResult extends InternalResult {
  /** Normalized schema as a plain object, or null when the schema was rejected (fatal). */
  readonly schema: Record<string, unknown> | null;
}

/** Normalize one JSON Schema for a target. Accepts plain objects or ordered JSON (Maps from parseOrdered). */
export function normalizeSchema(schema: unknown, target: Target, opts: NormalizeOptions = {}): NormalizeResult {
  const r = normalizeSchemaOrdered(schema, target, opts);
  return { ...r, schema: r.schemaOrdered === null ? null : (toPlain(r.schemaOrdered) as Record<string, unknown>) };
}

/** Normalize an MCP toolset (`tools/list` result tools) for a target. */
export function normalizeTools(tools: readonly unknown[], target: Target, opts: NormalizeOptions = {}): ToolsetResult {
  return normalizeToolsOrdered(tools, target, opts);
}

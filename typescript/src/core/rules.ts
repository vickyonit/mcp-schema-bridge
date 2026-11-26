/** Provider rules (generated from the repository's rules/ directory). */
import { RULES_DATA } from "./rules.generated.js";

export const TARGETS = ["gemini-json", "openai", "openai-strict", "anthropic", "anthropic-strict"] as const;
export type Target = (typeof TARGETS)[number];
export type KeywordStatus = "enforced" | "accepted" | "stripped" | "rejected";
export type KeywordKind = "applicator" | "validation" | "annotation" | "core" | "unknown";

export const RULES_VERSION: string = RULES_DATA.index.rules_version;

export interface Features {
  ref: boolean;
  recursion: "any" | "optional_only" | "none";
  ref_siblings: boolean;
  type_arrays: boolean;
  multi_type_arrays: boolean;
  multi_type_enum: boolean;
  root_union: boolean;
  root_anyof_with_object: boolean;
  anyof_validation_siblings: boolean;
  merge_allof: boolean;
  oneof: boolean;
  close_objects: boolean;
  all_required: boolean;
  open_objects: boolean;
  tuple_items: boolean;
  boolean_subschemas: boolean;
  enum_values: "any" | "primitive";
  min_items_values: readonly number[] | null;
  array_items_required: boolean;
  root_type_object_required: boolean;
}

export interface Rules {
  target: Target;
  provider: string;
  strict: boolean;
  fallbackTarget: Target | null;
  apiField: string;
  features: Features;
  keywords: Readonly<Record<string, KeywordStatus>>;
  keepsUnknownKeywords: boolean;
  formatsAllowed: ReadonlySet<string> | null;
  formatsEnforced: ReadonlySet<string>;
  patternForbiddenFeatures: ReadonlySet<string>;
  limits: Readonly<Record<string, number>>;
  requestLimits: Readonly<Record<string, number>>;
  toolNamePattern: string;
  propertyKeyPattern: string | null;
}

const cache = new Map<string, Rules>();

export function isTarget(t: string): t is Target {
  return (TARGETS as readonly string[]).includes(t);
}

export function loadRules(target: string): Rules {
  if (!isTarget(target)) throw new Error(`unknown target '${target}'; expected one of ${TARGETS.join(", ")}`);
  const hit = cache.get(target);
  if (hit) return hit;
  const d = RULES_DATA[target] as unknown as Record<string, unknown> & {
    features: Features;
    formats: { allowed: string[] | null; enforced: string[] };
  };
  const r: Rules = {
    target,
    provider: d.provider as string,
    strict: d.strict as boolean,
    fallbackTarget: d.fallback_target as Target | null,
    apiField: d.api_field as string,
    features: d.features,
    keywords: d.keywords as Record<string, KeywordStatus>,
    keepsUnknownKeywords: d.unknown_keywords === "keep",
    formatsAllowed: d.formats.allowed === null ? null : new Set(d.formats.allowed),
    formatsEnforced: new Set(d.formats.enforced),
    patternForbiddenFeatures: new Set(d.pattern_forbidden_features as string[]),
    limits: d.limits as Record<string, number>,
    requestLimits: d.request_limits as Record<string, number>,
    toolNamePattern: d.tool_name_pattern as string,
    propertyKeyPattern: d.property_key_pattern as string | null,
  };
  cache.set(target, r);
  return r;
}

export const keywordStatus = (r: Rules, kw: string): KeywordStatus | undefined =>
  Object.prototype.hasOwnProperty.call(r.keywords, kw) ? r.keywords[kw] : undefined;

const KC = RULES_DATA["keyword-classes"];
const CLASS_SETS: [KeywordKind, ReadonlySet<string>][] = [
  ["applicator", new Set<string>(KC.applicator)],
  ["validation", new Set<string>(KC.validation)],
  ["annotation", new Set<string>(KC.annotation)],
  ["core", new Set<string>(KC.core)],
];

export function keywordKind(kw: string): KeywordKind {
  if (kw.startsWith("x-")) return "annotation";
  for (const [kind, set] of CLASS_SETS) if (set.has(kw)) return kind;
  return "unknown";
}

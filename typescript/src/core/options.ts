/** Public option types (mirrors the Python NormalizeOptions; camelCase). */
export interface Budget {
  strictTools?: number;
  optionalParams?: number;
  unionParams?: number;
}

export interface NormalizeOptions {
  /** Append dropped constraints to descriptions (spec/hint-format.md). Default true. */
  hints?: boolean;
  /** "raise": the first fatal entry throws UnsupportedSchemaError. Default "report". */
  onUnsupported?: "report" | "raise";
  /** Recursion unrolling depth on targets that forbid recursion. Default 3. */
  maxRefDepth?: number;
  /** Input and output JSON value cap. Default 10000. */
  maxNodes?: number;
  /** Input nesting cap. Default 64. */
  maxDepth?: number;
  /** Truncate original description text (never the hint). */
  maxDescriptionChars?: number | null;
  /** Demote unfixable or over-budget tools to the non-strict sibling target. Default false. */
  strictFallback?: boolean;
  reservedBudget?: Budget | null;
}

export type ResolvedOptions = Required<Omit<NormalizeOptions, "maxDescriptionChars" | "reservedBudget">> & {
  maxDescriptionChars: number | null;
  reservedBudget: Budget | null;
};

export function resolveOptions(o: NormalizeOptions = {}): ResolvedOptions {
  return {
    hints: o.hints ?? true,
    onUnsupported: o.onUnsupported ?? "report",
    maxRefDepth: o.maxRefDepth ?? 3,
    maxNodes: o.maxNodes ?? 10_000,
    maxDepth: o.maxDepth ?? 64,
    maxDescriptionChars: o.maxDescriptionChars ?? null,
    strictFallback: o.strictFallback ?? false,
    reservedBudget: o.reservedBudget ?? null,
  };
}

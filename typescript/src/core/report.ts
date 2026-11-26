/** Lossiness report model (spec/report.schema.json). */
import { utf16Compare } from "./jcs.js";

export const SEVERITIES = ["info", "reversible", "lossy", "fatal"] as const;
export type Severity = (typeof SEVERITIES)[number];
export const ACTIONS = ["dropped", "rewritten", "inlined", "merged", "coerced", "wrapped", "narrowed", "truncated", "fallback", "rejected"] as const;
export type Action = (typeof ACTIONS)[number];

const RANK: Record<Severity, number> = { info: 0, reversible: 1, lossy: 2, fatal: 3 };
export const severityAtLeast = (s: Severity, threshold: Severity): boolean => RANK[s] >= RANK[threshold];

export interface ReportEntry {
  readonly rule: string;
  readonly tid: string;
  readonly tool: string | null;
  readonly sourcePath: string;
  readonly targetPath: string | null;
  readonly instancePath: string | null;
  readonly keyword: string | null;
  readonly action: Action;
  readonly severity: Severity;
  readonly original: unknown;
  readonly hinted: boolean;
  readonly message: string;
}

export function entryToOrdered(e: ReportEntry): Map<string, unknown> {
  return new Map<string, unknown>([
    ["rule", e.rule],
    ["tid", e.tid],
    ["tool", e.tool],
    ["source_path", e.sourcePath],
    ["target_path", e.targetPath],
    ["instance_path", e.instancePath],
    ["keyword", e.keyword],
    ["action", e.action],
    ["severity", e.severity],
    ["original", e.original === undefined ? null : e.original],
    ["hinted", e.hinted],
    ["message", e.message],
  ]);
}

function sortKey(e: ReportEntry): string[] {
  return [e.tool ?? "", e.sourcePath, e.rule, e.keyword ?? "", e.targetPath ?? "", e.action];
}

export class Report {
  constructor(
    readonly target: string,
    readonly entries: ReportEntry[] = [],
  ) {}

  sorted(): ReportEntry[] {
    // stable sort, total order on the key tuple (UTF-16 code units, like RFC 8785)
    return [...this.entries].sort((a, b) => {
      const ka = sortKey(a);
      const kb = sortKey(b);
      for (let i = 0; i < ka.length; i++) {
        const c = utf16Compare(ka[i]!, kb[i]!);
        if (c) return c;
      }
      return 0;
    });
  }

  maxSeverity(): Severity | null {
    let best: Severity | null = null;
    for (const e of this.entries) if (best === null || RANK[e.severity] > RANK[best]) best = e.severity;
    return best;
  }

  hasFatal(): boolean {
    return this.entries.some((e) => e.severity === "fatal");
  }

  toOrdered(libraryVersion: string, rulesVersion: string): Map<string, unknown> {
    return new Map<string, unknown>([
      ["library_version", libraryVersion],
      ["rules_version", rulesVersion],
      ["target", this.target],
      ["entries", this.sorted().map(entryToOrdered)],
    ]);
  }
}

/** Per-normalization mutable state shared by pipeline stages. */
import { UnsupportedSchemaError } from "./errors.js";
import { type ResolvedOptions } from "./options.js";
import { type Action, type Severity } from "./report.js";
import { type Rules } from "./rules.js";
import { type SNode } from "./tree.js";

export interface PendingEntry {
  rule: string;
  tid: string;
  sourcePath: string;
  keyword: string | null;
  action: Action;
  severity: Severity;
  node: SNode | null;
  original: unknown;
  hinted: boolean;
  message: string;
  wantHint: boolean;
}

export interface AddArgs {
  node: SNode | null;
  keyword: string | null;
  action: Action;
  severity: Severity;
  sourcePath?: string;
  original?: unknown;
  message?: string;
  hint?: boolean;
}

export class Ctx {
  entries: PendingEntry[] = [];
  defs = new Map<string, SNode>();
  fatal = false;

  constructor(
    readonly rules: Rules,
    readonly opts: ResolvedOptions,
    readonly tool: string | null = null,
  ) {}

  add(rule: string, tid: string, a: AddArgs): PendingEntry {
    const src = a.sourcePath ?? (a.node && a.node.src.length ? a.node.src[0]! : "");
    const e: PendingEntry = {
      rule,
      tid,
      sourcePath: src,
      keyword: a.keyword,
      action: a.action,
      severity: a.severity,
      node: a.node,
      original: a.original === undefined ? null : a.original,
      hinted: false,
      message: a.message ?? "",
      wantHint: a.hint ?? false,
    };
    this.entries.push(e);
    if (a.severity === "fatal") {
      this.fatal = true;
      if (this.opts.onUnsupported === "raise") throw new UnsupportedSchemaError(a.message || rule, src);
    }
    return e;
  }

  ruleId(slug: string): string {
    return `${this.rules.target}/${slug}`;
  }

  /** A child context sharing defs, collecting entries separately and never raising (try-merge). */
  sub(): Ctx {
    const c = new Ctx(this.rules, { ...this.opts, onUnsupported: "report" }, this.tool);
    c.defs = this.defs;
    return c;
  }
}

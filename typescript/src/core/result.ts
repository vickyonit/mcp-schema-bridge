/** Result types: NormalizeResult and ReverseMap. */
import { type OMap } from "./ojson.js";
import { type Report } from "./report.js";

export interface ReverseMap {
  readonly fingerprint: string;
  readonly rulesVersion: string;
  readonly target: string;
  readonly ops: readonly OMap[];
}

export function reverseToOrdered(r: ReverseMap): OMap {
  return new Map<string, unknown>([
    ["fingerprint", r.fingerprint],
    ["rules_version", r.rulesVersion],
    ["target", r.target],
    ["ops", r.ops.map((o) => new Map(o))],
  ]);
}

export interface NormalizeResult {
  readonly target: string;
  readonly strict: boolean;
  /** The normalized schema as an insertion-ordered Map (null when fatal). Use `schemaObject` for a plain object. */
  readonly schemaOrdered: OMap | null;
  readonly report: Report;
  readonly reverse: ReverseMap;
  readonly fingerprint: string;
  readonly libraryVersion: string;
  readonly rulesVersion: string;
  readonly provenance: ReadonlyMap<string, readonly string[]>;
}

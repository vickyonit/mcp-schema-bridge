/**
 * Internal schema tree. Every schema object is an SNode (an insertion-ordered Map of keywords) with:
 * src (provenance), ref (resolved $ref target, by identity), ops (reverse-map ops), kwSrc (per-keyword
 * origins). Name maps (properties, $defs, ...) are Maps; plain JSON values stay as parsed.
 */
import { type OMap } from "./ojson.js";
import { join } from "./pointer.js";

export const SCHEMA_MAPS = new Set(["properties", "patternProperties", "$defs", "definitions", "dependentSchemas"]);
export const SCHEMA_ARRAYS = new Set(["allOf", "anyOf", "oneOf", "prefixItems"]);
export const SCHEMA_VALUES = new Set([
  "additionalProperties", "propertyNames", "contains", "not", "if", "then", "else",
  "unevaluatedProperties", "unevaluatedItems", "additionalItems", "contentSchema",
]);

export type Schema = SNode | boolean;
export type Op = Map<string, unknown>;

export class SNode extends Map<string, unknown> {
  src: string[];
  ref: SNode | null;
  ops: Op[] = [];
  kwSrc = new Map<string, string[]>();

  constructor(entries: Iterable<readonly [string, unknown]> = [], src: string[] = [], ref: SNode | null = null) {
    super(entries);
    this.src = src;
    this.ref = ref;
  }

  /** Source pointer(s) that contributed this keyword's current value. */
  origins(keyword: string): string[] {
    return this.kwSrc.get(keyword) ?? [this.src[0] ?? ""];
  }
}

export const isSchema = (v: unknown): v is Schema => v instanceof SNode || typeof v === "boolean";
export const isMap = (v: unknown): v is OMap => v instanceof Map && !(v instanceof SNode);

/** Identity set that keeps nodes alive. */
export class Seen {
  private readonly s = new Set<object>();
  has(n: object): boolean {
    return this.s.has(n);
  }
  add(n: object): void {
    this.s.add(n);
  }
}

export function build(value: unknown, pointer = ""): unknown {
  if (typeof value === "boolean" || !(value instanceof Map)) return value;
  const node = new SNode([], [pointer]);
  for (const [kw, v] of value as OMap) node.set(kw, buildChild(kw, v, join(pointer, kw)));
  return node;
}

function buildChild(kw: string, v: unknown, pointer: string): unknown {
  if (SCHEMA_MAPS.has(kw) && v instanceof Map) {
    return new Map([...(v as OMap)].map(([k, s]) => [k, build(s, join(pointer, k))]));
  }
  if (SCHEMA_ARRAYS.has(kw) && Array.isArray(v)) return v.map((s: unknown, i) => build(s, join(pointer, i)));
  if (SCHEMA_VALUES.has(kw)) return build(v, pointer);
  if (kw === "items") return Array.isArray(v) ? v.map((s: unknown, i) => build(s, join(pointer, i))) : build(v, pointer);
  if (kw === "dependencies" && v instanceof Map) {
    return new Map([...(v as OMap)].map(([k, s]) => [k, s instanceof Map || typeof s === "boolean" ? build(s, join(pointer, k)) : s]));
  }
  return plainCopy(v);
}

export function plainCopy(v: unknown): unknown {
  if (v instanceof SNode) return copyTree(v);
  if (v instanceof Map) return new Map([...(v as OMap)].map(([k, x]) => [k, plainCopy(x)]));
  if (Array.isArray(v)) return v.map(plainCopy);
  return v;
}

export type Sub = [kw: string, key: string | number | null, child: Schema];

export function* iterSubschemas(node: SNode): Generator<Sub> {
  for (const [kw, v] of node) {
    if (SCHEMA_MAPS.has(kw) && isMap(v)) {
      for (const [k, s] of v) if (isSchema(s)) yield [kw, k, s];
    } else if ((SCHEMA_ARRAYS.has(kw) || kw === "items") && Array.isArray(v)) {
      for (let i = 0; i < v.length; i++) if (isSchema(v[i])) yield [kw, i, v[i] as Schema];
    } else if ((SCHEMA_VALUES.has(kw) || kw === "items") && isSchema(v)) {
      yield [kw, null, v];
    } else if (kw === "dependencies" && isMap(v)) {
      for (const [k, s] of v) if (isSchema(s)) yield [kw, k, s];
    }
  }
}

export const childPointer = (pointer: string, kw: string, key: string | number | null): string =>
  key === null ? join(pointer, kw) : join(pointer, kw, key);

export function* walk(node: unknown, pointer = ""): Generator<[string, SNode]> {
  if (!(node instanceof SNode)) return;
  yield [pointer, node];
  for (const [kw, key, child] of iterSubschemas(node)) yield* walk(child, childPointer(pointer, kw, key));
}

export function copyTree<T>(node: T): T {
  if (!(node instanceof SNode)) return node;
  const out = new SNode([], node.src, node.ref);
  out.ops = node.ops.map((o) => new Map(o));
  out.kwSrc = new Map(node.kwSrc);
  for (const [kw, v] of node) {
    if (SCHEMA_MAPS.has(kw) && isMap(v)) out.set(kw, new Map([...v].map(([k, s]) => [k, copyTree(s)])));
    else if ((SCHEMA_ARRAYS.has(kw) || kw === "items") && Array.isArray(v)) out.set(kw, v.map((s: unknown) => copyTree(s)));
    else if ((SCHEMA_VALUES.has(kw) || kw === "items") && isSchema(v)) out.set(kw, copyTree(v));
    else if (kw === "dependencies" && isMap(v)) out.set(kw, new Map([...v].map(([k, s]) => [k, copyTree(s)])));
    else out.set(kw, plainCopy(v));
  }
  return out as T;
}

/** Strip node types: SNodes and Maps become ordered Maps (OMap), recursively. */
export function toOrdered(v: unknown): unknown {
  if (v instanceof Map) return new Map([...(v as OMap)].map(([k, x]) => [k, toOrdered(x)]));
  if (Array.isArray(v)) return v.map(toOrdered);
  return v;
}

export const getMap = (v: unknown): OMap | undefined => (v instanceof Map ? (v as OMap) : undefined);

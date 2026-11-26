/** denormalizeArgs: map model-produced arguments back to the original MCP schema shape. Port of reverse.py. */
import { InvalidInputError, ReverseMismatchError } from "./errors.js";
import { canonicalize } from "./jcs.js";
import { decodeFragment, join } from "./pointer.js";
import { pyRepr } from "./pyfmt.js";
import { type ReportEntry } from "./report.js";
import { type ReverseMap } from "./result.js";
import { RULES_VERSION } from "./rules.js";

export type Repair = "int_from_integral_float" | "enum_case_insensitive";
type Json = unknown;
type Obj = Record<string, unknown>;

export interface HasReverse {
  readonly schema: Obj | null;
  readonly reverse: ReverseMap;
  readonly fingerprint: string;
}

export interface DenormalizeResult {
  args: Json;
  warnings: ReportEntry[];
}

const isObj = (v: unknown): v is Obj => v !== null && typeof v === "object" && !Array.isArray(v);
const same = (a: unknown, b: unknown): boolean => {
  try {
    return canonicalize(a) === canonicalize(b);
  } catch {
    return false;
  }
};

function entry(rule: string, pointer: string, action: "coerced" | "rewritten", severity: "info" | "lossy", message: string, original: unknown = null): ReportEntry {
  return { rule, tid: "reverse", tool: null, sourcePath: pointer, targetPath: null, instancePath: null, keyword: null, action, severity, original, hinted: false, message };
}

class Walker {
  warnings: ReportEntry[] = [];
  constructor(
    readonly root: Obj,
    readonly ops: Map<string, Obj[]>,
    readonly strict: boolean,
    readonly repairs: ReadonlySet<Repair>,
  ) {}

  warn(rule: string, pointer: string, message: string): void {
    if (this.strict) throw new InvalidInputError(message, pointer);
    this.warnings.push(entry(rule, pointer, "rewritten", "lossy", message));
  }

  resolve(ref: string): [string, unknown] {
    const tokens = decodeFragment(ref);
    let node: unknown = this.root;
    for (const t of tokens) node = Array.isArray(node) ? node[Number(t)] : (node as Obj)[t];
    return [join("", ...tokens), node];
  }

  repair(ptr: string, s: Obj, value: Json): Json {
    // int_from_integral_float is a no-op in JavaScript: 5.0 and 5 are the same number.
    if (this.repairs.has("enum_case_insensitive") && typeof value === "string") {
      const en = s.enum;
      if (Array.isArray(en) && !en.includes(value)) {
        const matches = en.filter((v): v is string => typeof v === "string" && v.toLowerCase() === value.toLowerCase());
        if (matches.length === 1) {
          this.warnings.push(entry("core/repair-enum-case", ptr, "coerced", "info", `enum value matched case-insensitively to ${pyRepr(matches[0]!)}`, value));
          return matches[0];
        }
      }
    }
    return value;
  }

  walk(ptr: string, schema: unknown, value: Json, depth = 0): Json {
    if (!isObj(schema) || depth > 10_000) return value;
    const s = schema;
    if (typeof s.$ref === "string") {
      const [rptr, target] = this.resolve(s.$ref);
      value = this.walk(rptr, target, value, depth + 1);
    }
    if (isObj(value)) {
      const props = isObj(s.properties) ? s.properties : {};
      for (const k of Object.keys(value)) {
        if (Object.prototype.hasOwnProperty.call(props, k)) value[k] = this.walk(join(ptr, "properties", k), props[k], value[k], depth + 1);
        else if (isObj(s.additionalProperties)) value[k] = this.walk(join(ptr, "additionalProperties"), s.additionalProperties, value[k], depth + 1);
      }
    }
    if (Array.isArray(value)) {
      const arr = value as unknown[];
      const prefix = Array.isArray(s.prefixItems) ? (s.prefixItems as unknown[]) : [];
      arr.forEach((item, i) => {
        if (i < prefix.length) arr[i] = this.walk(join(ptr, "prefixItems", i), prefix[i], item, depth + 1);
        else if (isObj(s.items)) arr[i] = this.walk(join(ptr, "items"), s.items, item, depth + 1);
      });
    }
    for (const kw of ["anyOf", "oneOf"]) {
      const branches = s[kw];
      if (Array.isArray(branches)) {
        const i = branches.findIndex((b) => this.matches(b, value));
        if (i >= 0) value = this.walk(join(ptr, kw, i), branches[i], value, depth + 1);
      }
    }
    if (Array.isArray(s.allOf)) (s.allOf as unknown[]).forEach((b, i) => (value = this.walk(join(ptr, "allOf", i), b, value, depth + 1)));
    if (this.repairs.size) value = this.repair(ptr, s, value);
    for (const op of this.ops.get(ptr) ?? []) value = this.apply(op, ptr, value);
    return value;
  }

  apply(op: Obj, ptr: string, value: Json): Json {
    if (op.op === "unwrap_root") {
      if (isObj(value) && "value" in value) return value.value;
      this.warn("core/reverse-unrecognized-shape", ptr, "expected wrapper object with key 'value'");
      return value;
    }
    if (op.op === "drop_injected_null") {
      const name = op.property as string;
      // eslint-disable-next-line @typescript-eslint/no-dynamic-delete -- removing the injected key is the point
      if (isObj(value) && name in value && value[name] === null) delete value[name];
      return value;
    }
    throw new Error(`unknown reverse op ${String(op.op)}`);
  }

  matches(branch: unknown, value: Json): boolean {
    if (branch === true || (isObj(branch) && Object.keys(branch).length === 0)) return true;
    if (!isObj(branch)) return false;
    const b = branch;
    if (typeof b.$ref === "string" && !this.matches(this.resolve(b.$ref)[1], value)) return false;
    for (const kw of ["anyOf", "oneOf"]) {
      const subs = b[kw];
      if (Array.isArray(subs) && !subs.some((x) => this.matches(x, value))) return false;
    }
    if (Array.isArray(b.allOf) && !(b.allOf as unknown[]).every((x) => this.matches(x, value))) return false;
    if (b.type !== undefined) {
      const types = typeof b.type === "string" ? [b.type] : (b.type as string[]);
      if (!types.some((t) => typeOk(t, value))) return false;
    }
    if ("const" in b && !same(b.const, value)) return false;
    if (Array.isArray(b.enum) && b.enum.length === 1 && !same(b.enum[0], value)) return false;
    if (Array.isArray(b.required)) {
      if (!isObj(value)) return false;
      if ((b.required as string[]).some((k) => !(k in value))) return false;
    }
    return true;
  }
}

function typeOk(t: string, v: unknown): boolean {
  switch (t) {
    case "null": return v === null;
    case "integer": return typeof v === "number" && Number.isInteger(v);
    case "number": return typeof v === "number";
    case "string": return typeof v === "string";
    case "boolean": return typeof v === "boolean";
    case "array": return Array.isArray(v);
    case "object": return isObj(v);
    default: return false;
  }
}

export function denormalizeArgs(tool: HasReverse, args: Json, opts: { strict?: boolean; repairs?: Iterable<Repair> } = {}): DenormalizeResult {
  const rev = tool.reverse;
  if (rev.fingerprint !== tool.fingerprint) throw new ReverseMismatchError("reverse map fingerprint does not match the tool fingerprint");
  if (rev.rulesVersion !== RULES_VERSION) throw new ReverseMismatchError(`reverse map rules_version ${rev.rulesVersion} != loaded rules ${RULES_VERSION}`);
  const value: Json = args === undefined ? undefined : structuredClone(args);
  if (tool.schema === null) return { args: value, warnings: [] };
  const ops = new Map<string, Obj[]>();
  for (const op of rev.ops) {
    const plain = Object.fromEntries(op) as Obj;
    const at = plain.at as string;
    ops.set(at, [...(ops.get(at) ?? []), plain]);
  }
  const w = new Walker(tool.schema, ops, opts.strict ?? false, new Set(opts.repairs ?? []));
  return { args: w.walk("", tool.schema, value), warnings: w.warnings };
}

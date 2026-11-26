/** Stage S0: I-JSON validation, deep copy into ordered Maps, size and depth guards. */
import { InvalidInputError, LimitExceededError } from "./errors.js";
import { MAX_SAFE_INTEGER } from "./jcs.js";
import { type OMap } from "./ojson.js";
import { join } from "./pointer.js";

export interface Limits {
  maxNodes: number;
  maxDepth: number;
}

/** Validate an (ordered or plain) JSON value and return a deep copy where objects are Maps. */
export function checkValue(value: unknown, limits: Limits = { maxNodes: 10_000, maxDepth: 64 }): unknown {
  let count = 0;
  const visit = (v: unknown, pointer: string, depth: number): unknown => {
    count += 1;
    if (count > limits.maxNodes) throw new LimitExceededError(`input exceeds max_nodes=${limits.maxNodes}`, pointer);
    if (depth > limits.maxDepth) throw new LimitExceededError(`input exceeds max_depth=${limits.maxDepth}`, pointer);
    if (v === null || typeof v === "boolean") return v;
    if (typeof v === "number") {
      if (!Number.isFinite(v)) throw new InvalidInputError("JSON numbers must be finite", pointer);
      if (Number.isInteger(v) && Math.abs(v) > MAX_SAFE_INTEGER) {
        throw new InvalidInputError(`integer ${v} is outside the I-JSON safe range (|n| <= 2**53 - 1)`, pointer);
      }
      return v;
    }
    if (typeof v === "string") {
      checkString(v, pointer);
      return v;
    }
    if (Array.isArray(v)) return v.map((c: unknown, i) => visit(c, join(pointer, i), depth + 1));
    if (v instanceof Map || (typeof v === "object" && v !== undefined)) {
      const entries = v instanceof Map ? [...(v as Map<unknown, unknown>)] : Object.entries(v as object);
      const out: OMap = new Map();
      for (const [k, c] of entries) {
        if (typeof k !== "string") throw new InvalidInputError("object keys must be strings", pointer);
        checkString(k, pointer);
        out.set(k, visit(c, join(pointer, k), depth + 1));
      }
      return out;
    }
    throw new InvalidInputError(`not a JSON value: ${typeof v}`, pointer);
  };
  return visit(value, "", 0);
}

function checkString(s: string, pointer: string): void {
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdbff) {
      const n = s.charCodeAt(i + 1);
      if (n >= 0xdc00 && n <= 0xdfff) {
        i++;
        continue;
      }
      throw new InvalidInputError("lone surrogate in string is not valid I-JSON", pointer);
    }
    if (c >= 0xdc00 && c <= 0xdfff) throw new InvalidInputError("lone surrogate in string is not valid I-JSON", pointer);
  }
}

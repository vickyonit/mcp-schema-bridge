/** Stage S12 (finalize): working tree -> ordered output; resolve refs, ops and entry paths. */
import { type Ctx } from "./context.js";
import { type OMap } from "./ojson.js";
import { join, split } from "./pointer.js";
import { pyQuote, pyRepr } from "./pyfmt.js";
import { type ReportEntry } from "./report.js";
import { isMap, isSchema, iterSubschemas, SCHEMA_ARRAYS, SCHEMA_MAPS, SCHEMA_VALUES, Seen, SNode } from "./tree.js";

export interface Emitted {
  schema: OMap | null;
  pointers: Map<SNode, string>;
  provenance: Map<string, string[]>;
  ops: OMap[];
  entries: ReportEntry[];
}

export function emit(root: SNode, ctx: Ctx): Emitted {
  const out: Emitted = { schema: null, pointers: new Map(), provenance: new Map(), ops: [], entries: [] };
  const reachable = reachableDefs(root, ctx);
  const defPointer = new Map<SNode, string>([...reachable].map(([name, n]) => [n, join("", "$defs", name)]));
  const refString = (target: SNode): string => {
    if (target === root) return "#";
    const p = defPointer.get(target);
    if (p === undefined) throw new Error("ref target is neither root nor a registered def");
    return "#" + pyQuote(p);
  };
  const conv = (node: unknown, pointer: string): unknown => {
    if (!(node instanceof SNode)) return node;
    if (!out.pointers.has(node)) out.pointers.set(node, pointer);
    out.provenance.set(pointer, node.src);
    for (const op of node.ops) out.ops.push(new Map([...op, ["at", pointer]]));
    const d: OMap = new Map();
    for (const [kw, v] of node) {
      if (kw === "$ref" && node.ref !== null) d.set(kw, refString(node.ref));
      else if (SCHEMA_MAPS.has(kw) && isMap(v)) d.set(kw, new Map([...v].map(([k, s]) => [k, conv(s, join(pointer, kw, k))])));
      else if ((SCHEMA_ARRAYS.has(kw) || kw === "items") && Array.isArray(v)) d.set(kw, v.map((s: unknown, i) => conv(s, join(pointer, kw, i))));
      else if ((SCHEMA_VALUES.has(kw) || kw === "items") && isSchema(v)) d.set(kw, conv(v, join(pointer, kw)));
      else d.set(kw, v);
    }
    return d;
  };
  const schema = conv(root, "") as OMap;
  if (reachable.size) {
    schema.set("$defs", new Map([...reachable].map(([name, n]) => [name, conv(n, join("", "$defs", name))])));
  }
  out.schema = ctx.fatal ? null : schema;
  for (const [name, n] of ctx.defs) {
    if (!reachable.has(name)) {
      ctx.add("core/unused-def-pruned", "T1", {
        node: null, keyword: null, action: "dropped", severity: "info", sourcePath: n.src[0] ?? "",
        message: `unused definition ${pyRepr(name)} removed`,
      });
    }
  }
  out.entries = buildEntries(ctx, out.pointers);
  return out;
}

export function buildEntries(ctx: Ctx, pointers: Map<SNode, string>): ReportEntry[] {
  return ctx.entries.map((e) => {
    const targetPath = e.node ? (pointers.get(e.node) ?? null) : null;
    return {
      rule: e.rule,
      tid: e.tid,
      tool: ctx.tool,
      sourcePath: e.sourcePath,
      targetPath: ctx.fatal ? null : targetPath,
      instancePath: ctx.fatal ? null : instancePath(targetPath),
      keyword: e.keyword,
      action: e.action,
      severity: e.severity,
      original: e.original,
      hinted: e.hinted,
      message: e.message,
    };
  });
}

function reachableDefs(root: SNode, ctx: Ctx): Map<string, SNode> {
  const byNode = new Map<SNode, string>([...ctx.defs].map(([name, n]) => [n, name]));
  const found = new Set<string>();
  const stack: unknown[] = [root];
  const seen = new Seen();
  while (stack.length) {
    const n = stack.pop();
    if (!(n instanceof SNode) || seen.has(n)) continue;
    seen.add(n);
    if (n.ref !== null) {
      const name = byNode.get(n.ref);
      if (name !== undefined) found.add(name);
      stack.push(n.ref);
    }
    for (const [, , child] of iterSubschemas(n)) stack.push(child);
  }
  return new Map([...ctx.defs].filter(([name]) => found.has(name)));
}

function instancePath(targetPath: string | null): string | null {
  if (targetPath === null) return null;
  const tokens = split(targetPath);
  const out: string[] = [];
  let i = 0;
  while (i < tokens.length) {
    if (tokens[i] === "properties" && i + 1 < tokens.length) {
      out.push(tokens[i + 1]!);
      i += 2;
      continue;
    }
    return null;
  }
  return join("", ...out);
}

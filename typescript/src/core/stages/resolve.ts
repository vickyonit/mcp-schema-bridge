/** Stage S1: dialect detection and $ref resolution (see the Python module for the contract). */
import { type Ctx } from "../context.js";
import { InvalidInputError } from "../errors.js";
import { type OMap } from "../ojson.js";
import { decodeFragment } from "../pointer.js";
import { pyRepr } from "../pyfmt.js";
import { iterSubschemas, SCHEMA_VALUES, Seen, SNode } from "../tree.js";
import { urldefrag, urljoin } from "../url.js";
import { setChild } from "./canonicalize.js";

const DIALECTS: Record<string, string> = {
  "https://json-schema.org/draft/2020-12/schema": "2020-12",
  "http://json-schema.org/draft/2020-12/schema": "2020-12",
  "https://json-schema.org/draft/2019-09/schema": "2019-09",
  "http://json-schema.org/draft/2019-09/schema": "2019-09",
  "http://json-schema.org/draft-07/schema": "draft-07",
  "https://json-schema.org/draft-07/schema": "draft-07",
};
const DEFAULT_BASE = "urn:mcp-schema-bridge:root";
const STRIP = ["$schema", "$id", "$anchor", "$dynamicAnchor", "$recursiveAnchor", "$vocabulary"];

export function detectDialect(root: SNode): string {
  const uri = root.get("$schema");
  if (uri === undefined) return "2020-12";
  if (typeof uri !== "string") throw new InvalidInputError("$schema must be a string", "/$schema");
  const key = uri.replace(/#+$/, "");
  const d = DIALECTS[key];
  if (d === undefined) {
    throw new InvalidInputError(
      `unsupported JSON Schema dialect ${pyRepr(uri)}; supported: 2020-12, 2019-09, draft-07`,
      "/$schema",
    );
  }
  return d;
}

interface Loc {
  parent: unknown;
  key: string | number;
}

export function resolve(root: SNode, ctx: Ctx): string {
  const dialect = detectDialect(root);
  const resources = new Map<string, SNode>();
  const anchors = new Map<string, SNode>();
  const bases = new Map<SNode, string>();
  const locs = new Map<SNode, Loc>();
  let rootBase = DEFAULT_BASE;
  const rid = root.get("$id");
  if (typeof rid === "string") rootBase = urldefrag(urljoin(DEFAULT_BASE, rid))[0] || DEFAULT_BASE;
  resources.set(rootBase, root);
  if (rootBase !== DEFAULT_BASE) resources.set(DEFAULT_BASE, root);
  const akey = (base: string, a: string) => `${base}\u0000${a}`;

  const index = (node: SNode, base: string): void => {
    bases.set(node, base);
    const anchor = node.get("$anchor");
    if (typeof anchor === "string") anchors.set(akey(base, anchor), node);
    for (const [kw, key, child] of iterSubschemas(node)) {
      if (!(child instanceof SNode)) continue;
      let cbase = base;
      const cid = child.get("$id");
      if (typeof cid === "string") {
        const [url, frag] = urldefrag(urljoin(base, cid));
        if (url) {
          cbase = url;
          resources.set(url, child);
        }
        if (frag && dialect === "draft-07") anchors.set(akey(cbase, frag), child);
      }
      locs.set(child, key === null ? { parent: node, key: kw } : { parent: node.get(kw), key });
      index(child, cbase);
    }
  };
  index(root, rootBase);

  const refNodes: SNode[] = [];
  const visitRefs = (node: SNode): void => {
    for (const kw of ["$dynamicRef", "$recursiveRef"]) {
      if (node.has(kw)) {
        ctx.add("core/dynamic-ref-unsupported", "T2c", {
          node, keyword: kw, action: "rejected", severity: "fatal", original: node.get(kw),
          message: `${kw} is not supported by any target`,
        });
      }
    }
    const ref = node.get("$ref");
    if (typeof ref === "string") {
      const target = lookup(ref, bases.get(node) ?? rootBase, resources, (b, a) => anchors.get(akey(b, a)));
      if (target === null) {
        ctx.add("core/unresolvable-ref", "T2c", {
          node, keyword: "$ref", action: "rejected", severity: "fatal", original: ref,
          message: "external or unresolvable $ref (remote references are never fetched)",
        });
      } else {
        node.ref = target;
        refNodes.push(node);
      }
    }
    for (const [, , child] of iterSubschemas(node)) if (child instanceof SNode) visitRefs(child);
  };
  visitRefs(root);

  const register = (name: string, node: SNode): void => {
    let n = name;
    let i = 1;
    while (ctx.defs.has(n)) n = `${name}_${i++}`;
    ctx.defs.set(n, node);
  };
  const hoistDefMaps = (node: SNode): void => {
    for (const kw of ["$defs", "definitions"]) {
      const m = node.get(kw);
      if (m instanceof Map) {
        for (const [name, d] of m as OMap) {
          if (d instanceof SNode) {
            register(name, d);
            hoistDefMaps(d);
          }
        }
        node.delete(kw);
      }
    }
    for (const [, , child] of iterSubschemas(node)) if (child instanceof SNode) hoistDefMaps(child);
  };
  hoistDefMaps(root);
  const registered = new Set<SNode>(ctx.defs.values());
  for (const rn of refNodes) {
    const t = rn.ref!;
    if (t === root || registered.has(t)) continue;
    const loc = locs.get(t);
    register(nameFor(t, loc), t);
    registered.add(t);
    if (loc) setChild(loc.parent, loc.key, new SNode([["$ref", "#"]], [], t));
  }
  stripCore(root, ctx);
  for (const d of ctx.defs.values()) stripCore(d, ctx);
  return dialect;
}

function nameFor(node: SNode, loc: Loc | undefined): string {
  if (loc && typeof loc.key === "string" && !SCHEMA_VALUES.has(loc.key)) return loc.key;
  const src = node.src[0] ?? "";
  const tail = src ? src.slice(src.lastIndexOf("/") + 1) : "def";
  return tail || "def";
}

function lookup(
  ref: string,
  base: string,
  resources: Map<string, SNode>,
  anchor: (base: string, a: string) => SNode | undefined,
): SNode | null {
  const [url, frag] = urldefrag(urljoin(base, ref));
  const resource = resources.get(url || base);
  if (!resource) return null;
  if (frag === "") return resource;
  if (!frag.startsWith("/")) return anchor(url || base, frag) ?? null;
  let tokens: string[];
  try {
    tokens = decodeFragment(frag);
  } catch {
    return null;
  }
  let node: unknown = resource;
  for (const tok of tokens) {
    node = step(node, tok);
    if (node === undefined) return null;
  }
  return node instanceof SNode ? node : null;
}

function step(node: unknown, tok: string): unknown {
  if (node instanceof Map) return (node as OMap).get(tok);
  if (Array.isArray(node)) {
    if (!/^\d+$/.test(tok)) return undefined;
    return node[Number(tok)];
  }
  return undefined;
}

function stripCore(node: SNode, ctx: Ctx): void {
  const seen = new Seen();
  const visit = (n: SNode): void => {
    if (seen.has(n)) return;
    seen.add(n);
    for (const kw of STRIP) {
      if (n.has(kw)) {
        ctx.add("core/identity-keyword-removed", "T1", {
          node: n, keyword: kw, action: "dropped", severity: "info", original: n.get(kw),
          message: `${kw} is resolved and removed; output always uses 2020-12 semantics`,
        });
        n.delete(kw);
      }
    }
    for (const [, , child] of iterSubschemas(n)) if (child instanceof SNode) visit(child);
  };
  visit(node);
}

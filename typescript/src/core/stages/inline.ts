/** Stage S4: recursion analysis and inlining (T2a, T2b) plus root $ref inlining. Port of inline.py. */
import { type Ctx } from "../context.js";
import { keywordKind } from "../rules.js";
import { copyTree, iterSubschemas, SNode, toOrdered } from "../tree.js";
import { setChild } from "./canonicalize.js";
import { mergeInto } from "./merge.js";

interface Ref {
  node: SNode;
  owner: SNode;
  breakable: boolean;
}
type PathStep = [parent: SNode, kw: string, key: string | number | null];

export function inlineStage(root: SNode, ctx: Ctx): void {
  inlineRootRef(root, ctx);
  const refs = collectRefs(root, ctx);
  const cyclic = cyclicTargets(refs);
  rejectUnsatisfiable(refs, ctx);
  if (!ctx.rules.features.ref_siblings) inlineRefSiblings(refs, cyclic, ctx);
  if (ctx.rules.features.recursion === "none" && cyclic.size) unroll(root, ctx, cyclic);
}

function replaceContents(node: SNode, body: SNode): void {
  node.clear();
  for (const [k, v] of body) node.set(k, v);
  node.ref = body.ref;
  node.src = [...new Set([...node.src, ...body.src])];
  node.kwSrc = new Map(body.kwSrc);
}

function inlineRootRef(root: SNode, ctx: Ctx): void {
  if (root.ref === null) return;
  const siblings = new SNode([...root].filter(([k]) => k !== "$ref"), root.src);
  const body = copyTree(root.ref);
  if (siblings.size) mergeInto(body, siblings, ctx);
  ctx.add("core/root-ref-inlined", "T2b", {
    node: root, keyword: "$ref", action: "inlined", severity: "info", original: root.get("$ref"),
    message: "root $ref replaced by its target",
  });
  replaceContents(root, body);
}

const nullable = (node: SNode): boolean => {
  const t = node.get("type");
  return t === "null" || (Array.isArray(t) && t.includes("null"));
};

function collectRefs(root: SNode, ctx: Ctx): Ref[] {
  const out: Ref[] = [];
  const visit = (node: SNode, owner: SNode, breakableIn: boolean): void => {
    const breakable = breakableIn || nullable(node);
    if (node.ref !== null) out.push({ node, owner, breakable });
    const required = new Set((node.get("required") as string[] | undefined) ?? []);
    const minItems = (node.get("minItems") as number | undefined) ?? 0;
    for (const [kw, key, child] of iterSubschemas(node)) {
      if (!(child instanceof SNode)) continue;
      let step: boolean;
      if (kw === "properties") step = !required.has(key as string);
      else if (kw === "items") step = minItems === 0;
      else if (kw === "prefixItems") step = minItems <= (key as number);
      else if (kw === "anyOf" || kw === "oneOf") step = (node.get(kw) as unknown[]).length > 1;
      else if (kw === "allOf" || kw === "contains") step = false;
      else step = true;
      visit(child, owner, breakable || step);
    }
  };
  for (const tree of [root, ...ctx.defs.values()]) visit(tree, tree, false);
  return out;
}

function reach(edges: Map<SNode, Set<SNode>>, start: SNode): Set<SNode> {
  const seen = new Set<SNode>();
  const stack = [start];
  while (stack.length) {
    const n = stack.pop()!;
    for (const m of edges.get(n) ?? []) {
      if (!seen.has(m)) {
        seen.add(m);
        stack.push(m);
      }
    }
  }
  return seen;
}

function addEdge(edges: Map<SNode, Set<SNode>>, a: SNode, b: SNode): void {
  const s = edges.get(a) ?? new Set<SNode>();
  s.add(b);
  edges.set(a, s);
}

function cyclicTargets(refs: Ref[]): Set<SNode> {
  const edges = new Map<SNode, Set<SNode>>();
  for (const r of refs) addEdge(edges, r.owner, r.node.ref!);
  return new Set([...new Set(refs.map((r) => r.node.ref!))].filter((t) => reach(edges, t).has(t)));
}

function rejectUnsatisfiable(refs: Ref[], ctx: Ctx): void {
  const edges = new Map<SNode, Set<SNode>>();
  for (const r of refs) if (!r.breakable) addEdge(edges, r.owner, r.node.ref!);
  for (const r of refs) {
    const t = r.node.ref!;
    if (!r.breakable && (reach(edges, t).has(r.owner) || t === r.owner)) {
      ctx.add("core/unsatisfiable-recursion", "T2a", {
        node: r.node, keyword: "$ref", action: "rejected", severity: "fatal", original: r.node.get("$ref"),
        message: "recursion only through required, non-nullable positions; no finite value exists",
      });
    }
  }
}

function inlineRefSiblings(refs: Ref[], cyclic: Set<SNode>, ctx: Ctx): void {
  for (const r of refs) {
    const node = r.node;
    const siblings = [...node].filter(([k]) => k !== "$ref");
    if (!siblings.length) continue;
    const target = node.ref!;
    if (cyclic.has(target)) {
      for (const [kw, v] of siblings) {
        const lossy = ["validation", "applicator"].includes(keywordKind(kw));
        ctx.add("core/ref-sibling-dropped", "T2b", {
          node, keyword: kw, action: "dropped", severity: lossy ? "lossy" : "info", original: toOrdered(v), hint: lossy,
          message: "target forbids keywords next to $ref and the reference is recursive",
        });
        node.delete(kw);
      }
      continue;
    }
    const body = copyTree(target);
    mergeInto(body, new SNode(siblings, node.src), ctx);
    ctx.add("core/ref-with-siblings-inlined", "T2b", {
      node, keyword: "$ref", action: "inlined", severity: "info", original: node.get("$ref"),
      message: "target forbids keywords next to $ref; reference inlined",
    });
    replaceContents(node, body);
  }
}

function unroll(root: SNode, ctx: Ctx, cyclic: Set<SNode>): void {
  const limit = ctx.opts.maxRefDepth;
  for (const tree of [root, ...[...ctx.defs.values()].filter((d) => !cyclic.has(d))]) {
    unrollNode(tree, ctx, cyclic, new Map(), [], limit);
  }
}

function unrollNode(node: SNode, ctx: Ctx, cyclic: Set<SNode>, depth: Map<SNode, number>, parents: PathStep[], limit: number): void {
  for (const [kw, key, child] of [...iterSubschemas(node)]) {
    if (!(child instanceof SNode)) continue;
    const path: PathStep[] = [...parents, [node, kw, key]];
    const target = child.ref;
    if (target !== null && cyclic.has(target)) {
      const d = depth.get(target) ?? 0;
      if (d >= limit) {
        cut(child, path, ctx);
        continue;
      }
      const body = copyTree(target);
      const siblings = [...child].filter(([k]) => k !== "$ref");
      if (siblings.length) mergeInto(body, new SNode(siblings, child.src), ctx);
      if (key === null) node.set(kw, body);
      else setChild(node.get(kw), key, body);
      unrollNode(body, ctx, cyclic, new Map([...depth, [target, d + 1]]), path, limit);
    } else {
      unrollNode(child, ctx, cyclic, depth, path, limit);
    }
  }
}

function cut(ref: SNode, path: PathStep[], ctx: Ctx): void {
  const entry = (lossy: boolean, message: string): void => {
    ctx.add("core/recursion-truncated", "T2a", {
      node: null, keyword: null, action: lossy ? "truncated" : "rejected", severity: lossy ? "lossy" : "fatal",
      sourcePath: ref.src[0] ?? "", message,
    });
  };
  const depth = ctx.opts.maxRefDepth;
  for (const [parent, kw, key] of [...path].reverse()) {
    if (kw === "properties" && !((parent.get("required") as string[] | undefined) ?? []).includes(key as string)) {
      (parent.get("properties") as Map<string, unknown>).delete(key as string);
      entry(true, `recursion cut at depth ${depth}: optional property removed`);
      return;
    }
    if ((kw === "anyOf" || kw === "oneOf") && (parent.get(kw) as unknown[]).length > 1) {
      (parent.get(kw) as unknown[]).splice(key as number, 1);
      entry(true, `recursion cut at depth ${depth}: union branch removed`);
      return;
    }
  }
  entry(false, "recursion cannot be cut safely for a target without recursion support");
}

/** Stage S10: description hints (spec/hint-format.md). Port of hints.py (lengths in code points). */
import { type Ctx, type PendingEntry } from "../context.js";
import { canonicalize, utf16Compare } from "../jcs.js";
import { iterSubschemas, Seen, SNode } from "../tree.js";

export const MAX_VALUE_CHARS = 200;
// Python semantics: `.` excludes only \n; `$` also matches before one trailing newline.
const HINT_RE = /^(?:([\s\S]*)\n\n)?\[constraints: ([^\n]*)\]\n?$/;

const cpLen = (s: string): number => [...s].length;
const cpSlice = (s: string, n: number): string => [...s].slice(0, n).join("");

export function formatValue(value: unknown): string {
  const enc = canonicalize(value);
  return cpLen(enc) > MAX_VALUE_CHARS ? cpSlice(enc, MAX_VALUE_CHARS - 1) + "…" : enc;
}

export function splitHint(description: string): [string | null, string[]] {
  const m = HINT_RE.exec(description);
  if (m === null) return [description, []];
  const body = m[2]!;
  const entries = body ? body.split("; ") : [];
  if (!entries.every((e) => e.includes("="))) return [description, []];
  return [m[1] ?? null, entries];
}

export function render(text: string | null, entries: string[]): string {
  const part = (e: string): [string, string] => {
    const i = e.indexOf("=");
    return [e.slice(0, i), e.slice(i + 1)];
  };
  const sorted = [...new Set(entries)].sort((a, b) => {
    const [ka, va] = part(a);
    const [kb, vb] = part(b);
    return utf16Compare(ka, kb) || utf16Compare(va, vb);
  });
  const block = "[constraints: " + sorted.join("; ") + "]";
  return text ? `${text}\n\n${block}` : block;
}

export function hintsStage(root: SNode, ctx: Ctx): void {
  if (ctx.opts.maxDescriptionChars !== null) truncateDescriptions(root, ctx, ctx.opts.maxDescriptionChars);
  if (!ctx.opts.hints) return;
  const byNode = new Map<SNode, PendingEntry[]>();
  for (const e of ctx.entries) {
    if (!e.wantHint || e.node === null) continue;
    if (e.node.ref !== null && !ctx.rules.features.ref_siblings) continue;
    byNode.set(e.node, [...(byNode.get(e.node) ?? []), e]);
  }
  for (const [node, entries] of byNode) {
    const desc = node.get("description");
    const [text, existing] = typeof desc === "string" ? splitHint(desc) : [null, []];
    const fresh = entries.filter((e) => e.keyword).map((e) => `${e.keyword}=${formatValue(e.original)}`);
    node.set("description", render(text, [...existing, ...fresh]));
    for (const e of entries) e.hinted = true;
  }
}

function truncateDescriptions(root: SNode, ctx: Ctx, limit: number): void {
  const seen = new Seen();
  const visit = (node: SNode): void => {
    if (seen.has(node)) return;
    seen.add(node);
    const desc = node.get("description");
    if (typeof desc === "string") {
      const [text, hint] = splitHint(desc);
      if (text !== null && cpLen(text) > limit) {
        const cut = cpSlice(text, Math.max(limit - 1, 0)) + "…";
        node.set("description", hint.length ? render(cut, hint) : cut);
        ctx.add("core/description-truncated", "T1", {
          node, keyword: "description", action: "truncated", severity: "info", original: desc,
          message: `description truncated to ${limit} characters`,
        });
      }
    }
    for (const [, , child] of [...iterSubschemas(node)]) if (child instanceof SNode) visit(child);
  };
  for (const tree of [root, ...ctx.defs.values()]) visit(tree);
}

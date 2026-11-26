"""Stage S4: recursion analysis and inlining (T2a, T2b) plus root $ref inlining."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from mcp_schema_bridge.core.context import Ctx
from mcp_schema_bridge.core.rules import keyword_classes
from mcp_schema_bridge.core.stages.merge import merge_into
from mcp_schema_bridge.core.tree import SNode, copy_tree, iter_subschemas, to_plain


@dataclass
class _Ref:
    node: SNode
    owner: SNode
    breakable: bool


def inline_stage(root: SNode, ctx: Ctx) -> None:
    _inline_root_ref(root, ctx)
    refs = _collect_refs(root, ctx)
    cyclic = _cyclic_targets(refs)
    _reject_unsatisfiable(refs, ctx)
    if not ctx.rules.features.ref_siblings:
        _inline_ref_siblings(refs, cyclic, ctx)
    if ctx.rules.features.recursion == "none" and cyclic:
        _unroll(root, ctx, cyclic)


# --- root ---------------------------------------------------------------------------------------


def _inline_root_ref(root: SNode, ctx: Ctx) -> None:
    if root.ref is None:
        return
    target = root.ref
    siblings = SNode({k: v for k, v in root.items() if k != "$ref"}, src=root.src)
    body = copy_tree(target)
    if not isinstance(body, SNode):
        return
    if siblings:
        merge_into(body, siblings, ctx)
    ctx.add(
        "core/root-ref-inlined",
        "T2b",
        node=root,
        keyword="$ref",
        action="inlined",
        severity="info",
        original=root.get("$ref"),
        message="root $ref replaced by its target",
    )
    root.clear()
    root.update(body)
    root.ref = body.ref
    root.src = tuple(dict.fromkeys((*root.src, *body.src)))
    root.kw_src = dict(body.kw_src)


# --- analysis -----------------------------------------------------------------------------------


def _nullable(node: SNode) -> bool:
    t = node.get("type")
    return t == "null" or (isinstance(t, list) and "null" in t)


def _collect_refs(root: SNode, ctx: Ctx) -> list[_Ref]:
    out: list[_Ref] = []

    def visit(node: SNode, owner: SNode, breakable: bool) -> None:
        breakable = breakable or _nullable(node)
        if node.ref is not None:
            out.append(_Ref(node, owner, breakable))
        required = set(cast(list[str], node.get("required") or []))
        min_items = node.get("minItems", 0)
        for kw, key, child in iter_subschemas(node):
            if not isinstance(child, SNode):
                continue
            if kw == "properties":
                step = key not in required
            elif kw == "items":  # tuple form was canonicalized to prefixItems in S2
                step = min_items == 0
            elif kw == "prefixItems":
                step = min_items <= cast(int, key)
            elif kw in ("anyOf", "oneOf"):
                step = len(cast(list[Any], node[kw])) > 1
            elif kw in ("allOf", "contains"):
                step = False
            else:
                step = True
            visit(child, owner, breakable or step)

    for tree in [root, *ctx.defs.values()]:
        visit(tree, tree, False)
    return out


def _reach(edges: dict[int, set[int]], start: int) -> set[int]:
    seen: set[int] = set()
    stack = [start]
    while stack:
        n = stack.pop()
        for m in edges.get(n, set()):
            if m not in seen:
                seen.add(m)
                stack.append(m)
    return seen


def _cyclic_targets(refs: list[_Ref]) -> set[int]:
    edges: dict[int, set[int]] = {}
    for r in refs:
        assert r.node.ref is not None
        edges.setdefault(id(r.owner), set()).add(id(r.node.ref))
    return {t for t in {id(cast(SNode, r.node.ref)) for r in refs} if t in _reach(edges, t)}


def _reject_unsatisfiable(refs: list[_Ref], ctx: Ctx) -> None:
    edges: dict[int, set[int]] = {}
    for r in refs:
        if not r.breakable:
            edges.setdefault(id(r.owner), set()).add(id(cast(SNode, r.node.ref)))
    for r in refs:
        t = id(cast(SNode, r.node.ref))
        if not r.breakable and id(r.owner) in _reach(edges, t) | (
            {t} if t == id(r.owner) else set()
        ):
            ctx.add(
                "core/unsatisfiable-recursion",
                "T2a",
                node=r.node,
                keyword="$ref",
                action="rejected",
                severity="fatal",
                original=r.node.get("$ref"),
                message="recursion only through required, non-nullable positions; no finite value exists",
            )


# --- T2b ----------------------------------------------------------------------------------------


def _inline_ref_siblings(refs: list[_Ref], cyclic: set[int], ctx: Ctx) -> None:
    kc = keyword_classes()
    for r in refs:
        node = r.node
        siblings = {k: v for k, v in node.items() if k != "$ref"}
        if not siblings:
            continue
        target = cast(SNode, node.ref)
        if id(target) in cyclic:
            for kw, v in siblings.items():
                lossy = kc.kind(kw) in ("validation", "applicator")
                ctx.add(
                    "core/ref-sibling-dropped",
                    "T2b",
                    node=node,
                    keyword=kw,
                    action="dropped",
                    severity="lossy" if lossy else "info",
                    original=to_plain(v),
                    hint=lossy,
                    message="target forbids keywords next to $ref and the reference is recursive",
                )
                del node[kw]
            continue
        body = copy_tree(target)
        if not isinstance(body, SNode):
            continue
        merge_into(body, SNode(siblings, src=node.src), ctx)
        ctx.add(
            "core/ref-with-siblings-inlined",
            "T2b",
            node=node,
            keyword="$ref",
            action="inlined",
            severity="info",
            original=node.get("$ref"),
            message="target forbids keywords next to $ref; reference inlined",
        )
        node.clear()
        node.update(body)
        node.ref = body.ref
        node.src = tuple(dict.fromkeys((*node.src, *body.src)))
        node.kw_src = dict(body.kw_src)


# --- T2a ----------------------------------------------------------------------------------------


def _unroll(root: SNode, ctx: Ctx, cyclic: set[int]) -> None:
    limit = ctx.opts.max_ref_depth
    trees = [root, *(d for d in ctx.defs.values() if id(d) not in cyclic)]
    for tree in trees:
        _unroll_node(tree, ctx, cyclic, {}, [], limit)


def _unroll_node(
    node: SNode,
    ctx: Ctx,
    cyclic: set[int],
    depth: dict[int, int],
    parents: list[tuple[SNode, str, str | int | None]],
    limit: int,
) -> None:
    for kw, key, child in list(iter_subschemas(node)):
        if not isinstance(child, SNode):
            continue
        path = [*parents, (node, kw, key)]
        target = child.ref
        if target is not None and id(target) in cyclic:
            d = depth.get(id(target), 0)
            if d >= limit:
                _cut(child, path, ctx)
                continue
            body = copy_tree(target)
            assert isinstance(body, SNode)
            siblings = {k: v for k, v in child.items() if k != "$ref"}
            if siblings:
                merge_into(body, SNode(siblings, src=child.src), ctx)
            _replace(node, kw, key, body)
            _unroll_node(body, ctx, cyclic, {**depth, id(target): d + 1}, path, limit)
        else:
            _unroll_node(child, ctx, cyclic, depth, path, limit)


def _replace(parent: SNode, kw: str, key: str | int | None, new: Any) -> None:
    if key is None:
        parent[kw] = new
    else:
        parent[kw][key] = new


def _cut(ref: SNode, path: list[tuple[SNode, str, str | int | None]], ctx: Ctx) -> None:
    def entry(severity: str, message: str) -> None:
        ctx.add(
            "core/recursion-truncated",
            "T2a",
            node=None,
            keyword=None,
            action="truncated" if severity == "lossy" else "rejected",
            severity="lossy" if severity == "lossy" else "fatal",
            source_path=ref.src[0] if ref.src else "",
            message=message,
        )

    depth = ctx.opts.max_ref_depth
    for parent, kw, key in reversed(path):
        if kw == "properties" and key not in cast(list[str], parent.get("required") or []):
            del parent["properties"][key]
            entry("lossy", f"recursion cut at depth {depth}: optional property removed")
            return
        if kw in ("anyOf", "oneOf") and len(parent[kw]) > 1:
            del parent[kw][cast(int, key)]
            entry("lossy", f"recursion cut at depth {depth}: union branch removed")
            return
    entry("fatal", "recursion cannot be cut safely for a target without recursion support")

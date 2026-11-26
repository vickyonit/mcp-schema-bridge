"""Stage S2: dialect-independent canonical form (equivalent rewrites, reported as info)."""

from __future__ import annotations

from typing import Any, cast

from mcp_schema_bridge.core.context import Ctx
from mcp_schema_bridge.core.pointer import join
from mcp_schema_bridge.core.tree import Seen, SNode, iter_subschemas

_BOOL_KEEP = {
    "additionalProperties",
    "items",
    "unevaluatedProperties",
    "unevaluatedItems",
    "additionalItems",
}
_D7_KEEP_WITH_REF = {"$ref", "$comment"}


def canonicalize_tree(root: SNode, ctx: Ctx, dialect: str) -> None:
    seen = Seen()
    for tree in [root, *ctx.defs.values()]:
        _visit(tree, ctx, dialect, seen)


def _visit(node: SNode, ctx: Ctx, dialect: str, seen: Seen) -> None:
    if node in seen:
        return
    seen.add(node)
    if dialect == "draft-07" and "$ref" in node:
        _drop_draft07_ref_siblings(node, ctx)
    _tuple_items(node, ctx)
    _dependencies(node, ctx)
    _nullable(node, ctx)
    if not ctx.rules.features.boolean_subschemas:
        _booleans(node, ctx)
    for _, _, child in list(iter_subschemas(node)):
        if isinstance(child, SNode):
            _visit(child, ctx, dialect, seen)


def _drop_draft07_ref_siblings(node: SNode, ctx: Ctx) -> None:
    for kw in [k for k in node if k not in _D7_KEEP_WITH_REF]:
        ctx.add(
            "core/draft07-ref-sibling-ignored",
            "T3",
            node=node,
            keyword=kw,
            action="dropped",
            severity="info",
            original=node[kw],
            message="draft-07 ignores keywords next to $ref",
        )
        del node[kw]


def _tuple_items(node: SNode, ctx: Ctx) -> None:
    items = node.get("items")
    if not isinstance(items, list):
        return
    tail = node.pop("additionalItems", None)
    rebuilt: dict[str, Any] = {}
    for k, v in node.items():
        if k == "items":
            rebuilt["prefixItems"] = v
            if tail is not None:
                rebuilt["items"] = tail
        else:
            rebuilt[k] = v
    node.clear()
    node.update(rebuilt)
    ctx.add(
        "core/tuple-items-to-prefix-items",
        "T3",
        node=node,
        keyword="items",
        action="rewritten",
        severity="info",
        message="array-form items rewritten to prefixItems (2020-12)",
    )


def _dependencies(node: SNode, ctx: Ctx) -> None:
    deps = node.get("dependencies")
    if not isinstance(deps, dict):
        return
    req: dict[str, Any] = {}
    sch: dict[str, Any] = {}
    for k, v in cast(dict[str, Any], deps).items():
        (req if isinstance(v, list) else sch)[k] = v
    rebuilt: dict[str, Any] = {}
    for k, v in node.items():
        if k == "dependencies":
            if req:
                rebuilt["dependentRequired"] = req
            if sch:
                rebuilt["dependentSchemas"] = sch
        else:
            rebuilt[k] = v
    node.clear()
    node.update(rebuilt)
    ctx.add(
        "core/dependencies-split",
        "T3",
        node=node,
        keyword="dependencies",
        action="rewritten",
        severity="info",
        message="draft-07 dependencies split into dependentRequired / dependentSchemas",
    )


def _nullable(node: SNode, ctx: Ctx) -> None:
    if "nullable" not in node:
        return
    flag = node.pop("nullable")
    t = node.get("type")
    if flag is True and t is not None:
        types = [t] if isinstance(t, str) else list(cast(list[Any], t))
        if "null" not in types:
            types.append("null")
        node["type"] = types
    ctx.add(
        "core/openapi-nullable",
        "T3",
        node=node,
        keyword="nullable",
        action="rewritten" if flag is True else "dropped",
        severity="info",
        original=flag,
        message="OpenAPI nullable folded into the JSON Schema type array",
    )


def _booleans(node: SNode, ctx: Ctx) -> None:
    for kw, key, child in list(iter_subschemas(node)):
        if not isinstance(child, bool) or (key is None and kw in _BOOL_KEEP):
            continue
        ptr_src = node.src[0] if node.src else ""
        ptr = join(ptr_src, kw) if key is None else join(ptr_src, kw, key)
        new = SNode(src=(ptr,)) if child else SNode({"not": SNode(src=())}, src=(ptr,))
        container = node[kw]
        if key is None:
            node[kw] = new
        else:
            container[key] = new
        ctx.add(
            "core/boolean-subschema",
            "T3",
            node=new,
            keyword=None if child else "not",
            action="rewritten",
            severity="info",
            source_path=ptr,
            original=child,
            message="boolean subschema rewritten as an equivalent object schema",
        )

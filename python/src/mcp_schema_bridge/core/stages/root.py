"""Stage S5 / T14: make the root a plain object the target accepts."""

from __future__ import annotations

from typing import Any, cast

from mcp_schema_bridge.core.context import Ctx
from mcp_schema_bridge.core.tree import SNode, walk


def _type_set(node: SNode) -> set[str] | None:
    t = node.get("type")
    if t is None:
        return None
    if isinstance(t, str):
        return {t}
    return {x for x in cast(list[Any], t) if isinstance(x, str)}


def apply_root(root: SNode, ctx: Ctx) -> SNode:
    f = ctx.rules.features
    types = _type_set(root)
    has_union = "anyOf" in root or "oneOf" in root
    objectish = types is not None and "object" in types

    if types is not None and "object" in types and len(types) > 1:
        root["type"] = "object"
        ctx.add(
            "core/root-type-narrowed",
            "T14",
            node=root,
            keyword="type",
            action="narrowed",
            severity="info",
            original=sorted(types),
            message="MCP tool arguments are always objects; non-object root types removed",
        )
        types = {"object"}

    non_object = types is not None and "object" not in types
    union_root = has_union and types is None and "properties" not in root
    needs_wrap = (
        non_object
        or (union_root and not f.root_union)
        or (has_union and objectish and not f.root_anyof_with_object)
    )
    if needs_wrap:
        return _wrap(root, ctx)

    if types is None and f.root_type_object_required and not union_root:
        root["type"] = "object"
        ctx.add(
            "core/root-type-object-added",
            "T14",
            node=root,
            keyword="type",
            action="narrowed",
            severity="info",
            message="root declared no type; added type: object (MCP tool arguments are objects)",
        )
    return root


def _wrap(root: SNode, ctx: Ctx) -> SNode:
    referenced = any(n.ref is root for d in [root, *ctx.defs.values()] for _, n in walk(d))
    inner: SNode = root
    if referenced:
        name = _unique_name("__root", ctx)
        ctx.defs[name] = root
        inner = SNode({"$ref": "#"}, src=(), ref=root)
    wrapper = SNode(
        {"type": "object", "properties": {"value": inner}, "required": ["value"]},
        src=(),
    )
    wrapper.ops.append({"op": "unwrap_root"})
    ctx.add(
        "core/root-wrapped",
        "T14",
        node=root,
        keyword="type",
        action="wrapped",
        severity="reversible",
        message="root is not a plain object for this target; wrapped as {value: ...}",
    )
    return wrapper


def _unique_name(base: str, ctx: Ctx) -> str:
    name, i = base, 1
    while name in ctx.defs:
        name = f"{base}_{i}"
        i += 1
    return name

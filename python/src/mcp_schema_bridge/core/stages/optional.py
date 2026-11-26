"""Stage S8 / T11: optional properties -> required + nullable (targets with all_required)."""

from __future__ import annotations

from typing import Any, cast

from mcp_schema_bridge.core.context import Ctx
from mcp_schema_bridge.core.tree import SNode, iter_subschemas


def accepts_null(s: Any, seen: frozenset[int] = frozenset()) -> bool:
    """True if ``null`` is valid against the (resolved) schema."""
    if isinstance(s, bool):
        return s
    if not isinstance(s, SNode):
        return True
    if s.ref is not None:
        if id(s.ref) in seen:
            return False
        if not accepts_null(s.ref, seen | {id(s.ref)}):
            return False
    t = s.get("type")
    if t is not None and not (t == "null" or (isinstance(t, list) and "null" in t)):
        return False
    if "const" in s and s["const"] is not None:
        return False
    if "enum" in s and None not in cast(list[Any], s["enum"]):
        return False
    for kw in ("anyOf", "oneOf"):
        if kw in s and not any(accepts_null(b, seen) for b in cast(list[Any], s[kw])):
            return False
    return all(accepts_null(b, seen) for b in cast(list[Any], s.get("allOf") or []))


def optional_stage(root: SNode, ctx: Ctx) -> None:
    if not ctx.rules.features.all_required:
        return
    seen: set[int] = set()
    for tree in [root, *ctx.defs.values()]:
        _visit(tree, ctx, seen)


def _visit(node: SNode, ctx: Ctx, seen: set[int]) -> None:
    if id(node) in seen:
        return
    seen.add(id(node))
    for _, _, child in list(iter_subschemas(node)):
        if isinstance(child, SNode):
            _visit(child, ctx, seen)
    props = node.get("properties")
    if not isinstance(props, dict) or not props:
        return
    p = cast(dict[str, Any], props)
    required = list(cast(list[str], node.get("required") or []))
    missing = [n for n in p if n not in required]
    if not missing:
        return
    for name in missing:
        sub = p[name]
        if accepts_null(sub):
            ctx.add(
                ctx.rule_id("optional-nullable-ambiguous"),
                "T11b",
                node=sub if isinstance(sub, SNode) else node,
                keyword="required",
                action="rewritten",
                severity="lossy",
                source_path=_src(sub, node),
                message=f"optional property {name!r} already accepts null; once required, "
                "'omitted' and 'null' can no longer be distinguished",
            )
            continue
        p[name] = _inject_null(sub, name, node, ctx)
        node.ops.append({"op": "drop_injected_null", "property": name})
    node["required"] = required + missing


def _src(sub: Any, parent: SNode) -> str:
    if isinstance(sub, SNode) and sub.src:
        return sub.src[0]
    return parent.src[0] if parent.src else ""


def _entry(ctx: Ctx, node: SNode, keyword: str, name: str, original: Any = None) -> None:
    for origin in node.origins(keyword):
        ctx.add(
            ctx.rule_id("optional-to-nullable"),
            "T11a",
            node=node,
            keyword=keyword,
            action="rewritten",
            severity="reversible",
            original=original,
            source_path=origin,
            message=f"optional property {name!r} made required and nullable; null is removed "
            "again by denormalize_args",
        )


def _inject_null(sub: Any, name: str, parent: SNode, ctx: Ctx) -> Any:
    if (
        not isinstance(sub, SNode)
        or sub.ref is not None
        or ("type" not in sub and "anyOf" not in sub)
    ):
        wrapper = SNode({"anyOf": [sub, SNode({"type": "null"}, src=())]}, src=())
        if isinstance(sub, SNode):
            for k in ("description", "title"):
                if k in sub and sub.ref is not None:
                    wrapper[k] = sub.pop(k)
        ctx.add(
            ctx.rule_id("optional-to-nullable"),
            "T11a",
            node=wrapper,
            keyword="anyOf",
            action="rewritten",
            severity="reversible",
            source_path=_src(sub, parent),
            message=f"optional property {name!r} made required and nullable (anyOf with null); "
            "null is removed again by denormalize_args",
        )
        return wrapper
    if "anyOf" in sub and "type" not in sub:
        sub["anyOf"].append(SNode({"type": "null"}, src=()))
        _entry(ctx, sub, "anyOf", name)
        return sub
    t = sub["type"]
    types = [t] if isinstance(t, str) else list(cast(list[str], t))
    sub["type"] = [*types, "null"]
    _entry(ctx, sub, "type", name, original=t)
    if "enum" in sub:
        original = list(cast(list[Any], sub["enum"]))
        sub["enum"] = [*original, None]
        _entry(ctx, sub, "enum", name, original=original)
    if "const" in sub:
        c = sub.pop("const")
        sub["enum"] = [c, None]
        _entry(ctx, sub, "const", name, original=c)
    return sub

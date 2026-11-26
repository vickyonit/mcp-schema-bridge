"""Stage S6: union shaping.

Order within the stage (per node, children first): T8 oneOf->anyOf, T5 enum/const typing and
const->enum, T4 multi-type split, T9 distribution of anyOf siblings into branches.
"""

from __future__ import annotations

from typing import Any, cast

from mcp_schema_bridge.core.context import Ctx
from mcp_schema_bridge.core.jcs import canonicalize
from mcp_schema_bridge.core.rules import keyword_classes
from mcp_schema_bridge.core.stages.merge import union_product
from mcp_schema_bridge.core.tree import Seen, SNode, copy_tree, iter_subschemas, to_plain

TYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "string": (
        "minLength",
        "maxLength",
        "pattern",
        "format",
        "contentEncoding",
        "contentMediaType",
    ),
    "number": ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf"),
    "integer": ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf"),
    "array": (
        "items",
        "prefixItems",
        "minItems",
        "maxItems",
        "uniqueItems",
        "contains",
        "minContains",
        "maxContains",
        "unevaluatedItems",
    ),
    "object": (
        "properties",
        "required",
        "additionalProperties",
        "patternProperties",
        "propertyNames",
        "minProperties",
        "maxProperties",
        "dependentRequired",
        "dependentSchemas",
        "unevaluatedProperties",
    ),
    "boolean": (),
    "null": (),
}


def json_type(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return "integer"
    if isinstance(v, float):
        return "integer" if v.is_integer() else "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    return "object"


def unions_stage(root: SNode, ctx: Ctx) -> None:
    seen = Seen()
    for tree in [root, *ctx.defs.values()]:
        _visit(tree, ctx, seen)


def _visit(node: SNode, ctx: Ctx, seen: Seen) -> None:
    if node in seen:
        return
    seen.add(node)
    for _, _, child in list(iter_subschemas(node)):
        if isinstance(child, SNode):
            _visit(child, ctx, seen)
    f = ctx.rules.features
    if "oneOf" in node and not f.oneof:
        _t8(node, ctx)
    if ctx.rules.strict or f.enum_values == "primitive":
        _t5_type(node, ctx)
    _const_to_enum(node, ctx)
    if not f.multi_type_arrays or (not f.multi_type_enum and ("enum" in node or "const" in node)):
        _t4(node, ctx)
    if not f.anyof_validation_siblings and "anyOf" in node:
        _t9(node, ctx)
    # Branches created by the rewrites above have not been shaped yet.
    for b in cast(list[Any], node.get("anyOf") or []):
        if isinstance(b, SNode) and b not in seen:
            _visit(b, ctx, seen)


# --- T8 -----------------------------------------------------------------------------------------


def _type_set(b: Any) -> set[str] | None:
    if not isinstance(b, SNode) or b.ref is not None:
        return None
    t = b.get("type")
    if t is None:
        if "const" in b:
            return {json_type(b["const"])}
        return None
    s = {t} if isinstance(t, str) else set(cast(list[str], t))
    if "number" in s:
        s.add("integer")
    return s


def _values(b: Any) -> set[str] | None:
    if not isinstance(b, SNode):
        return None
    if "const" in b:
        return {canonicalize(b["const"])}
    if "enum" in b:
        return {canonicalize(v) for v in cast(list[Any], b["enum"])}
    return None


def _pairwise_disjoint(sets: list[set[str] | None]) -> bool:
    if any(s is None for s in sets):
        return False
    seen: set[str] = set()
    for s in cast(list[set[str]], sets):
        if seen & s:
            return False
        seen |= s
    return True


def _discriminated(branches: list[Any]) -> bool:
    if not all(isinstance(b, SNode) for b in branches):
        return False
    common: set[str] | None = None
    for b in cast(list[SNode], branches):
        props = cast(dict[str, Any], b.get("properties") or {})
        req = set(cast(list[str], b.get("required") or []))
        keys = {k for k, v in props.items() if k in req and _values(v) is not None}
        common = keys if common is None else common & keys
    for k in common or set():
        if _pairwise_disjoint([_values(cast(SNode, b)["properties"][k]) for b in branches]):
            return True
    return False


def disjoint(branches: list[Any]) -> bool:
    return (
        _pairwise_disjoint([_type_set(b) for b in branches])
        or _pairwise_disjoint([_values(b) for b in branches])
        or _discriminated(branches)
    )


def _t8(node: SNode, ctx: Ctx) -> None:
    origins = node.origins("oneOf")
    branches = cast(list[Any], node.pop("oneOf"))
    node.kw_src.pop("oneOf", None)
    exclusive = disjoint(branches)
    if "anyOf" in node:
        existing = cast(list[Any], node.pop("anyOf"))
        node["anyOf"] = _product(existing, branches, node, ctx)
    else:
        node["anyOf"] = branches
    for origin in origins:
        ctx.add(
            "core/oneof-to-anyof",
            "T8",
            node=node,
            keyword="oneOf",
            action="rewritten",
            severity="info" if exclusive else "lossy",
            source_path=origin,
            message="oneOf rewritten to anyOf"
            + (
                "; branches are disjoint so meaning is unchanged"
                if exclusive
                else "; exclusivity is no longer enforced"
            ),
        )


def _product(left: list[Any], right: list[Any], node: SNode, ctx: Ctx) -> list[Any]:
    return union_product(left, right, node, ctx, "T9")


# --- T5 / const->enum ---------------------------------------------------------------------------


def _t5_type(node: SNode, ctx: Ctx) -> None:
    if "type" in node or ("enum" not in node and "const" not in node) or node.ref is not None:
        return
    kw = "const" if "const" in node else "enum"
    values: list[Any] = [node["const"]] if kw == "const" else list(cast(list[Any], node["enum"]))
    if ctx.rules.features.enum_values == "primitive" and any(
        isinstance(v, dict | list) for v in values
    ):
        ctx.add(
            "core/non-primitive-enum",
            "T5",
            node=node,
            keyword=kw,
            action="dropped",
            severity="lossy",
            original=to_plain(node[kw]),
            hint=True,
            message="target only allows primitive enum/const values",
        )
        del node[kw]
        return
    by_type: dict[str, list[Any]] = {}
    for v in values:
        t = json_type(v)
        if t == "integer" and any(json_type(x) == "number" for x in values):
            t = "number"
        by_type.setdefault(t, []).append(v)
    non_null = [t for t in by_type if t != "null"]
    if len(non_null) <= 1:
        types = non_null + (["null"] if "null" in by_type else [])
        if not types:
            return
        node["type"] = types[0] if len(types) == 1 else types
        ctx.add(
            "core/enum-type-inferred",
            "T5",
            node=node,
            keyword="type",
            action="rewritten",
            severity="info",
            message=f"type inferred from {kw} values",
        )
        return
    if "anyOf" in node:
        return  # leave as-is; filter stage reports anything unsupported
    del node[kw]
    node["anyOf"] = [
        SNode({"type": t, "enum": vs}, src=node.src)
        if t != "null"
        else SNode({"type": "null"}, src=node.src)
        for t, vs in by_type.items()
    ]
    for b in node["anyOf"]:
        b.kw_src["enum"] = node.origins(kw)
    ctx.add(
        "core/mixed-enum-split",
        "T5",
        node=node,
        keyword=kw,
        action="rewritten",
        severity="info",
        original=values,
        message=f"{kw} with mixed value types split into one typed enum per type",
    )


def _const_status_unsupported(ctx: Ctx, kw: str) -> bool:
    s = ctx.rules.keyword_status(kw)
    return s in ("stripped", "rejected") or (s is None and not ctx.rules.keeps_unknown_keywords)


def _const_to_enum(node: SNode, ctx: Ctx) -> None:
    if "const" not in node or "enum" in node:
        return
    if not _const_status_unsupported(ctx, "const") or _const_status_unsupported(ctx, "enum"):
        return
    rebuilt = {
        ("enum" if k == "const" else k): ([v] if k == "const" else v) for k, v in node.items()
    }
    origins = node.origins("const")
    node.clear()
    node.update(rebuilt)
    node.kw_src["enum"] = origins
    for origin in origins:
        ctx.add(
            "core/const-to-enum",
            "T5",
            node=node,
            keyword="const",
            action="rewritten",
            severity="info",
            source_path=origin,
            original=node["enum"][0],
            message="const rewritten to an equivalent single-value enum (const is not enforced by the target)",
        )


# --- T4 -----------------------------------------------------------------------------------------


def _t4(node: SNode, ctx: Ctx) -> None:
    t = node.get("type")
    if not isinstance(t, list):
        return
    types = list(dict.fromkeys(cast(list[str], t)))
    non_null = [x for x in types if x != "null"]
    if "integer" in non_null and "number" in non_null:
        non_null.remove("integer")
        types = [x for x in types if x != "integer"]
    if len(non_null) <= 1:
        new_t: Any = types[0] if len(types) == 1 else types
        if canonicalize(new_t) != canonicalize(t):
            node["type"] = new_t
            ctx.add(
                "core/integer-number-collapsed",
                "T4",
                node=node,
                keyword="type",
                action="rewritten",
                severity="info",
                original=t,
                message="integer is subsumed by number",
            )
        return
    specific = {k for ty in types for k in TYPE_KEYWORDS.get(ty, ())}
    values_kw = "const" if "const" in node else ("enum" if "enum" in node else None)
    values: list[Any] | None = None
    if values_kw is not None:
        values = [node["const"]] if values_kw == "const" else list(cast(list[Any], node["enum"]))
    branches: list[SNode] = []
    for ty in types:
        b = SNode({"type": ty}, src=node.src)
        for k in TYPE_KEYWORDS.get(ty, ()):
            if k in node:
                b[k] = node[k] if not isinstance(node[k], SNode) else copy_tree(node[k])
                b.kw_src[k] = node.origins(k)
        if values is not None:
            vs = [
                v
                for v in values
                if json_type(v) == ty or (ty == "number" and json_type(v) == "integer")
            ]
            if not vs:
                continue
            b["enum"] = vs
            b.kw_src["enum"] = node.origins(cast(str, values_kw))
        branches.append(b)
    if values_kw is not None:
        for origin in node.origins(values_kw):
            ctx.add(
                "core/multi-type-split",
                "T4",
                node=node,
                keyword=values_kw,
                action="rewritten",
                severity="info",
                source_path=origin,
                original=values,
                message=f"{values_kw} values partitioned into the typed anyOf branches",
            )
    for k in [*specific, "type", *([values_kw] if values_kw else [])]:
        node.pop(k, None)
    if "anyOf" in node:
        existing = cast(list[Any], node.pop("anyOf"))
        node["anyOf"] = _product(branches, existing, node, ctx)
    else:
        node["anyOf"] = branches
    ctx.add(
        "core/multi-type-split",
        "T4",
        node=node,
        keyword="type",
        action="rewritten",
        severity="info",
        original=t,
        message="multi-type array rewritten as anyOf with type-specific keywords per branch",
    )


# --- T9 -----------------------------------------------------------------------------------------


def _t9(node: SNode, ctx: Ctx) -> None:
    kc = keyword_classes()
    moving = [
        k
        for k in node
        if k != "anyOf"
        and kc.kind(k) in ("validation", "applicator", "unknown")
        and not k.startswith("x-")
    ]
    if not moving:
        return
    base = SNode({k: node[k] for k in moving}, src=node.src)
    base.kw_src = {k: node.origins(k) for k in moving}
    branches = cast(list[Any], node["anyOf"])
    new = _product([base], branches, node, ctx)
    for k in moving:
        del node[k]
    node["anyOf"] = new
    for b in new:
        if isinstance(b, SNode):
            _visit(b, ctx, Seen())
    ctx.add(
        "core/anyof-siblings-distributed",
        "T9",
        node=node,
        keyword="anyOf",
        action="rewritten",
        severity="info",
        message="keywords next to anyOf distributed into each branch",
    )

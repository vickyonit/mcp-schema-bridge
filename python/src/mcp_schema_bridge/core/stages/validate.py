"""Stage S11 / T18: per-schema limits, property keys and arrays without items."""

from __future__ import annotations

import re
from typing import Any, cast

from mcp_schema_bridge.core.context import Ctx
from mcp_schema_bridge.core.errors import LimitExceededError
from mcp_schema_bridge.core.pointer import join
from mcp_schema_bridge.core.tree import Seen, SNode, iter_subschemas


def validate_tree(root: SNode, ctx: Ctx) -> None:
    """Checks on the working tree (before emission): property keys and arrays without items."""
    pattern = re.compile(ctx.rules.property_key_pattern) if ctx.rules.property_key_pattern else None
    seen = Seen()

    def visit(node: SNode) -> None:
        if node in seen:
            return
        seen.add(node)
        props = node.get("properties")
        if pattern is not None and isinstance(props, dict):
            for key, child in cast(dict[str, Any], props).items():
                if not pattern.fullmatch(key):
                    ctx.add(
                        ctx.rule_id("property-key-invalid"),
                        "T18",
                        node=node,
                        keyword="properties",
                        action="rejected",
                        severity="fatal",
                        source_path=child.src[0]
                        if isinstance(child, SNode) and child.src
                        else join(node.src[0] if node.src else "", "properties", key),
                        original=key,
                        message=f"property name {key!r} does not match {pattern.pattern} "
                        "(renaming arrives in v0.2)",
                    )
        if (
            ctx.rules.features.array_items_required
            and _is_array(node)
            and "items" not in node
            and "prefixItems" not in node
        ):
            if ctx.rules.strict:
                ctx.add(
                    ctx.rule_id("array-items-missing"),
                    "T18",
                    node=node,
                    keyword="items",
                    action="rejected",
                    severity="fatal",
                    message="array without items cannot be expressed in strict mode",
                )
            else:
                node["items"] = SNode(src=())
                ctx.add(
                    ctx.rule_id("array-items-added"),
                    "T18",
                    node=node,
                    keyword="items",
                    action="rewritten",
                    severity="info",
                    message="array without items: added the equivalent items: {}",
                )
        for _, _, child in list(iter_subschemas(node)):
            if isinstance(child, SNode):
                visit(child)

    for tree in [root, *ctx.defs.values()]:
        visit(tree)


def _is_array(node: SNode) -> bool:
    t = node.get("type")
    return t == "array" or (isinstance(t, list) and "array" in t)


def count_nodes(v: Any) -> int:
    if isinstance(v, dict):
        return 1 + sum(count_nodes(x) for x in cast(dict[str, Any], v).values())
    if isinstance(v, list):
        return 1 + sum(count_nodes(x) for x in cast(list[Any], v))
    return 1


def check_output(schema: dict[str, Any], ctx: Ctx) -> None:
    """Checks on the emitted schema: output node cap and the target's per-schema limits."""
    n = count_nodes(schema)
    if n > ctx.opts.max_nodes:
        raise LimitExceededError(f"output exceeds max_nodes={ctx.opts.max_nodes} ({n} nodes)")
    limits = ctx.rules.limits
    if not limits:
        return
    stats = _stats(schema)

    def over(name: str, value: int, what: str) -> None:
        limit = limits.get(name)
        if limit is not None and value > limit:
            ctx.add(
                ctx.rule_id("limit-" + name.replace("_", "-")),
                "T18",
                node=None,
                keyword=None,
                action="rejected",
                severity="fatal",
                source_path="",
                original=value,
                message=f"{what} is {value}; the target allows at most {limit}",
            )

    over("max_properties", stats["properties"], "total number of object properties")
    over("max_nesting_depth", stats["depth"], "object nesting depth")
    over(
        "max_total_string_chars",
        stats["chars"],
        "total length of property/definition names and enum/const values",
    )
    over("max_enum_values", stats["enum_values"], "total number of enum values")
    threshold = limits.get("large_enum_threshold")
    if threshold is not None:
        over(
            "max_large_enum_chars",
            stats["large_enum_chars"] if stats["large_enum_count"] > threshold else 0,
            f"total length of a string enum with more than {threshold} values",
        )


def _stats(schema: dict[str, Any]) -> dict[str, int]:
    s = {
        "properties": 0,
        "depth": 0,
        "chars": 0,
        "enum_values": 0,
        "large_enum_chars": 0,
        "large_enum_count": 0,
    }

    def visit(node: Any, depth: int) -> None:
        if not isinstance(node, dict):
            return
        d = cast(dict[str, Any], node)
        is_obj = "properties" in d
        level = depth + 1 if is_obj else depth
        s["depth"] = max(s["depth"], level)
        props = cast(dict[str, Any], d.get("properties") or {})
        s["properties"] += len(props)
        s["chars"] += sum(len(k) for k in props)
        defs = cast(dict[str, Any], d.get("$defs") or {})
        s["chars"] += sum(len(k) for k in defs)
        enum = d.get("enum")
        if isinstance(enum, list):
            values = cast(list[Any], enum)
            s["enum_values"] += len(values)
            strs = [v for v in values if isinstance(v, str)]
            s["chars"] += sum(len(v) for v in strs)
            if len(strs) > s["large_enum_count"]:
                s["large_enum_count"] = len(strs)
                s["large_enum_chars"] = sum(len(v) for v in strs)
        if isinstance(d.get("const"), str):
            s["chars"] += len(d["const"])
        for k, v in d.items():
            if k in ("properties", "$defs", "patternProperties", "dependentSchemas"):
                for sub in cast(dict[str, Any], v).values():
                    visit(sub, level)
            elif k in ("anyOf", "oneOf", "allOf", "prefixItems") and isinstance(v, list):
                for sub in cast(list[Any], v):
                    visit(sub, level)
            elif isinstance(v, dict) and k not in ("default", "const", "examples"):
                visit(v, level)

    visit(schema, 0)
    return s

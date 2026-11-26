"""Stage S7 / T10: close objects on strict targets."""

from __future__ import annotations

from typing import Any, cast

from mcp_schema_bridge.core.context import Ctx
from mcp_schema_bridge.core.rules import keyword_classes
from mcp_schema_bridge.core.tree import SNode, iter_subschemas, to_plain

_OBJECT_HINTS = (
    "properties",
    "additionalProperties",
    "patternProperties",
    "propertyNames",
    "required",
)


def is_object_schema(node: SNode) -> bool:
    t = node.get("type")
    if t is not None:
        return t == "object" or (isinstance(t, list) and "object" in t)
    return any(k in node for k in _OBJECT_HINTS)


def is_any(node: SNode) -> bool:
    """True if the schema places no constraint on values (only annotations)."""
    if node.ref is not None:
        return False
    kc = keyword_classes()
    return not any(kc.kind(k) in ("validation", "applicator", "core", "unknown") for k in node)


def close_objects(root: SNode, ctx: Ctx) -> None:
    if not ctx.rules.features.close_objects:
        return
    seen: set[int] = set()
    _close_root(root, ctx)
    seen.add(id(root))
    for tree in [root, *ctx.defs.values()]:
        _visit(tree, ctx, seen)


def _close_root(root: SNode, ctx: Ctx) -> None:
    if not is_object_schema(root) and root.get("type") is not None:
        return
    has_props = bool(root.get("properties"))
    extra = root.get("additionalProperties")
    if has_props:
        _close(root, ctx)
        return
    if "patternProperties" in root or isinstance(extra, dict) or extra is True:
        _reject_open(root, ctx)
        return
    if "properties" not in root:
        root["properties"] = {}
    if extra is not False:
        root["additionalProperties"] = False
        ctx.add(
            "core/parameterless-tool-closed",
            "T10",
            node=root,
            keyword="additionalProperties",
            action="narrowed",
            severity="info",
            message="tool declares no parameters; closed as {type: object, properties: {}, additionalProperties: false}",
        )


_VALUE_POSITIONS = {"properties", "items", "prefixItems", "anyOf", "oneOf"}


def _visit(node: SNode, ctx: Ctx, seen: set[int], position: str | None = None) -> None:
    first = id(node) not in seen
    seen.add(id(node))
    if first:
        if position in _VALUE_POSITIONS and is_any(node):
            ctx.add(
                "core/any-value-unsupported",
                "T10",
                node=node,
                keyword=None,
                action="rejected",
                severity="fatal",
                message="a schema that accepts any value cannot be expressed in strict mode",
            )
        elif is_object_schema(node):
            if node.get("properties") or (
                "properties" in node and node.get("additionalProperties") is False
            ):
                _close(node, ctx)
            else:
                _reject_open(node, ctx)
    for kw, _, child in list(iter_subschemas(node)):
        if isinstance(child, SNode) and id(child) not in seen:
            _visit(child, ctx, seen, kw)


def _close(node: SNode, ctx: Ctx) -> None:
    extra = node.get("additionalProperties")
    if extra is False:
        return
    severity = "info" if extra is None else "lossy"
    node["additionalProperties"] = False
    ctx.add(
        "core/object-closed",
        "T10",
        node=node,
        keyword="additionalProperties",
        action="narrowed",
        severity=severity,
        original=to_plain(extra) if extra is not None else None,
        message="strict mode requires additionalProperties: false"
        + ("" if extra is None else "; additional keys are no longer allowed"),
    )


def _reject_open(node: SNode, ctx: Ctx) -> None:
    ctx.add(
        "core/open-object-unsupported",
        "T10",
        node=node,
        keyword="additionalProperties",
        action="rejected",
        severity="fatal",
        original=to_plain(cast(Any, node.get("additionalProperties"))),
        message="an object without declared properties (a map) cannot be expressed in strict mode",
    )

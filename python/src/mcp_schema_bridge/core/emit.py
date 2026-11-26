"""Stage S12 (finalize): turn the working tree into plain output, resolve refs and entry paths."""

from __future__ import annotations

from typing import Any, cast
from urllib.parse import quote

from mcp_schema_bridge.core.context import Ctx
from mcp_schema_bridge.core.pointer import join, split
from mcp_schema_bridge.core.report import ReportEntry
from mcp_schema_bridge.core.tree import (
    SCHEMA_ARRAYS,
    SCHEMA_MAPS,
    SCHEMA_VALUES,
    Seen,
    SNode,
    is_schema,
    iter_subschemas,
)


class Emitted:
    def __init__(self) -> None:
        self.schema: dict[str, Any] | None = None
        self.pointers: dict[int, str] = {}  # id(SNode) -> output pointer (first occurrence)
        self.provenance: dict[str, tuple[str, ...]] = {}
        self.ops: list[dict[str, Any]] = []
        self.entries: list[ReportEntry] = []


def emit(root: SNode, ctx: Ctx) -> Emitted:
    out = Emitted()
    # Which defs are reachable from the root (following refs)?
    reachable = _reachable_defs(root, ctx)
    def_pointer = {id(node): join("", "$defs", name) for name, node in reachable.items()}

    def ref_string(target: SNode) -> str:
        if target is root:
            return "#"
        p = def_pointer.get(id(target))
        if p is None:
            raise AssertionError("ref target is neither root nor a registered def")
        return "#" + quote(p, safe="/~!$&'()*+,;=:@")

    def conv(node: Any, pointer: str) -> Any:
        if not isinstance(node, SNode):
            return node
        out.pointers.setdefault(id(node), pointer)
        out.provenance[pointer] = node.src
        for op in node.ops:
            out.ops.append({**op, "at": pointer})
        d: dict[str, Any] = {}
        for kw, v in node.items():
            if kw == "$ref" and node.ref is not None:
                d[kw] = ref_string(node.ref)
            elif kw in SCHEMA_MAPS and isinstance(v, dict):
                d[kw] = {
                    k: conv(s, join(pointer, kw, k)) for k, s in cast(dict[str, Any], v).items()
                }
            elif (kw in SCHEMA_ARRAYS or kw == "items") and isinstance(v, list):
                d[kw] = [conv(s, join(pointer, kw, i)) for i, s in enumerate(cast(list[Any], v))]
            elif (kw in SCHEMA_VALUES or kw == "items") and is_schema(v):
                d[kw] = conv(v, join(pointer, kw))
            else:
                d[kw] = v
        return d

    schema = cast(dict[str, Any], conv(root, ""))
    if reachable:
        schema["$defs"] = {
            name: conv(node, join("", "$defs", name)) for name, node in reachable.items()
        }
    out.schema = None if ctx.fatal else schema

    # Defs that were registered but are unreachable are pruned (info).
    for name, node in ctx.defs.items():
        if name not in reachable:
            ctx.add(
                "core/unused-def-pruned",
                "T1",
                node=None,
                keyword=None,
                action="dropped",
                severity="info",
                source_path=node.src[0] if node.src else "",
                message=f"unused definition {name!r} removed",
            )

    out.entries = build_entries(ctx, out.pointers)
    return out


def build_entries(ctx: Ctx, pointers: dict[int, str]) -> list[ReportEntry]:
    entries: list[ReportEntry] = []
    for e in ctx.entries:
        target_path = pointers.get(id(e.node)) if e.node is not None else None
        entries.append(
            ReportEntry(
                rule=e.rule,
                tid=e.tid,
                tool=ctx.tool,
                source_path=e.source_path,
                target_path=None if ctx.fatal else target_path,
                instance_path=None if ctx.fatal else _instance_path(target_path),
                keyword=e.keyword,
                action=e.action,
                severity=e.severity,
                original=e.original,
                hinted=e.hinted,
                message=e.message,
            )
        )
    return entries


def _reachable_defs(root: SNode, ctx: Ctx) -> dict[str, SNode]:
    by_id = {id(n): name for name, n in ctx.defs.items()}
    found: dict[str, SNode] = {}
    stack: list[Any] = [root]
    seen = Seen()
    while stack:
        n = stack.pop()
        if not isinstance(n, SNode) or n in seen:
            continue
        seen.add(n)
        if n.ref is not None:
            name = by_id.get(id(n.ref))
            if name is not None and name not in found:
                found[name] = n.ref
            stack.append(n.ref)
        for _, _, child in iter_subschemas(n):
            stack.append(child)
    # keep registration order for determinism
    return {name: ctx.defs[name] for name in ctx.defs if name in found}


def _instance_path(target_path: str | None) -> str | None:
    if target_path is None:
        return None
    tokens = split(target_path)
    out: list[str] = []
    i = 0
    while i < len(tokens):
        if tokens[i] == "properties" and i + 1 < len(tokens):
            out.append(tokens[i + 1])
            i += 2
            continue
        return None
    return join("", *out)

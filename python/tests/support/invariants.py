"""Invariant checks shared by property tests and corpus tests (plan §8.3)."""

from __future__ import annotations

from typing import Any, cast

from mcp_schema_bridge import NormalizeResult, normalize_schema
from mcp_schema_bridge.core.jcs import canonicalize
from mcp_schema_bridge.core.pointer import join, split
from mcp_schema_bridge.core.rules import keyword_classes, load_rules
from mcp_schema_bridge.core.tree import build, walk


def _node_at(schema: Any, pointer: str) -> Any:
    node = schema
    for tok in split(pointer):
        node = node[int(tok)] if isinstance(node, list) else node[tok]
    return node


def no_silent_loss(original: dict[str, Any], result: NormalizeResult) -> list[str]:
    """Every validation keyword of the original survives on a traced node or has a report entry."""
    if result.schema is None:
        return []
    kc = keyword_classes()
    by_src: dict[str, list[str]] = {}
    for out_ptr, srcs in result.provenance.items():
        for s in srcs:
            by_src.setdefault(s, []).append(out_ptr)
    entries = result.report.entries
    covered = {(e.source_path, e.keyword) for e in entries}
    subtree_covered = [e.source_path for e in entries if e.keyword is None] + [
        join(e.source_path, e.keyword)
        for e in entries
        if e.keyword is not None and e.action in ("dropped", "rejected", "truncated")
    ]
    problems: list[str] = []
    for ptr, node in walk(build(original)):
        if any(ptr == c or ptr.startswith(c + "/") for c in subtree_covered):
            continue
        for kw, val in node.items():
            if kc.kind(kw) != "validation":
                continue
            if (ptr, kw) in covered:
                continue
            ok = False
            for out_ptr in by_src.get(ptr, []):
                out_node = _node_at(result.schema, out_ptr)
                if kw not in out_node:
                    continue
                if kw == "required":
                    ok = set(cast(list[str], val)) <= set(out_node["required"])
                else:
                    ok = canonicalize(out_node[kw]) == canonicalize(val)
                if ok:
                    break
            if not ok:
                problems.append(
                    f"{ptr or '/'}: {kw}={canonicalize(val)} lost without a report entry"
                )
    return problems


STRUCTURAL = {"$ref", "$defs", "properties", "items", "required", "type", "description", "title"}


def allow_list(result: NormalizeResult) -> list[str]:
    if result.schema is None:
        return []
    rules = load_rules(result.target)
    problems: list[str] = []
    for ptr, node in walk(build(result.schema)):
        for kw in node:
            status = rules.keyword_status(kw)
            if status in ("rejected", "stripped"):
                problems.append(f"{ptr or '/'}: emits {status} keyword {kw}")
            elif status is None and not rules.keeps_unknown_keywords and kw not in STRUCTURAL:
                problems.append(f"{ptr or '/'}: emits unlisted keyword {kw}")
        fmt = node.get("format")
        if (
            isinstance(fmt, str)
            and rules.formats_allowed is not None
            and fmt not in rules.formats_allowed
        ):
            problems.append(f"{ptr or '/'}: emits format {fmt}")
    return problems


def idempotent(result: NormalizeResult) -> list[str]:
    if result.schema is None:
        return []
    again = normalize_schema(result.schema, result.target)  # type: ignore[arg-type]
    problems: list[str] = []
    if again.schema != result.schema:
        problems.append(f"second pass changed schema:\n{again.schema}\n!=\n{result.schema}")
    if again.report.entries:
        problems.append(f"second pass reported: {[e.rule for e in again.report.entries]}")
    return problems


def check_all(original: dict[str, Any], result: NormalizeResult) -> list[str]:
    return no_silent_loss(original, result) + allow_list(result) + idempotent(result)

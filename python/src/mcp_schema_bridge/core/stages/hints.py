"""Stage S10: description hints for dropped constraints (spec/hint-format.md)."""

from __future__ import annotations

import re
from typing import Any

from mcp_schema_bridge.core.context import Ctx, PendingEntry
from mcp_schema_bridge.core.jcs import canonicalize, utf16_sort_key
from mcp_schema_bridge.core.tree import Seen, SNode, iter_subschemas

MAX_VALUE_CHARS = 200
_HINT_RE = re.compile(r"^(?:(?P<text>[\s\S]*)\n\n)?\[constraints: (?P<body>.*)\]$")


def format_value(value: Any) -> str:
    enc = canonicalize(value)
    if len(enc) > MAX_VALUE_CHARS:
        enc = enc[: MAX_VALUE_CHARS - 1] + "…"
    return enc


def split_hint(description: str) -> tuple[str | None, list[str]]:
    """Return (original_text_or_None, hint_entries) for a description that may end in a hint."""
    m = _HINT_RE.match(description)
    if m is None:
        return description, []
    body = m.group("body")
    entries = body.split("; ") if body else []
    if not all("=" in e for e in entries):
        return description, []
    return m.group("text"), entries


def render(text: str | None, entries: list[str]) -> str:
    def key(e: str) -> tuple[bytes, bytes]:
        k, _, v = e.partition("=")
        return utf16_sort_key(k), utf16_sort_key(v)

    block = "[constraints: " + "; ".join(sorted(dict.fromkeys(entries), key=key)) + "]"
    return block if not text else f"{text}\n\n{block}"


def hints_stage(root: SNode, ctx: Ctx) -> None:
    if ctx.opts.max_description_chars is not None:
        _truncate_descriptions(root, ctx)
    if not ctx.opts.hints:
        return
    by_node: dict[int, tuple[SNode, list[PendingEntry]]] = {}
    for e in ctx.entries:
        if not e.want_hint or e.node is None:
            continue
        node = e.node
        if node.ref is not None and not ctx.rules.features.ref_siblings:
            continue
        by_node.setdefault(id(node), (node, []))[1].append(e)
    for node, entries in by_node.values():
        desc = node.get("description")
        text, existing = split_hint(desc) if isinstance(desc, str) else (None, [])
        new = [f"{e.keyword}={format_value(e.original)}" for e in entries if e.keyword]
        node["description"] = render(text, [*existing, *new])
        for e in entries:
            e.hinted = True


def _truncate_descriptions(root: SNode, ctx: Ctx) -> None:
    limit = ctx.opts.max_description_chars
    assert limit is not None
    seen = Seen()

    def visit(node: SNode) -> None:
        if node in seen:
            return
        seen.add(node)
        desc = node.get("description")
        if isinstance(desc, str):
            text, hint = split_hint(desc)
            if text is not None and len(text) > limit:
                cut = text[: max(limit - 1, 0)] + "…"
                node["description"] = render(cut, hint) if hint else cut
                ctx.add(
                    "core/description-truncated",
                    "T1",
                    node=node,
                    keyword="description",
                    action="truncated",
                    severity="info",
                    original=desc,
                    message=f"description truncated to {limit} characters",
                )
        for _, _, child in list(iter_subschemas(node)):
            if isinstance(child, SNode):
                visit(child)

    for tree in [root, *ctx.defs.values()]:
        visit(tree)

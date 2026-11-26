"""Stage S9: keyword filter (T1 annotations, T12 validation/applicators, T13 default,
T15 formats, T16 patterns). Dropped validation constraints are flagged for description hints."""

from __future__ import annotations

from typing import Any, cast

from mcp_schema_bridge.core.context import Ctx
from mcp_schema_bridge.core.regex_scan import scan
from mcp_schema_bridge.core.rules import keyword_classes
from mcp_schema_bridge.core.tree import Seen, SNode, iter_subschemas, to_plain

ALWAYS_KEEP = {"$ref", "type", "properties", "required", "items", "anyOf", "description", "title"}


def filter_stage(root: SNode, ctx: Ctx) -> None:
    seen = Seen()
    for tree in [root, *ctx.defs.values()]:
        _visit(tree, ctx, seen)


def _visit(node: SNode, ctx: Ctx, seen: Seen) -> None:
    if node in seen:
        return
    seen.add(node)
    _integer_exclusive_bounds(node, ctx)
    for kw in list(node):
        if kw in node:
            _filter_keyword(node, kw, ctx)
    for _, _, child in list(iter_subschemas(node)):
        if isinstance(child, SNode):
            _visit(child, ctx, seen)


def _supported(ctx: Ctx, kw: str) -> bool:
    status = ctx.rules.keyword_status(kw)
    if status in ("enforced", "accepted"):
        return True
    if status is None:
        return ctx.rules.keeps_unknown_keywords
    return False


def _slug(ctx: Ctx, kw: str) -> str:
    status = ctx.rules.keyword_status(kw)
    return {"stripped": "keyword-not-enforced", "rejected": "keyword-rejected"}.get(
        cast(str, status), "keyword-unsupported"
    )


def _drop(
    node: SNode, kw: str, ctx: Ctx, *, tid: str, rule: str, severity: str, hint: bool, message: str
) -> None:
    value = to_plain(node[kw])
    for origin in node.origins(kw):
        ctx.add(
            rule,
            tid,
            node=node,
            keyword=kw,
            action="dropped",
            severity=severity,  # type: ignore[arg-type]
            source_path=origin,
            original=value,
            hint=hint,
            message=message,
        )
    del node[kw]
    node.kw_src.pop(kw, None)


def _filter_keyword(node: SNode, kw: str, ctx: Ctx) -> None:
    if kw in ALWAYS_KEEP:
        return
    rules = ctx.rules
    kind = keyword_classes().kind(kw)
    if _supported(ctx, kw):
        if kw == "format":
            _check_format(node, ctx)
        elif kw == "pattern" and rules.pattern_forbidden_features:
            bad = scan(cast(str, node["pattern"])) & rules.pattern_forbidden_features
            if bad:
                _drop(
                    node,
                    kw,
                    ctx,
                    tid="T16",
                    rule=ctx.rule_id("pattern-unsupported"),
                    severity="lossy",
                    hint=True,
                    message=f"pattern uses features the target rejects: {', '.join(sorted(bad))}",
                )
        elif kw == "minItems" and rules.features.min_items_values is not None:
            _clamp_min_items(node, ctx)
        elif kw in ("enum", "const") and rules.features.enum_values == "primitive":
            values = [node["const"]] if kw == "const" else cast(list[Any], node["enum"])
            if any(isinstance(v, dict | list) for v in values):
                _drop(
                    node,
                    kw,
                    ctx,
                    tid="T12",
                    rule=ctx.rule_id("non-primitive-enum"),
                    severity="lossy",
                    hint=True,
                    message="target only allows primitive enum/const values",
                )
        return
    if kw == "prefixItems":
        _flatten_tuple(node, ctx)
        return
    if kw == "default":
        _drop(
            node,
            kw,
            ctx,
            tid="T13",
            rule=ctx.rule_id("default-dropped"),
            severity="info",
            hint=True,
            message="default is not supported by the target; kept as a description hint",
        )
        return
    if kw == "format":
        _drop(
            node,
            kw,
            ctx,
            tid="T15",
            rule=ctx.rule_id("format-unsupported"),
            severity="lossy",
            hint=True,
            message="format is not supported by the target",
        )
        return
    if kind in ("annotation", "unknown", "core"):
        _drop(
            node,
            kw,
            ctx,
            tid="T1",
            rule="core/annotation-dropped",
            severity="info",
            hint=False,
            message=f"{kw} is not supported by the target",
        )
        return
    # validation or applicator keyword the target rejects or ignores
    _drop(
        node,
        kw,
        ctx,
        tid="T12",
        rule=ctx.rule_id(_slug(ctx, kw)),
        severity="lossy",
        hint=True,
        message=f"{kw} is {'not enforced' if rules.keyword_status(kw) == 'stripped' else 'not supported'} "
        "by the target; kept as a description hint",
    )


def _check_format(node: SNode, ctx: Ctx) -> None:
    fmt = node["format"]
    rules = ctx.rules
    allowed = rules.formats_allowed
    enforced = rules.formats_enforced
    ok = (
        isinstance(fmt, str)
        and (allowed is None or fmt in allowed)
        and (not enforced or fmt in enforced)
    )
    if not ok:
        _drop(
            node,
            "format",
            ctx,
            tid="T15",
            rule=ctx.rule_id("format-unsupported"),
            severity="lossy",
            hint=True,
            message=f"format {fmt!r} is not enforced by the target",
        )


def _clamp_min_items(node: SNode, ctx: Ctx) -> None:
    allowed = cast(tuple[int, ...], ctx.rules.features.min_items_values)
    v = node["minItems"]
    if v in allowed:
        return
    best = max(a for a in allowed if a <= v) if any(a <= v for a in allowed) else min(allowed)
    for origin in node.origins("minItems"):
        ctx.add(
            ctx.rule_id("min-items-clamped"),
            "T12",
            node=node,
            keyword="minItems",
            action="rewritten",
            severity="lossy",
            source_path=origin,
            original=v,
            hint=True,
            message=f"minItems {v} is not supported; clamped to {best}",
        )
    node["minItems"] = best


def _is_integer_typed(node: SNode) -> bool:
    t = node.get("type")
    types = [t] if isinstance(t, str) else cast(list[str], t or [])
    return "integer" in types and all(x in ("integer", "null") for x in types)


def _integer_exclusive_bounds(node: SNode, ctx: Ctx) -> None:
    """exclusiveMinimum n == minimum n+1 for integers (and maximum n-1): exact, so info."""
    if not _is_integer_typed(node):
        return
    for ex, inc, delta in (("exclusiveMinimum", "minimum", 1), ("exclusiveMaximum", "maximum", -1)):
        if ex not in node or _supported(ctx, ex) or not _supported(ctx, inc):
            continue
        v = node[ex]
        if not isinstance(v, int | float) or isinstance(v, bool) or not float(v).is_integer():
            continue
        bound = int(v) + delta
        origins = node.origins(ex)
        previous = node.get(inc)
        if previous is not None:
            bound = max(bound, previous) if delta > 0 else min(bound, previous)
            if bound != previous:
                for origin in node.origins(inc):
                    ctx.add(
                        ctx.rule_id("integer-exclusive-bound"),
                        "T12",
                        node=node,
                        keyword=inc,
                        action="merged",
                        severity="info",
                        source_path=origin,
                        original=previous,
                        message=f"{inc} tightened by {ex}",
                    )
            node.kw_src[inc] = tuple(dict.fromkeys((*node.origins(inc), *origins)))
        else:
            node.kw_src[inc] = origins
        node[inc] = bound
        del node[ex]
        for origin in origins:
            ctx.add(
                ctx.rule_id("integer-exclusive-bound"),
                "T12",
                node=node,
                keyword=ex,
                action="rewritten",
                severity="info",
                source_path=origin,
                original=v,
                message=f"{ex} {v} rewritten as the equivalent {inc} {bound} for integers",
            )


def _flatten_tuple(node: SNode, ctx: Ctx) -> None:
    """Target lacks prefixItems: approximate the tuple with `items` = union of the element schemas.

    Dropping prefixItems alone would leave `items` (which only constrains elements after the prefix)
    applying to every element, e.g. `items: false` would forbid all elements.
    """
    prefix = [s for s in cast(list[Any], node["prefixItems"]) if isinstance(s, SNode)]
    tail = node.get("items")
    members: list[Any] = [*prefix, *([tail] if isinstance(tail, SNode) else [])]
    _drop(
        node,
        "prefixItems",
        ctx,
        tid="T12",
        rule=ctx.rule_id(_slug(ctx, "prefixItems")),
        severity="lossy",
        hint=True,
        message="prefixItems (tuple) is not supported by the target; elements are typed as a union",
    )
    if not members:
        node.pop("items", None)
        return
    new_items: Any = members[0] if len(members) == 1 else SNode({"anyOf": members}, src=())
    if "items" in node:
        for origin in node.origins("items"):
            ctx.add(
                ctx.rule_id("tuple-flattened"),
                "T12",
                node=node,
                keyword="items",
                action="rewritten",
                severity="lossy",
                source_path=origin,
                original=to_plain(tail),
                message="items replaced by the union of the tuple element schemas",
            )
    node["items"] = new_items

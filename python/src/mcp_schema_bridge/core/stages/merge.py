"""Stage S3 / T7: merge allOf into a single schema (spec/allof-merge.md).

Also provides :func:`merge_into`, used by inlining of ``$ref`` with sibling keywords (T2b).
"""

from __future__ import annotations

from typing import Any, cast

from mcp_schema_bridge.core.context import Ctx
from mcp_schema_bridge.core.jcs import canonicalize
from mcp_schema_bridge.core.rules import keyword_classes
from mcp_schema_bridge.core.tree import SNode, copy_tree, iter_subschemas, to_plain

_LOWER = {"minimum", "exclusiveMinimum", "minLength", "minItems", "minProperties", "minContains"}
_UPPER = {"maximum", "exclusiveMaximum", "maxLength", "maxItems", "maxProperties", "maxContains"}
_FIRST_WINS_LOSSY = {"pattern", "multipleOf", "format"}
_SINGLE_SUBSCHEMA_FIRST = {
    "not",
    "if",
    "then",
    "else",
    "unevaluatedProperties",
    "unevaluatedItems",
    "contentSchema",
}
_SUBSCHEMA_MERGE = {"items", "contains", "propertyNames"}


def _c(v: Any) -> str:
    return canonicalize(v)


def merge_allof(root: SNode, ctx: Ctx) -> None:
    if not ctx.rules.features.merge_allof:
        return
    seen: set[int] = set()
    for tree in [root, *ctx.defs.values()]:
        _visit(tree, ctx, seen, ())


def _visit(node: SNode, ctx: Ctx, seen: set[int], stack: tuple[int, ...]) -> None:
    if id(node) in seen:
        return
    seen.add(id(node))
    for _, _, child in list(iter_subschemas(node)):
        if isinstance(child, SNode):
            _visit(child, ctx, seen, stack)
    branches = node.get("allOf")
    if not isinstance(branches, list):
        return
    del node["allOf"]
    ctx.add(
        "core/allof-merged",
        "T7",
        node=node,
        keyword="allOf",
        action="merged",
        severity="info",
        message="allOf merged into a single schema",
    )
    contributors: list[SNode] = [_snapshot(node)]
    for b in cast(list[Any], branches):
        if b is True:
            continue
        if b is False:
            ctx.add(
                "core/allof-unsatisfiable",
                "T7",
                node=node,
                keyword="allOf",
                action="rejected",
                severity="fatal",
                message="allOf contains false; schema is unsatisfiable",
            )
            continue
        branch = _resolved_copy(cast(SNode, b), ctx, stack)
        if branch is None:
            continue
        _visit(branch, ctx, set(), stack)  # nested allOf inside the branch copy
        contributors.append(_snapshot(branch))
        merge_into(node, branch, ctx)
    report_changed(node, contributors, ctx)


def _snapshot(n: SNode) -> SNode:
    """Shallow snapshot of a node's own keyword values (for change reporting)."""
    snap = SNode({k: _plain(v) for k, v in n.items()}, src=n.src)
    return snap


def _resolved_copy(b: SNode, ctx: Ctx, stack: tuple[int, ...]) -> SNode | None:
    """Copy of a branch with a top-level $ref replaced by (a copy of) its target."""
    if b.ref is None:
        return b
    target = b.ref
    if id(target) in stack:
        ctx.add(
            "core/allof-ref-cycle",
            "T7",
            node=b,
            keyword="$ref",
            action="rejected",
            severity="fatal",
            message="allOf references itself; cannot be merged",
        )
        return None
    inlined = copy_tree(target)
    if isinstance(inlined, SNode) and inlined.ref is not None:
        nested = _resolved_copy(inlined, ctx, (*stack, id(target)))
        if nested is None:
            return None
        inlined = nested
    siblings = SNode({k: v for k, v in b.items() if k != "$ref"}, src=b.src)
    if siblings:
        merge_into(inlined, siblings, ctx)
    if isinstance(inlined, SNode) and "allOf" in inlined:
        _visit(inlined, ctx, set(), (*stack, id(target)))
    ctx.add(
        "core/allof-ref-inlined",
        "T7",
        node=b,
        keyword="$ref",
        action="inlined",
        severity="info",
        original=b.get("$ref"),
        message="$ref inside allOf resolved before merging",
    )
    return inlined


def merge_into(dst: SNode, src: SNode, ctx: Ctx) -> None:
    """Merge ``src`` into ``dst`` in place (``dst`` keeps its identity)."""
    sides = [_closed_names(dst), _closed_names(src)]
    dst.src = tuple(dict.fromkeys((*dst.src, *src.src)))
    if src.ref is not None and dst.ref is None and "$ref" not in dst:
        dst.ref = src.ref
    for kw, v in src.items():
        if kw == "$ref":
            if "$ref" not in dst:
                dst["$ref"] = v
                dst.ref = src.ref
            elif dst.ref is not src.ref:
                ctx.add(
                    "core/allof-two-refs",
                    "T7",
                    node=dst,
                    keyword="$ref",
                    action="dropped",
                    severity="lossy",
                    source_path=src.src[0] if src.src else "",
                    original=v,
                    message="two different $ref in one allOf; second dropped",
                )
            continue
        if kw not in dst:
            dst[kw] = copy_tree(v) if isinstance(v, SNode) else _copy_value(v)
            continue
        _merge_keyword(dst, src, kw, ctx)
    _apply_additional_properties(dst, sides, ctx)


def _copy_value(v: Any) -> Any:
    if isinstance(v, dict):
        return {
            k: (copy_tree(x) if isinstance(x, SNode) else _copy_value(x))
            for k, x in cast(dict[str, Any], v).items()
        }
    if isinstance(v, list):
        return [
            (copy_tree(x) if isinstance(x, SNode) else _copy_value(x)) for x in cast(list[Any], v)
        ]
    return v


def _types(v: Any) -> list[str]:
    return [v] if isinstance(v, str) else list(cast(list[str], v))


def _merge_keyword(dst: SNode, src: SNode, kw: str, ctx: Ctx) -> None:
    a, b = dst[kw], src[kw]
    src_path = src.src[0] if src.src else ""
    if kw == "properties":
        pa, pb = cast(dict[str, Any], a), cast(dict[str, Any], b)
        for name, sb in pb.items():
            if name not in pa:
                pa[name] = copy_tree(sb)
            else:
                pa[name] = _merge_schemas(pa[name], sb, ctx)
    elif kw == "required":
        dst[kw] = list(dict.fromkeys([*cast(list[str], a), *cast(list[str], b)]))
    elif kw == "type":
        ta, tb = _types(a), _types(b)
        out = [t for t in ta if t in tb]
        if "integer" in ta and "number" in tb and "integer" not in out:
            out.append("integer")
        if "number" in ta and "integer" in tb and "integer" not in out:
            out.append("integer")
        if not out:
            ctx.add(
                "core/allof-unsatisfiable",
                "T7",
                node=dst,
                keyword="type",
                action="rejected",
                severity="fatal",
                original=b,
                message="allOf branches have disjoint types",
            )
            return
        dst[kw] = out[0] if len(out) == 1 else out
    elif kw in ("enum", "const"):
        pass  # handled after the loop via _merge_enum_const
    elif kw in _LOWER:
        dst[kw] = max(a, b)
    elif kw in _UPPER:
        dst[kw] = min(a, b)
    elif kw == "uniqueItems":
        dst[kw] = bool(a) or bool(b)
    elif kw in _FIRST_WINS_LOSSY:
        if _c(a) != _c(b):
            ctx.add(
                f"core/allof-conflicting-{kw.lower()}",
                "T7",
                node=dst,
                keyword=kw,
                action="dropped",
                severity="lossy",
                source_path=src_path,
                original=b,
                hint=True,
                message=f"two different {kw} values; kept the first",
            )
    elif kw in _SINGLE_SUBSCHEMA_FIRST:
        if _c(_plain(a)) != _c(_plain(b)):
            ctx.add(
                "core/allof-conflicting-subschema",
                "T7",
                node=dst,
                keyword=kw,
                action="dropped",
                severity="lossy",
                source_path=src_path,
                original=_plain(b),
                message=f"{kw} in several allOf branches; kept the first",
            )
    elif kw in _SUBSCHEMA_MERGE:
        dst[kw] = _merge_schemas(a, b, ctx)
    elif kw == "prefixItems":
        la, lb = cast(list[Any], a), cast(list[Any], b)
        merged = [_merge_schemas(x, y, ctx) for x, y in zip(la, lb, strict=False)]
        merged += [copy_tree(x) for x in (la[len(lb) :] if len(la) > len(lb) else lb[len(la) :])]
        dst[kw] = merged
    elif kw in ("anyOf", "oneOf"):
        la, lb = cast(list[Any], a), cast(list[Any], b)
        product = [_merge_schemas(copy_tree(x), y, ctx) for x in la for y in lb]
        if len(product) > ctx.opts.max_nodes:
            ctx.add(
                "core/allof-distribution-too-large",
                "T7",
                node=dst,
                keyword=kw,
                action="rejected",
                severity="fatal",
                message="allOf of unions is too large to distribute",
            )
            return
        dst["anyOf"] = product
        if kw == "oneOf":
            del dst["oneOf"]
            ctx.add(
                "core/oneof-to-anyof",
                "T8",
                node=dst,
                keyword="oneOf",
                action="rewritten",
                severity="lossy",
                message="oneOf branches distributed as anyOf; exclusivity lost",
            )
    elif kw == "additionalProperties":
        if a is False or b is False:
            dst[kw] = False
        elif a is True:
            dst[kw] = copy_tree(b)
        elif b is True:
            pass
        else:
            dst[kw] = _merge_schemas(a, b, ctx)
    elif kw == "description":
        if a != b:
            dst[kw] = f"{a}\n\n{b}"
    elif kw == "dependentRequired":
        da, db = cast(dict[str, list[str]], a), cast(dict[str, list[str]], b)
        for k, v in db.items():
            da[k] = list(dict.fromkeys([*da.get(k, []), *v]))
    elif kw in ("dependentSchemas", "patternProperties"):
        da, db = cast(dict[str, Any], a), cast(dict[str, Any], b)
        for k, v in db.items():
            da[k] = _merge_schemas(da[k], v, ctx) if k in da else copy_tree(v)
    else:
        # title, default, examples, unknown keywords: first wins
        if _c(_plain(a)) != _c(_plain(b)):
            kind = keyword_classes().kind(kw)
            ctx.add(
                "core/allof-first-wins",
                "T7",
                node=dst,
                keyword=kw,
                action="merged" if kind in ("annotation",) else "dropped",
                severity="info" if kind in ("annotation",) else "lossy",
                source_path=src_path,
                original=_plain(b),
                message=f"{kw} differs between allOf branches; kept the first",
            )
    if kw in ("enum", "const"):
        _merge_enum_const(dst, src, ctx)


def _merge_enum_const(dst: SNode, src: SNode, ctx: Ctx) -> None:
    def values(n: SNode) -> list[Any] | None:
        if "const" in n:
            return [n["const"]]
        if "enum" in n:
            return list(cast(list[Any], n["enum"]))
        return None

    va, vb = values(dst), values(src)
    if va is None or vb is None:
        return
    keys_b = {_c(x) for x in vb}
    out = [x for x in va if _c(x) in keys_b]
    if not out:
        ctx.add(
            "core/allof-unsatisfiable",
            "T7",
            node=dst,
            keyword="const" if "const" in src else "enum",
            action="rejected",
            severity="fatal",
            message="allOf enum/const values do not intersect",
        )
        return
    if "const" in dst or "const" in src:
        dst.pop("enum", None)
        dst["const"] = out[0]
    else:
        dst["enum"] = out


def _merge_schemas(a: Any, b: Any, ctx: Ctx) -> Any:
    if a is True:
        return copy_tree(b)
    if b is True:
        return a
    if a is False or b is False:
        return False
    snaps = [_snapshot(a), _snapshot(b)]
    out = copy_tree(a)
    merge_into(out, b, ctx)
    report_changed(out, snaps, ctx)
    return out


def _plain(v: Any) -> Any:
    return to_plain(v)


def _closed_names(n: SNode) -> set[str] | None:
    """Property names allowed by ``n`` if it is closed (additionalProperties: false), else None."""
    if n.get("additionalProperties") is not False:
        return None
    return set(cast(dict[str, Any], n.get("properties") or {}))


def _apply_additional_properties(dst: SNode, sides: list[set[str] | None], ctx: Ctx) -> None:
    """additionalProperties: false in one side limits the merged property set to that side's."""
    props = dst.get("properties")
    if not isinstance(props, dict):
        return
    allowed: set[str] | None = None
    for names in sides:
        if names is not None:
            allowed = names if allowed is None else allowed & names
    if allowed is None:
        return
    p = cast(dict[str, Any], props)
    required = set(cast(list[str], dst.get("required") or []))
    for name in [n for n in p if n not in allowed]:
        if name in required:
            ctx.add(
                "core/allof-unsatisfiable",
                "T7",
                node=dst,
                keyword="required",
                action="rejected",
                severity="fatal",
                original=name,
                message=f"property {name!r} is required but forbidden by "
                "additionalProperties: false",
            )
            continue
        removed = p.pop(name)
        ctx.add(
            "core/allof-property-forbidden",
            "T7",
            node=dst,
            keyword=None,
            action="narrowed",
            severity="info",
            original=name,
            source_path=removed.src[0] if isinstance(removed, SNode) and removed.src else "",
            message=f"property {name!r} removed: forbidden by additionalProperties: false "
            "in another branch",
        )


def report_changed(final: SNode, contributors: list[SNode], ctx: Ctx) -> None:
    """Record validation keywords of each contributor whose value changed in ``final`` (info)."""
    for c in contributors:
        _report_changed(final, c, ctx)


def _report_changed(dst: SNode, src: SNode, ctx: Ctx) -> None:
    kc = keyword_classes()
    for kw, v in src.items():
        if kc.kind(kw) != "validation" or kw not in dst or kw in _FIRST_WINS_LOSSY:
            continue
        if kw == "required":
            continue
        if _c(dst[kw]) != _c(v):
            ctx.add(
                "core/allof-value-merged",
                "T7",
                node=dst,
                keyword=kw,
                action="merged",
                severity="info",
                source_path=src.src[0] if src.src else "",
                original=v,
                message=f"{kw} combined with other allOf branches",
            )

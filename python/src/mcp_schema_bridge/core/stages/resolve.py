"""Stage S1: dialect detection and $ref resolution.

After this stage:
- every ``$ref`` node has ``node.ref`` set to its target SNode (identity);
- every reference target is either the root or a registered definition in ``ctx.defs``;
- ``$defs``/``definitions`` maps are removed from the tree (emission re-creates root ``$defs``);
- ``$schema``, ``$id``, ``$anchor`` are removed (info).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urldefrag, urljoin

from mcp_schema_bridge.core.context import Ctx
from mcp_schema_bridge.core.errors import InvalidInputError
from mcp_schema_bridge.core.pointer import decode_fragment
from mcp_schema_bridge.core.tree import SCHEMA_VALUES, SNode, iter_subschemas

DIALECTS: dict[str, str] = {
    "https://json-schema.org/draft/2020-12/schema": "2020-12",
    "http://json-schema.org/draft/2020-12/schema": "2020-12",
    "https://json-schema.org/draft/2019-09/schema": "2019-09",
    "http://json-schema.org/draft/2019-09/schema": "2019-09",
    "http://json-schema.org/draft-07/schema": "draft-07",
    "https://json-schema.org/draft-07/schema": "draft-07",
}
DEFAULT_BASE = "urn:mcp-schema-bridge:root"


def detect_dialect(root: SNode) -> str:
    uri = root.get("$schema")
    if uri is None:
        return "2020-12"
    if not isinstance(uri, str):
        raise InvalidInputError("$schema must be a string", "/$schema")
    key = uri.rstrip("#")
    if key not in DIALECTS:
        raise InvalidInputError(
            f"unsupported JSON Schema dialect {uri!r}; supported: 2020-12, 2019-09, draft-07",
            "/$schema",
        )
    return DIALECTS[key]


@dataclass
class _Loc:
    parent: Any  # SNode | dict | list
    key: str | int
    base: str


def resolve(root: SNode, ctx: Ctx) -> str:
    dialect = detect_dialect(root)
    resources: dict[str, SNode] = {}
    anchors: dict[tuple[str, str], SNode] = {}
    bases: dict[int, str] = {}
    locs: dict[int, _Loc] = {}

    root_base = DEFAULT_BASE
    rid = root.get("$id")
    if isinstance(rid, str):
        root_base = urldefrag(urljoin(DEFAULT_BASE, rid))[0] or DEFAULT_BASE
    resources[root_base] = root
    if root_base != DEFAULT_BASE:
        resources[DEFAULT_BASE] = root

    def index(node: SNode, base: str) -> None:
        bases[id(node)] = base
        anchor = node.get("$anchor")
        if isinstance(anchor, str):
            anchors[(base, anchor)] = node
        for kw, key, child in iter_subschemas(node):
            if not isinstance(child, SNode):
                continue
            cbase = base
            cid = child.get("$id")
            if isinstance(cid, str):
                url, frag = urldefrag(urljoin(base, cid))
                if url:
                    cbase = url
                    resources[url] = child
                if frag and dialect == "draft-07":
                    anchors[(cbase, frag)] = child
            container = node[kw]
            locs[id(child)] = _Loc(
                container if key is not None else node, key if key is not None else kw, cbase
            )
            index(child, cbase)

    index(root, root_base)

    # --- resolve every reference ---------------------------------------------------------------
    ref_nodes: list[SNode] = []

    def visit_refs(node: SNode) -> None:
        for kw in ("$dynamicRef", "$recursiveRef"):
            if kw in node:
                ctx.add(
                    "core/dynamic-ref-unsupported",
                    "T2c",
                    node=node,
                    keyword=kw,
                    action="rejected",
                    severity="fatal",
                    original=node[kw],
                    message=f"{kw} is not supported by any target",
                )
        ref = node.get("$ref")
        if isinstance(ref, str):
            target = _lookup(ref, bases.get(id(node), root_base), resources, anchors)
            if target is None:
                ctx.add(
                    "core/unresolvable-ref",
                    "T2c",
                    node=node,
                    keyword="$ref",
                    action="rejected",
                    severity="fatal",
                    original=ref,
                    message="external or unresolvable $ref (remote references are never fetched)",
                )
            else:
                node.ref = target
                ref_nodes.append(node)
        for _, _, child in iter_subschemas(node):
            if isinstance(child, SNode):
                visit_refs(child)

    visit_refs(root)

    # --- register definitions --------------------------------------------------------------------
    def register(name: str, node: SNode) -> None:
        base, i = name, 1
        while name in ctx.defs:
            name = f"{base}_{i}"
            i += 1
        ctx.defs[name] = node

    def hoist_def_maps(node: SNode) -> None:
        for kw in ("$defs", "definitions"):
            m = node.get(kw)
            if isinstance(m, dict):
                for name, d in cast(dict[str, Any], m).items():
                    if isinstance(d, SNode):
                        register(name, d)
                        hoist_def_maps(d)
                del node[kw]
        for _, _, child in iter_subschemas(node):
            if isinstance(child, SNode):
                hoist_def_maps(child)

    hoist_def_maps(root)
    registered = {id(n) for n in ctx.defs.values()}

    # Targets that are neither the root nor a definition get hoisted into $defs and replaced
    # at their original location by a reference.
    for rn in ref_nodes:
        t = rn.ref
        assert t is not None
        if t is root or id(t) in registered:
            continue
        loc = locs.get(id(t))
        name = _name_for(t, loc)
        register(name, t)
        registered.add(id(t))
        if loc is not None:
            stub = SNode({"$ref": "#"}, src=(), ref=t)
            loc.parent[loc.key] = stub

    # --- strip identity keywords -----------------------------------------------------------------
    _strip_core(root, ctx)
    for d in ctx.defs.values():
        _strip_core(d, ctx)
    return dialect


def _name_for(node: SNode, loc: _Loc | None) -> str:
    if loc is not None and isinstance(loc.key, str) and loc.key not in SCHEMA_VALUES:
        return loc.key
    src = node.src[0] if node.src else ""
    tail = src.rsplit("/", 1)[-1] if src else "def"
    return tail or "def"


def _lookup(
    ref: str, base: str, resources: dict[str, SNode], anchors: dict[tuple[str, str], SNode]
) -> SNode | None:
    url, frag = urldefrag(urljoin(base, ref))
    resource = resources.get(url or base)
    if resource is None:
        return None
    if frag == "":
        return resource
    if not frag.startswith("/"):
        return anchors.get((url or base, frag))
    try:
        tokens = decode_fragment(frag)
    except (ValueError, UnicodeDecodeError):
        return None
    node: Any = resource
    for tok in tokens:
        node = _step(node, tok)
        if node is None:
            return None
    return node if isinstance(node, SNode) else None


def _step(node: Any, tok: str) -> Any:
    if isinstance(node, SNode):
        return node.get(tok)
    if isinstance(node, dict):
        return cast(dict[str, Any], node).get(tok)
    if isinstance(node, list):
        if not tok.isdigit():
            return None
        i = int(tok)
        lst = cast(list[Any], node)
        return lst[i] if i < len(lst) else None
    return None


_STRIP: tuple[str, ...] = (
    "$schema",
    "$id",
    "$anchor",
    "$dynamicAnchor",
    "$recursiveAnchor",
    "$vocabulary",
)


def _strip_core(node: SNode, ctx: Ctx) -> None:
    seen: set[int] = set()

    def visit(n: SNode) -> None:
        if id(n) in seen:
            return
        seen.add(id(n))
        for kw in _STRIP:
            if kw in n:
                ctx.add(
                    "core/identity-keyword-removed",
                    "T1",
                    node=n,
                    keyword=kw,
                    action="dropped",
                    severity="info",
                    original=n[kw],
                    message=f"{kw} is resolved and removed; output always uses 2020-12 semantics",
                )
                del n[kw]
        for _, _, child in iter_subschemas(n):
            if isinstance(child, SNode):
                visit(child)

    visit(node)

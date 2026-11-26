"""normalize_schema: runs stages S0..S12 for one schema."""

from __future__ import annotations

import hashlib
from typing import Any

from mcp_schema_bridge._version import __version__
from mcp_schema_bridge.core.context import Ctx
from mcp_schema_bridge.core.emit import emit
from mcp_schema_bridge.core.jcs import canonicalize
from mcp_schema_bridge.core.options import NormalizeOptions
from mcp_schema_bridge.core.parse import Limits, check_value
from mcp_schema_bridge.core.report import Report
from mcp_schema_bridge.core.result import NormalizeResult, ReverseMap
from mcp_schema_bridge.core.rules import RULES_VERSION, Target, load_rules
from mcp_schema_bridge.core.stages.canonicalize import canonicalize_tree
from mcp_schema_bridge.core.stages.inline import inline_stage
from mcp_schema_bridge.core.stages.merge import merge_allof
from mcp_schema_bridge.core.stages.resolve import resolve
from mcp_schema_bridge.core.stages.root import apply_root
from mcp_schema_bridge.core.tree import SNode, build


def fingerprint(original: Any, target: str) -> str:
    payload = {
        "original": original,
        "library_version": __version__,
        "rules_version": RULES_VERSION,
        "target": target,
    }
    return hashlib.sha256(canonicalize(payload).encode("utf-8")).hexdigest()


def normalize_schema(
    schema: dict[str, Any],
    target: Target,
    opts: NormalizeOptions | None = None,
    *,
    tool: str | None = None,
    fingerprint_of: Any = None,
) -> NormalizeResult:
    rules = load_rules(target)
    o = opts or NormalizeOptions()
    value, _coerced = check_value(
        schema, big_int=o.big_int, limits=Limits(max_nodes=o.max_nodes, max_depth=o.max_depth)
    )
    ctx = Ctx(rules=rules, opts=o, tool=tool)
    root = build(value)
    if not isinstance(root, SNode):
        root = SNode(src=("",))
    dialect = resolve(root, ctx)
    canonicalize_tree(root, ctx, dialect)
    merge_allof(root, ctx)
    inline_stage(root, ctx)
    root = apply_root(root, ctx)
    out = emit(root, ctx)
    fp = fingerprint(fingerprint_of if fingerprint_of is not None else value, target)
    return NormalizeResult(
        target=target,
        strict=rules.strict,
        schema=out.schema,
        report=Report(target=target, entries=out.entries),
        reverse=ReverseMap(
            fingerprint=fp, rules_version=RULES_VERSION, target=target, ops=tuple(out.ops)
        ),
        fingerprint=fp,
        library_version=__version__,
        rules_version=RULES_VERSION,
        provenance=out.provenance,
    )

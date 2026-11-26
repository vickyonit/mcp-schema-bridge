"""normalize_tools: a whole MCP toolset for one target, including per-request budgets (T17)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, cast

from mcp_schema_bridge._version import __version__
from mcp_schema_bridge.core.errors import InvalidInputError
from mcp_schema_bridge.core.options import Budget, NormalizeOptions
from mcp_schema_bridge.core.pipeline import normalize_schema
from mcp_schema_bridge.core.report import SEVERITIES, Action, Report, ReportEntry, Severity
from mcp_schema_bridge.core.result import NormalizeResult, ReverseMap
from mcp_schema_bridge.core.rules import RULES_VERSION, Target, load_rules


@dataclass(frozen=True)
class NormalizedTool:
    name: str
    description: str | None
    target: str
    strict: bool
    schema: dict[str, Any]
    reverse: ReverseMap
    fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "target": self.target,
            "strict": self.strict,
            "schema": self.schema,
            "reverse": self.reverse.to_dict(),
            "fingerprint": self.fingerprint,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> NormalizedTool:
        return cls(
            name=d["name"],
            description=d.get("description"),
            target=d["target"],
            strict=d["strict"],
            schema=d["schema"],
            reverse=ReverseMap.from_dict(d["reverse"]),
            fingerprint=d["fingerprint"],
        )


@dataclass(frozen=True)
class Rejection:
    name: str
    target: str
    reasons: list[ReportEntry]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "target": self.target,
            "reasons": [r.to_dict() for r in self.reasons],
        }


@dataclass(frozen=True)
class ToolsetResult:
    target: str
    tools: list[NormalizedTool]
    rejected: list[Rejection]
    report: Report
    library_version: str = __version__
    rules_version: str = RULES_VERSION

    def get(self, name: str) -> NormalizedTool | None:
        """The normalized tool with this name, or None if it was rejected or never existed."""
        return next((t for t in self.tools if t.name == name), None)

    def summary(self) -> str:
        """Human-readable summary (the same text as `mcp-schema-bridge check`), with server-side fixes."""
        from mcp_schema_bridge.fixes import fix_for

        counts = {s: 0 for s in SEVERITIES}
        for e in self.report.entries:
            counts[e.severity] += 1
        changes = ", ".join(f"{n} {s}" for s, n in counts.items() if n) or "no changes"
        demoted = sum(1 for t in self.tools if t.target != self.target)
        ok = f"{len(self.tools)} tool(s) ok" + (
            f" ({demoted} demoted to non-strict)" if demoted else ""
        )
        lines = [f"{self.target}: {ok}, {len(self.rejected)} rejected; {changes}"]
        for e in self.report.sorted():
            if e.severity == "info":
                continue
            where = f"{e.tool}  {e.source_path or '/'}" if e.tool else (e.source_path or "/")
            keyword = f" {e.keyword}" if e.keyword else ""
            lines.append(f"  [{e.severity}] {where}{keyword}: {e.message} ({e.rule})")
            fix = fix_for(e.rule)
            if fix and e.severity in ("lossy", "fatal"):
                lines.append(f"      fix: {fix}")
        return "\n".join(lines) + "\n"

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "library_version": self.library_version,
            "rules_version": self.rules_version,
            "tools": [t.to_dict() for t in self.tools],
            "rejected": [r.to_dict() for r in self.rejected],
            "report": self.report.to_dict(
                library_version=self.library_version, rules_version=self.rules_version
            ),
        }


def as_tool_dict(t: Any) -> Any:
    """Accept MCP SDK Tool objects (pydantic models) as well as plain dicts."""
    if isinstance(t, dict):
        return cast(Any, t)
    dump = getattr(t, "model_dump", None)
    if callable(dump):
        return dump(mode="json", by_alias=True, exclude_none=True)
    return t


def _check_tool(t: Any, i: int) -> tuple[str, str | None, dict[str, Any]]:
    if not isinstance(t, dict):
        raise InvalidInputError("tool must be an object", f"/{i}")
    tool = cast(dict[str, Any], t)
    name = tool.get("name")
    if not isinstance(name, str) or not name:
        raise InvalidInputError("tool name must be a non-empty string", f"/{i}/name")
    desc = tool.get("description")
    if desc is not None and not isinstance(desc, str):
        raise InvalidInputError("tool description must be a string", f"/{i}/description")
    schema = tool.get("inputSchema")
    if not isinstance(schema, dict):
        raise InvalidInputError("tool inputSchema must be an object", f"/{i}/inputSchema")
    return name, desc, cast(dict[str, Any], schema)


def _entry(
    rule: str,
    tool: str,
    message: str,
    *,
    action: Action = "rejected",
    severity: Severity = "fatal",
    original: Any = None,
    keyword: str | None = None,
) -> ReportEntry:
    return ReportEntry(
        rule=rule,
        tid="T18" if "name" in rule else "T17",
        tool=tool,
        source_path="",
        keyword=keyword,
        action=action,
        severity=severity,
        original=original,
        message=message,
    )


def normalize_tools(
    tools: list[Any], target: Target, opts: NormalizeOptions | None = None
) -> ToolsetResult:
    o = opts or NormalizeOptions()
    rules = load_rules(target)
    tools = [as_tool_dict(t) for t in tools]
    parsed = [_check_tool(t, i) for i, t in enumerate(tools)]
    name_re = re.compile(rules.tool_name_pattern)
    accepted: list[tuple[NormalizedTool, dict[str, Any]]] = []
    rejected: list[Rejection] = []
    entries: list[ReportEntry] = []
    seen_names: set[str] = set()

    for (name, desc, schema), raw in zip(parsed, tools, strict=True):
        if name in seen_names:
            reason = _entry(
                "core/duplicate-tool-name", name, f"duplicate tool name {name!r}", original=name
            )
            rejected.append(Rejection(name, target, [reason]))
            entries.append(reason)
            continue
        seen_names.add(name)
        if not name_re.fullmatch(name):
            reason = _entry(
                f"{target}/tool-name-invalid",
                name,
                f"tool name {name!r} does not match {rules.tool_name_pattern} (renaming arrives in v0.2)",
                original=name,
            )
            rejected.append(Rejection(name, target, [reason]))
            entries.append(reason)
            continue
        result = normalize_schema(schema, target, o, tool=name, fingerprint_of=raw)
        entries.extend(result.report.entries)
        if result.schema is None:
            rejected.append(
                Rejection(name, target, [e for e in result.report.entries if e.severity == "fatal"])
            )
            continue
        accepted.append((_tool(name, desc, result), raw))

    final: list[NormalizedTool] = []
    if rules.request_limits:
        final = _apply_budgets(accepted, rules.request_limits, o, target, rejected, entries)
    else:
        final = [t for t, _ in accepted]
    return ToolsetResult(
        target=target, tools=final, rejected=rejected, report=Report(target=target, entries=entries)
    )


def _tool(name: str, desc: str | None, r: NormalizeResult) -> NormalizedTool:
    assert r.schema is not None
    return NormalizedTool(
        name=name,
        description=desc,
        target=r.target,
        strict=r.strict,
        schema=r.schema,
        reverse=r.reverse,
        fingerprint=r.fingerprint,
    )


def usage(schema: dict[str, Any]) -> tuple[int, int]:
    """(optional_params, union_params) of an emitted schema, counted across nested objects and $defs."""
    optional = 0
    unions = 0

    def visit(node: Any) -> None:
        nonlocal optional, unions
        if not isinstance(node, dict):
            return
        d = cast(dict[str, Any], node)
        props = cast(dict[str, Any], d.get("properties") or {})
        required = set(cast(list[str], d.get("required") or []))
        for k, sub in props.items():
            if k not in required:
                optional += 1
            if isinstance(sub, dict):
                s = cast(dict[str, Any], sub)
                t = s.get("type")
                if "anyOf" in s or (isinstance(t, list) and len(cast(list[Any], t)) > 1):
                    unions += 1
        for k, v in d.items():
            if k in ("properties", "$defs"):
                for sub in cast(dict[str, Any], v).values():
                    visit(sub)
            elif k in ("anyOf", "prefixItems") and isinstance(v, list):
                for sub in cast(list[Any], v):
                    visit(sub)
            elif k == "items":
                visit(v)

    visit(schema)
    return optional, unions


def _apply_budgets(
    accepted: list[tuple[NormalizedTool, dict[str, Any]]],
    limits: dict[str, int],
    o: NormalizeOptions,
    target: str,
    rejected: list[Rejection],
    entries: list[ReportEntry],
) -> list[NormalizedTool]:
    reserved = o.reserved_budget or Budget()
    used = {
        "tools": reserved.strict_tools,
        "optional": reserved.optional_params,
        "union": reserved.union_params,
    }
    caps = {
        "tools": limits.get("max_strict_tools"),
        "optional": limits.get("max_optional_params"),
        "union": limits.get("max_union_params"),
    }
    rules = load_rules(target)
    out: list[NormalizedTool] = []
    overflow = False
    for t, raw in accepted:
        if not t.strict:
            out.append(t)
            continue
        opt, uni = usage(t.schema)
        nxt = {
            "tools": used["tools"] + 1,
            "optional": used["optional"] + opt,
            "union": used["union"] + uni,
        }
        fits = not overflow and all(caps[k] is None or nxt[k] <= cast(int, caps[k]) for k in nxt)
        if fits:
            used = nxt
            out.append(t)
            continue
        overflow = True
        over = [k for k in nxt if caps[k] is not None and nxt[k] > cast(int, caps[k])] or [
            "earlier overflow"
        ]
        reason = _entry(
            f"{target}/request-budget-exceeded",
            t.name,
            f"per-request strict budget exceeded ({', '.join(over)}); this tool and all later strict tools are affected",
            original={k: nxt[k] for k in nxt},
        )
        entries.append(reason)
        if o.strict_fallback and rules.fallback_target:
            fb = normalize_schema(
                raw["inputSchema"], rules.fallback_target, o, tool=t.name, fingerprint_of=raw
            )
            entries.extend(fb.report.entries)
            entries.append(
                _entry(
                    f"{target}/strict-fallback",
                    t.name,
                    f"tool demoted to {rules.fallback_target} (not grammar-constrained)",
                    action="fallback",
                    severity="lossy",
                )
            )
            if fb.schema is None:
                rejected.append(Rejection(t.name, target, [reason]))
            else:
                out.append(_tool(t.name, t.description, fb))
        else:
            rejected.append(Rejection(t.name, target, [reason]))
    return out

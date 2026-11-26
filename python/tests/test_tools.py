"""normalize_tools: toolsets, names, budgets (T17), fallback, serialization."""

from typing import Any

import pytest

from mcp_schema_bridge import (
    Budget,
    InvalidInputError,
    NormalizedTool,
    NormalizeOptions,
    ToolsetResult,
    denormalize_args,
    normalize_tools,
)


def tool(name: str, schema: dict[str, Any] | None = None, description: str = "d") -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": schema
        or {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
    }


def test_normalizes_each_tool_and_round_trips() -> None:
    res = normalize_tools([tool("search"), tool("noop", {"type": "object"})], "openai-strict")
    assert [t.name for t in res.tools] == ["search", "noop"]
    assert res.rejected == []
    assert res.tools[1].schema == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    assert all(t.strict for t in res.tools)
    assert denormalize_args(res.tools[0], {"q": "x"}).args == {"q": "x"}
    assert {e.tool for e in res.report.entries} <= {"search", "noop"}


def test_invalid_tool_name_is_rejected_per_target() -> None:
    res = normalize_tools([tool("files.read"), tool("ok")], "anthropic")
    assert [t.name for t in res.tools] == ["ok"]
    [rej] = res.rejected
    assert rej.name == "files.read"
    assert [r.rule for r in rej.reasons] == ["anthropic/tool-name-invalid"]
    # Gemini allows dots in function names
    assert [t.name for t in normalize_tools([tool("files.read")], "gemini-json").tools] == [
        "files.read"
    ]


def test_duplicate_names_reject_later_occurrence() -> None:
    res = normalize_tools([tool("a"), tool("a")], "openai")
    assert len(res.tools) == 1
    assert [r.rule for r in res.rejected[0].reasons] == ["core/duplicate-tool-name"]


def test_malformed_tool_raises() -> None:
    with pytest.raises(InvalidInputError, match="inputSchema"):
        normalize_tools([{"name": "x"}], "openai")
    with pytest.raises(InvalidInputError, match="name"):
        normalize_tools([{"inputSchema": {}}], "openai")


def test_fatal_tool_is_rejected_without_fallback() -> None:
    meta = tool(
        "meta", {"type": "object", "properties": {"m": {"type": "object"}}, "required": ["m"]}
    )
    res = normalize_tools([meta], "openai-strict")
    assert res.tools == []
    assert res.rejected[0].name == "meta"


def test_strict_fallback_demotes_fatal_tool_to_non_strict_sibling() -> None:
    meta = tool(
        "meta", {"type": "object", "properties": {"m": {"type": "object"}}, "required": ["m"]}
    )
    res = normalize_tools([meta], "openai-strict", NormalizeOptions(strict_fallback=True))
    [t] = res.tools
    assert (t.target, t.strict) == ("openai", False)
    assert t.schema["properties"]["m"] == {"type": "object"}
    assert any(e.action == "fallback" and e.tool == "meta" for e in res.report.entries)


def _optional_tool(name: str, n_optional: int) -> dict[str, Any]:
    props = {f"o{i}": {"type": "string"} for i in range(n_optional)}
    return tool(name, {"type": "object", "properties": props})


def test_anthropic_strict_optional_budget_rejects_from_first_overflow() -> None:
    tools = [
        _optional_tool("a", 10),
        _optional_tool("b", 10),
        _optional_tool("c", 10),
        _optional_tool("d", 1),
    ]
    res = normalize_tools(tools, "anthropic-strict")
    assert [t.name for t in res.tools] == ["a", "b"]
    assert [r.name for r in res.rejected] == ["c", "d"]
    assert res.rejected[0].reasons[0].rule == "anthropic-strict/request-budget-exceeded"


def test_anthropic_strict_budget_with_fallback_and_reserved() -> None:
    tools = [_optional_tool("a", 10), _optional_tool("b", 10)]
    opts = NormalizeOptions(strict_fallback=True, reserved_budget=Budget(optional_params=10))
    res = normalize_tools(tools, "anthropic-strict", opts)
    assert [(t.name, t.strict) for t in res.tools] == [("a", True), ("b", False)]


def test_anthropic_strict_tool_count_budget() -> None:
    res = normalize_tools([tool(f"t{i}") for i in range(21)], "anthropic-strict")
    assert len(res.tools) == 20
    assert [r.name for r in res.rejected] == ["t20"]


def test_anthropic_strict_union_budget() -> None:
    u = {
        "type": "object",
        "properties": {f"u{i}": {"type": ["string", "integer"]} for i in range(9)},
        "required": [f"u{i}" for i in range(9)],
    }
    res = normalize_tools([tool("a", u), tool("b", u)], "anthropic-strict")
    assert [t.name for t in res.tools] == ["a"]


def test_serialization_round_trip() -> None:
    res = normalize_tools([tool("search")], "openai-strict")
    d = res.to_dict()
    assert set(d) == {"target", "library_version", "rules_version", "tools", "rejected", "report"}
    again = NormalizedTool.from_dict(d["tools"][0])
    assert again == res.tools[0]
    assert denormalize_args(again, {"q": "x"}).args == {"q": "x"}
    assert isinstance(res, ToolsetResult)


def test_fingerprint_covers_whole_tool() -> None:
    a = normalize_tools([tool("search", description="one")], "openai").tools[0].fingerprint
    b = normalize_tools([tool("search", description="two")], "openai").tools[0].fingerprint
    assert a != b

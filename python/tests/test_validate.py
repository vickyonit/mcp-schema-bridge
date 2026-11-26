"""S11 / T18: per-schema limits, property keys, arrays without items, output node cap."""

from typing import Any

import pytest

from mcp_schema_bridge import LimitExceededError, NormalizeOptions, normalize_schema


def fatal_rules(r: Any) -> list[str]:
    return [e.rule for e in r.report.entries if e.severity == "fatal"]


def test_openai_strict_property_count_limit() -> None:
    props = {f"p{i}": {"type": "string"} for i in range(5001)}
    big = NormalizeOptions(max_nodes=100_000)
    r = normalize_schema(
        {"type": "object", "properties": props, "required": list(props)}, "openai-strict", big
    )
    assert r.schema is None
    assert "openai-strict/limit-max-properties" in fatal_rules(r)


def test_openai_strict_nesting_depth_limit() -> None:
    node: dict[str, Any] = {"type": "string"}
    for _ in range(11):
        node = {"type": "object", "properties": {"x": node}, "required": ["x"]}
    r = normalize_schema(node, "openai-strict")
    assert r.schema is None
    assert "openai-strict/limit-max-nesting-depth" in fatal_rules(r)


def test_openai_strict_enum_value_limit() -> None:
    s = {
        "type": "object",
        "properties": {"e": {"type": "string", "enum": [f"v{i}" for i in range(1001)]}},
        "required": ["e"],
    }
    r = normalize_schema(s, "openai-strict")
    assert "openai-strict/limit-max-enum-values" in fatal_rules(r)


def test_openai_strict_large_string_enum_chars_limit() -> None:
    values = [f"{i:04d}" + "x" * 60 for i in range(251)]  # 251 values * 64 chars > 15000
    s = {
        "type": "object",
        "properties": {"e": {"type": "string", "enum": values}},
        "required": ["e"],
    }
    r = normalize_schema(s, "openai-strict")
    assert "openai-strict/limit-max-large-enum-chars" in fatal_rules(r)


def test_limits_do_not_apply_to_other_targets() -> None:
    props = {f"p{i}": {"type": "string"} for i in range(5001)}
    r = normalize_schema(
        {"type": "object", "properties": props}, "gemini-json", NormalizeOptions(max_nodes=100_000)
    )
    assert r.schema is not None


def test_anthropic_property_key_pattern() -> None:
    r = normalize_schema({"type": "object", "properties": {"a b": {"type": "string"}}}, "anthropic")
    assert r.schema is None
    assert "anthropic/property-key-invalid" in fatal_rules(r)
    ok = normalize_schema(
        {"type": "object", "properties": {"a.b-c_d": {"type": "string"}}}, "anthropic"
    )
    assert ok.schema is not None


def test_array_without_items_gets_any_items_on_openai() -> None:
    r = normalize_schema({"type": "object", "properties": {"t": {"type": "array"}}}, "openai")
    assert r.schema is not None
    assert r.schema["properties"]["t"] == {"type": "array", "items": {}}
    [e] = [e for e in r.report.entries if e.tid == "T18"]
    assert (e.action, e.severity) == ("rewritten", "info")


def test_array_without_items_is_fatal_on_openai_strict() -> None:
    r = normalize_schema(
        {"type": "object", "properties": {"t": {"type": "array"}}, "required": ["t"]},
        "openai-strict",
    )
    assert r.schema is None


def test_output_node_cap_raises() -> None:
    # 3 refs to a def with 10 props, inlined by a target that forbids $ref siblings -> fine;
    # max_nodes small enough to trip on output but not input.
    s = {
        "type": "object",
        "properties": {f"p{i}": {"$ref": "#/$defs/D", "description": "d"} for i in range(5)},
        "required": [f"p{i}" for i in range(5)],
        "$defs": {
            "D": {
                "type": "object",
                "properties": {f"k{j}": {"type": "string"} for j in range(10)},
                "required": [f"k{j}" for j in range(10)],
            }
        },
    }

    def count(v: Any) -> int:
        if isinstance(v, dict):
            return 1 + sum(count(x) for x in v.values())
        if isinstance(v, list):
            return 1 + sum(count(x) for x in v)
        return 1

    # Input fits; the output (5 inlined copies of D) does not.
    with pytest.raises(LimitExceededError, match="output exceeds max_nodes"):
        normalize_schema(s, "openai-strict", NormalizeOptions(max_nodes=count(s) + 1))

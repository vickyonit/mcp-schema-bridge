"""T14: root handling."""

import pytest

from mcp_schema_bridge import denormalize_args, normalize_schema
from mcp_schema_bridge.core.rules import TARGETS


@pytest.mark.parametrize("target", TARGETS)
def test_non_object_root_is_wrapped_and_reversible(target: str) -> None:
    r = normalize_schema({"type": "string", "description": "a name"}, target)
    assert r.schema is not None
    assert r.schema["type"] == "object"
    assert r.schema["properties"]["value"]["type"] == "string"
    assert r.schema["required"] == ["value"]
    [e] = [e for e in r.report.entries if e.tid == "T14"]
    assert (e.action, e.severity, e.keyword) == ("wrapped", "reversible", "type")
    assert denormalize_args(r, {"value": "Ada"}).args == "Ada"


@pytest.mark.parametrize("target", TARGETS)
def test_root_anyof_is_wrapped(target: str) -> None:
    schema = {
        "anyOf": [
            {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]},
            {"type": "object", "properties": {"b": {"type": "integer"}}, "required": ["b"]},
        ]
    }
    r = normalize_schema(schema, target)
    assert r.schema is not None
    assert r.schema["type"] == "object"
    assert "anyOf" not in r.schema
    assert denormalize_args(r, {"value": {"a": "x"}}).args == {"a": "x"}


def test_root_object_with_anyof_is_kept_where_target_allows_it() -> None:
    schema = {
        "type": "object",
        "properties": {"a": {"type": "string"}, "b": {"type": "string"}},
        "anyOf": [{"required": ["a"]}, {"required": ["b"]}],
    }
    r = normalize_schema(schema, "gemini-json")
    assert r.schema == schema
    assert r.reverse.ops == ()


@pytest.mark.parametrize("target", ["openai", "anthropic", "openai-strict", "anthropic-strict"])
def test_empty_root_gets_type_object(target: str) -> None:
    r = normalize_schema({}, target)
    assert r.schema is not None
    assert r.schema["type"] == "object"
    [e] = [e for e in r.report.entries if e.tid == "T14"]
    assert (e.action, e.severity) == ("narrowed", "info")
    assert r.reverse.ops == ()


def test_empty_root_is_left_alone_for_gemini_json() -> None:
    r = normalize_schema({}, "gemini-json")
    assert r.schema == {}
    assert r.report.entries == []


def test_root_properties_without_type_gets_type_object_for_openai() -> None:
    r = normalize_schema({"properties": {"a": {"type": "string"}}}, "openai")
    assert r.schema == {"properties": {"a": {"type": "string"}}, "type": "object"}


def test_nullable_object_root_drops_null() -> None:
    r = normalize_schema({"type": ["object", "null"], "properties": {}}, "openai")
    assert r.schema is not None
    assert r.schema["type"] == "object"
    [e] = [e for e in r.report.entries if e.tid == "T14"]
    assert e.action == "narrowed"

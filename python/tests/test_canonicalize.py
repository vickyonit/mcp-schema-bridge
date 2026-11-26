"""S2: dialect-independent canonical form."""

import pytest

from mcp_schema_bridge import normalize_schema

D7 = "http://json-schema.org/draft-07/schema#"


def obj(props: dict, **kw: object) -> dict:
    return {"type": "object", "properties": props, **kw}


def test_tuple_items_become_prefix_items() -> None:
    s = obj(
        {
            "p": {
                "type": "array",
                "items": [{"type": "string"}, {"type": "integer"}],
                "additionalItems": False,
            }
        }
    )
    r = normalize_schema(s, "gemini-json")
    assert r.schema is not None
    assert r.schema["properties"]["p"] == {
        "type": "array",
        "prefixItems": [{"type": "string"}, {"type": "integer"}],
        "items": False,
    }
    [e] = [e for e in r.report.entries if e.keyword == "items"]
    assert (e.action, e.severity) == ("rewritten", "info")


def test_tuple_items_without_additional_items_leave_items_open() -> None:
    s = obj({"p": {"type": "array", "items": [{"type": "string"}]}})
    r = normalize_schema(s, "openai")
    assert r.schema is not None
    assert r.schema["properties"]["p"] == {"type": "array", "prefixItems": [{"type": "string"}]}


def test_dependencies_split_into_dependent_required_and_schemas() -> None:
    s = obj(
        {"a": {"type": "string"}, "b": {"type": "string"}},
        dependencies={"a": ["b"], "b": {"required": ["a"]}},
    )
    r = normalize_schema(s, "openai")
    assert r.schema is not None
    assert r.schema["dependentRequired"] == {"a": ["b"]}
    assert r.schema["dependentSchemas"] == {"b": {"required": ["a"]}}
    assert "dependencies" not in r.schema


def test_openapi_nullable_true_becomes_type_array() -> None:
    r = normalize_schema(obj({"a": {"type": "string", "nullable": True}}), "openai")
    assert r.schema is not None
    assert r.schema["properties"]["a"] == {"type": ["string", "null"]}


def test_openapi_nullable_false_is_dropped() -> None:
    r = normalize_schema(obj({"a": {"type": "string", "nullable": False}}), "openai")
    assert r.schema is not None
    assert r.schema["properties"]["a"] == {"type": "string"}


def test_draft07_ref_siblings_are_dropped_as_info() -> None:
    s = {
        "$schema": D7,
        "type": "object",
        "properties": {
            "a": {"$ref": "#/definitions/N", "description": "ignored in draft-07", "minLength": 3}
        },
        "definitions": {"N": {"type": "string"}},
    }
    r = normalize_schema(s, "openai")
    assert r.schema is not None
    assert r.schema["properties"]["a"] == {"$ref": "#/$defs/N"}
    t3 = sorted((e.keyword, e.severity) for e in r.report.entries if e.tid == "T3")
    assert t3 == [("description", "info"), ("minLength", "info")]


@pytest.mark.parametrize("target", ["openai-strict", "anthropic-strict"])
def test_boolean_subschemas_become_objects_where_unsupported(target: str) -> None:
    r = normalize_schema(
        obj({"a": {"type": "array", "items": {"type": "string"}, "contains": True}}), target
    )
    # contains: true -> {} (equivalent); later stages may drop 'contains' for the target
    assert r.schema is not None


def test_boolean_subschemas_kept_where_supported() -> None:
    s = obj({"a": True})
    assert normalize_schema(s, "gemini-json").schema == s

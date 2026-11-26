"""Edge cases for root wrapping, references, nullability and unions."""

from typing import Any

import pytest

from mcp_schema_bridge import InvalidInputError, denormalize_args, normalize_schema
from tests.support.invariants import check_all


def run(schema: dict[str, Any], target: str) -> Any:
    r = normalize_schema(schema, target)  # type: ignore[arg-type]
    assert check_all(schema, r) == []
    return r


def test_wrapping_a_self_referenced_root_moves_it_into_defs() -> None:
    s = {
        "anyOf": [
            {
                "type": "object",
                "properties": {"child": {"$ref": "#"}, "name": {"type": "string"}},
                "required": ["name"],
            },
            {"type": "object", "properties": {"leaf": {"type": "boolean"}}, "required": ["leaf"]},
        ]
    }
    r = run(s, "openai")
    assert r.schema["properties"]["value"] == {"$ref": "#/$defs/__root"}
    assert r.schema["$defs"]["__root"]["anyOf"][0]["properties"]["child"] == {
        "$ref": "#/$defs/__root"
    }
    assert denormalize_args(r, {"value": {"name": "a", "child": {"leaf": True}}}).args == {
        "name": "a",
        "child": {"leaf": True},
    }


def test_wrapping_root_avoids_def_name_collisions() -> None:
    s = {
        "anyOf": [
            {"type": "object", "properties": {"c": {"$ref": "#"}, "d": {"$ref": "#/$defs/__root"}}},
            {"type": "string"},
        ],
        "$defs": {"__root": {"type": "integer"}},
    }
    r = run(s, "openai")
    assert set(r.schema["$defs"]) == {"__root", "__root_1"}


def test_non_string_dollar_schema_is_invalid() -> None:
    with pytest.raises(InvalidInputError, match="must be a string"):
        normalize_schema({"$schema": 7, "type": "object"}, "openai")


def test_draft07_id_fragment_is_an_anchor() -> None:
    s = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {"a": {"$ref": "#item"}},
        "definitions": {"Item": {"$id": "#item", "type": "string"}},
    }
    r = run(s, "openai")
    assert r.schema["properties"]["a"] == {"$ref": "#/$defs/Item"}


def test_pointer_into_array_and_invalid_pointers() -> None:
    s = {
        "type": "object",
        "properties": {
            "a": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
            "b": {"$ref": "#/properties/a/anyOf/1"},
        },
    }
    r = run(s, "openai")
    assert r.schema["properties"]["b"] == {"$ref": "#/$defs/1"}
    for bad in (
        "#/properties/a/anyOf/x",
        "#/properties/a/anyOf/9",
        "#/properties/a/type",
        "#/%E0%A4%A",
    ):
        rr = normalize_schema(
            {
                "type": "object",
                "properties": {"b": {"$ref": bad}, "a": {"anyOf": [{"type": "string"}]}},
            },
            "openai",
        )
        assert rr.schema is None, bad


def test_nullability_detection_through_refs_and_booleans() -> None:
    s = {
        "type": "object",
        "properties": {
            "maybe": {"$ref": "#/$defs/MaybeStr"},
            "anything": True,
            "loop": {"$ref": "#/$defs/Loop"},
        },
        "$defs": {
            "MaybeStr": {"type": ["string", "null"]},
            "Loop": {"anyOf": [{"$ref": "#/$defs/Loop"}, {"type": "string"}]},
        },
    }
    r = normalize_schema(s, "openai-strict")
    ambiguous = {e.source_path for e in r.report.entries if e.tid == "T11b"}
    assert "/properties/maybe" in ambiguous
    reversible = {e.source_path for e in r.report.entries if e.tid == "T11a"}
    assert "/properties/loop" in reversible


def test_const_with_null_injection() -> None:
    s = {"type": "object", "properties": {"k": {"type": "string", "const": "x"}}}
    r = run(s, "openai-strict")
    assert r.schema["properties"]["k"] == {"type": ["string", "null"], "enum": ["x", None]}
    assert denormalize_args(r, {"k": None}).args == {}


def test_multi_type_split_with_enum_values_and_existing_anyof() -> None:
    s = {
        "type": "object",
        "properties": {
            "v": {
                "type": ["string", "integer"],
                "enum": ["a", 1],
                "anyOf": [{"minLength": 1}, {"minimum": 0}],
            }
        },
        "required": ["v"],
    }
    r = run(s, "openai-strict")
    branches = r.schema["properties"]["v"]["anyOf"]
    assert {b["type"] for b in branches} == {"string", "integer"}

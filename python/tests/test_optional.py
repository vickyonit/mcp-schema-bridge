"""S8 / T11: optional -> required + nullable (openai-strict), with round-trip."""

from typing import Any

import pytest

from mcp_schema_bridge import denormalize_args, normalize_schema
from tests.support.invariants import no_silent_loss

T = "openai-strict"


def run(schema: dict[str, Any]) -> Any:
    r = normalize_schema(schema, T)
    assert no_silent_loss(schema, r) == []
    return r


def entries(r: Any, tid: str) -> list[tuple[str | None, str, str]]:
    return [(e.keyword, e.action, e.severity) for e in r.report.entries if e.tid == tid]


def test_optional_string_becomes_required_nullable_and_round_trips() -> None:
    r = run(
        {
            "type": "object",
            "properties": {"q": {"type": "string"}, "limit": {"type": "integer"}},
            "required": ["q"],
        }
    )
    assert r.schema["required"] == ["q", "limit"]
    assert r.schema["properties"]["limit"] == {"type": ["integer", "null"]}
    assert entries(r, "T11a") == [("type", "rewritten", "reversible")]
    assert denormalize_args(r, {"q": "x", "limit": None}).args == {"q": "x"}
    assert denormalize_args(r, {"q": "x", "limit": 5}).args == {"q": "x", "limit": 5}


def test_enum_gets_null_value() -> None:
    r = run({"type": "object", "properties": {"o": {"type": "string", "enum": ["asc", "desc"]}}})
    assert r.schema["properties"]["o"] == {
        "type": ["string", "null"],
        "enum": ["asc", "desc", None],
    }


def test_ref_is_wrapped_at_use_site_not_in_def() -> None:
    s = {
        "type": "object",
        "properties": {"a": {"$ref": "#/$defs/N"}, "b": {"$ref": "#/$defs/N"}},
        "required": ["a"],
        "$defs": {"N": {"type": "string"}},
    }
    r = run(s)
    assert r.schema["$defs"]["N"] == {"type": "string"}
    assert r.schema["properties"]["a"] == {"$ref": "#/$defs/N"}
    assert r.schema["properties"]["b"] == {"anyOf": [{"$ref": "#/$defs/N"}, {"type": "null"}]}
    assert denormalize_args(r, {"a": "x", "b": None}).args == {"a": "x"}


def test_anyof_gets_null_branch() -> None:
    r = run(
        {
            "type": "object",
            "properties": {"u": {"anyOf": [{"type": "string"}, {"type": "integer"}]}},
        }
    )
    assert r.schema["properties"]["u"]["anyOf"][-1] == {"type": "null"}


def test_already_nullable_optional_is_lossy_and_null_passes_through() -> None:
    r = run({"type": "object", "properties": {"n": {"type": ["string", "null"]}}})
    assert r.schema["properties"]["n"] == {"type": ["string", "null"]}
    assert r.schema["required"] == ["n"]
    assert entries(r, "T11b") == [("required", "rewritten", "lossy")]
    [e] = [e for e in r.report.entries if e.tid == "T11b"]
    assert e.rule == "openai-strict/optional-nullable-ambiguous"
    assert denormalize_args(r, {"n": None}).args == {"n": None}


def test_nested_optional_properties_round_trip() -> None:
    s = {
        "type": "object",
        "properties": {
            "filter": {
                "type": "object",
                "properties": {"tag": {"type": "string"}, "max": {"type": "integer"}},
                "required": ["tag"],
            }
        },
    }
    r = run(s)
    out = denormalize_args(r, {"filter": {"tag": "a", "max": None}}).args
    assert out == {"filter": {"tag": "a"}}
    out = denormalize_args(r, {"filter": None}).args
    assert out == {}


def test_optional_inside_recursive_def_round_trips() -> None:
    s = {
        "type": "object",
        "properties": {"head": {"$ref": "#/$defs/Node"}},
        "required": ["head"],
        "$defs": {
            "Node": {
                "type": "object",
                "properties": {"v": {"type": "string"}, "next": {"$ref": "#/$defs/Node"}},
                "required": ["v"],
            }
        },
    }
    r = run(s)
    args = {"head": {"v": "1", "next": {"v": "2", "next": None}}}
    assert denormalize_args(r, args).args == {"head": {"v": "1", "next": {"v": "2"}}}


def test_required_inside_anyof_branch_stays_non_nullable() -> None:
    s = {
        "type": "object",
        "properties": {
            "x": {
                "anyOf": [
                    {"type": "object", "properties": {"k": {"type": "string"}}, "required": ["k"]},
                    {"type": "integer"},
                ]
            }
        },
        "required": ["x"],
    }
    r = run(s)
    branch = r.schema["properties"]["x"]["anyOf"][0]
    assert branch["properties"]["k"] == {"type": "string"}


@pytest.mark.parametrize("target", ["openai", "anthropic", "anthropic-strict", "gemini-json"])
def test_other_targets_keep_optionals(target: str) -> None:
    s = {"type": "object", "properties": {"q": {"type": "string"}}}
    r = normalize_schema(s, target)  # type: ignore[arg-type]
    assert "required" not in r.schema


def test_optional_nullable_with_default_null_is_reversible_not_lossy() -> None:
    # Pydantic `x: str | None = None` emits default null: omitted and null mean the same thing.
    s = {
        "type": "object",
        "properties": {"email": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None}},
    }
    r = run(s)
    [e] = [e for e in r.report.entries if e.keyword == "required"]
    assert (e.rule, e.severity) == ("openai-strict/optional-nullable-default-null", "reversible")
    assert denormalize_args(r, {"email": None}).args == {}
    assert denormalize_args(r, {"email": "a@b.c"}).args == {"email": "a@b.c"}


def test_optional_nullable_with_non_null_default_stays_lossy() -> None:
    s = {"type": "object", "properties": {"n": {"type": ["string", "null"], "default": "x"}}}
    r = run(s)
    assert any(e.rule == "openai-strict/optional-nullable-ambiguous" for e in r.report.entries)

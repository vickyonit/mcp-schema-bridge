"""S3 / T7: allOf merge (spec/allof-merge.md)."""

from typing import Any

import pytest

from mcp_schema_bridge import normalize_schema
from tests.support.invariants import no_silent_loss

T = "openai-strict"


def prop(schema: dict[str, Any], target: str = "gemini-json") -> Any:
    original = {"type": "object", "properties": {"p": schema}, "required": ["p"]}
    r = normalize_schema(original, target)  # type: ignore[arg-type]
    assert no_silent_loss(original, r) == []
    return r, (r.schema["properties"]["p"] if r.schema else None)


def entries(r: Any, tid: str = "T7") -> list[tuple[str | None, str, str]]:
    return sorted(
        ((e.keyword, e.action, e.severity) for e in r.report.entries if e.tid == tid),
        key=lambda t: (t[0] or "", t[1], t[2]),
    )


def test_properties_union_and_required_union_in_first_seen_order() -> None:
    _, p = prop(
        {
            "allOf": [
                {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]},
                {
                    "type": "object",
                    "properties": {"b": {"type": "integer"}},
                    "required": ["b", "a"],
                },
            ]
        }
    )
    assert p == {
        "type": "object",
        "properties": {"a": {"type": "string"}, "b": {"type": "integer"}},
        "required": ["a", "b"],
    }


def test_same_named_properties_merge_recursively_with_bounds() -> None:
    _, p = prop(
        {
            "allOf": [
                {"properties": {"n": {"type": "number", "minimum": 1, "maximum": 10}}},
                {"properties": {"n": {"type": "integer", "minimum": 3, "maximum": 20}}},
            ]
        }
    )
    assert p == {"properties": {"n": {"type": "integer", "minimum": 3, "maximum": 10}}}


def test_merged_values_are_reported_as_info() -> None:
    r, _ = prop({"allOf": [{"type": "integer", "minimum": 1}, {"minimum": 3}]})
    assert ("allOf", "merged", "info") in entries(r)
    assert ("minimum", "merged", "info") in entries(r)


def test_type_intersection_empty_is_fatal() -> None:
    r, p = prop({"allOf": [{"type": "string"}, {"type": "integer"}]})
    assert p is None
    assert ("type", "rejected", "fatal") in entries(r)


def test_enum_intersection_and_const() -> None:
    _, p = prop({"allOf": [{"enum": ["a", "b", "c"]}, {"enum": ["c", "b", "z"]}]})
    assert p == {"enum": ["b", "c"]}
    _, p = prop({"allOf": [{"enum": ["a", "b"]}, {"const": "b"}]}, "openai")
    # openai (non-strict) keeps allOf as-is
    assert p == {"allOf": [{"enum": ["a", "b"]}, {"const": "b"}]}
    r, p = prop({"allOf": [{"const": "a"}, {"const": "b"}]})
    assert p is None
    assert ("const", "rejected", "fatal") in entries(r)


def test_additional_properties_false_restricts_merged_properties() -> None:
    r, p = prop(
        {
            "allOf": [
                {
                    "type": "object",
                    "properties": {"a": {"type": "string"}},
                    "additionalProperties": False,
                },
                {"type": "object", "properties": {"b": {"type": "string"}}},
            ]
        }
    )
    assert p == {
        "type": "object",
        "properties": {"a": {"type": "string"}},
        "additionalProperties": False,
    }
    assert (None, "narrowed", "info") in entries(r)


def test_additional_properties_false_with_required_forbidden_property_is_fatal() -> None:
    r, p = prop(
        {
            "allOf": [
                {
                    "type": "object",
                    "properties": {"a": {"type": "string"}},
                    "additionalProperties": False,
                },
                {"type": "object", "properties": {"b": {"type": "string"}}, "required": ["b"]},
            ]
        }
    )
    assert p is None
    assert ("required", "rejected", "fatal") in entries(r)


def test_conflicting_patterns_keep_first_and_hint_rest() -> None:
    r, p = prop(
        {"allOf": [{"type": "string", "pattern": "^a"}, {"pattern": "b$"}]}, "openai-strict"
    )
    assert p["pattern"] == "^a"
    [e] = [e for e in r.report.entries if e.tid == "T7" and e.keyword == "pattern"]
    assert (e.action, e.severity, e.original) == ("dropped", "lossy", "b$")


def test_anyof_inside_allof_is_distributed() -> None:
    _, p = prop(
        {
            "allOf": [
                {"type": "object", "properties": {"k": {"type": "string"}}},
                {"anyOf": [{"required": ["k"]}, {"properties": {"z": {"type": "integer"}}}]},
            ]
        }
    )
    assert p == {
        "type": "object",
        "properties": {"k": {"type": "string"}},
        "anyOf": [{"required": ["k"]}, {"properties": {"z": {"type": "integer"}}}],
    }


def test_not_and_conditionals_in_multiple_branches_keep_first() -> None:
    r, p = prop(
        {"allOf": [{"type": "string", "not": {"const": "x"}}, {"not": {"const": "y"}}]}, "openai"
    )
    # non-strict openai keeps allOf; check the merge itself on a target that merges:
    r, p = prop({"allOf": [{"type": "string", "not": {"const": "x"}}, {"not": {"const": "y"}}]})
    assert "not" not in p  # gemini-json does not enforce `not`; dropped by the filter (T12)
    assert ("not", "dropped", "lossy") in entries(r)
    assert any(e.tid == "T12" and e.keyword == "not" for e in r.report.entries)


def test_ref_branches_are_resolved_before_merging() -> None:
    s = {
        "type": "object",
        "properties": {
            "p": {"allOf": [{"$ref": "#/$defs/Base"}, {"properties": {"y": {"type": "integer"}}}]}
        },
        "$defs": {
            "Base": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}
        },
    }
    r = normalize_schema(s, "gemini-json")
    assert r.schema is not None
    assert r.schema["properties"]["p"] == {
        "type": "object",
        "properties": {"x": {"type": "string"}, "y": {"type": "integer"}},
        "required": ["x"],
    }
    assert "$defs" not in r.schema  # Base is no longer referenced


def test_annotations_merge_deterministically() -> None:
    r, p = prop(
        {
            "allOf": [
                {"description": "A", "title": "T1", "default": 1},
                {"description": "B", "title": "T2", "default": 2},
            ]
        }
    )
    assert p == {"description": "A\n\nB", "title": "T1", "default": 1}
    assert ("default", "merged", "info") in entries(r)


def test_nested_allof_merges_innermost_first() -> None:
    _, p = prop({"allOf": [{"allOf": [{"minimum": 1}, {"maximum": 5}]}, {"type": "integer"}]})
    assert p == {"minimum": 1, "maximum": 5, "type": "integer"}


@pytest.mark.parametrize("target", ["openai", "anthropic"])
def test_non_strict_targets_keep_allof(target: str) -> None:
    s = {"allOf": [{"type": "string"}, {"minLength": 1}]}
    _, p = prop(s, target)
    assert p == s

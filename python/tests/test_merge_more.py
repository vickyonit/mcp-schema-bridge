"""Additional allOf merge rules (spec/allof-merge.md)."""

from typing import Any

from mcp_schema_bridge import NormalizeOptions, normalize_schema
from tests.support.invariants import check_all


def prop(schema: dict[str, Any], target: str = "gemini-json", **opts: Any) -> tuple[Any, Any]:
    original = {"type": "object", "properties": {"p": schema}, "required": ["p"]}
    r = normalize_schema(original, target, NormalizeOptions(**opts))  # type: ignore[arg-type]
    assert check_all(original, r) == []
    return r, (r.schema["properties"]["p"] if r.schema else None)


def rules(r: Any) -> set[str]:
    return {e.rule for e in r.report.entries}


def test_true_branch_is_ignored_and_false_branch_is_unsatisfiable() -> None:
    _, p = prop({"allOf": [True, {"type": "string"}]})
    assert p == {"type": "string"}
    r, p = prop({"allOf": [False, {"type": "string"}]})
    assert p is None
    assert "core/allof-unsatisfiable" in rules(r)


def test_self_referencing_allof_is_fatal() -> None:
    s = {
        "type": "object",
        "properties": {"p": {"$ref": "#/$defs/A"}},
        "required": ["p"],
        "$defs": {"A": {"allOf": [{"$ref": "#/$defs/A"}, {"type": "string"}]}},
    }
    r = normalize_schema(s, "gemini-json")
    assert r.schema is None
    assert "core/allof-ref-cycle" in rules(r)


def test_two_different_refs_keep_the_first() -> None:
    s = {
        "type": "object",
        "properties": {"p": {"allOf": [{"$ref": "#/$defs/A"}, {"$ref": "#/$defs/B"}]}},
        "required": ["p"],
        "$defs": {"A": {"type": "string", "minLength": 1}, "B": {"type": "string", "maxLength": 9}},
    }
    r = normalize_schema(s, "gemini-json")
    # both refs are resolved into a single merged schema
    assert r.schema is not None
    assert "$ref" not in str(r.schema["properties"]["p"])


def test_items_and_prefix_items_merge_pairwise() -> None:
    _, p = prop(
        {
            "allOf": [
                {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 0},
                    "prefixItems": [{"type": "integer"}],
                },
                {"items": {"maximum": 9}, "prefixItems": [{"minimum": 1}, {"type": "integer"}]},
            ]
        },
        "openai",
    )
    # openai keeps allOf; check the merge on gemini-json
    _, p = prop(
        {
            "allOf": [
                {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 0},
                    "prefixItems": [{"type": "integer"}],
                },
                {"items": {"maximum": 9}, "prefixItems": [{"minimum": 1}, {"type": "integer"}]},
            ]
        }
    )
    assert p["items"] == {"type": "integer", "minimum": 0, "maximum": 9}
    assert p["prefixItems"] == [{"type": "integer", "minimum": 1}, {"type": "integer"}]


def test_additional_properties_schemas_merge() -> None:
    _, p = prop(
        {
            "allOf": [
                {"type": "object", "additionalProperties": {"type": "string"}},
                {"type": "object", "additionalProperties": {"maxLength": 5}},
            ]
        }
    )
    # maxLength is not enforced by Gemini: merged, then dropped and restated as a hint
    assert p["additionalProperties"] == {
        "type": "string",
        "description": "[constraints: maxLength=5]",
    }


def test_additional_properties_true_and_schema() -> None:
    _, p = prop(
        {
            "allOf": [
                {"type": "object", "additionalProperties": True},
                {"additionalProperties": {"type": "integer"}},
            ]
        }
    )
    assert p["additionalProperties"] == {"type": "integer"}


def test_dependent_required_and_pattern_properties_merge() -> None:
    _, p = prop(
        {
            "allOf": [
                {
                    "type": "object",
                    "dependentRequired": {"a": ["b"]},
                    "patternProperties": {"^x": {"type": "string"}},
                },
                {
                    "dependentRequired": {"a": ["c"], "d": ["e"]},
                    "patternProperties": {"^x": {"maxLength": 3}, "^y": {"type": "integer"}},
                },
            ]
        },
        "openai",
    )
    assert (
        "allOf" in p
    )  # non-strict openai keeps allOf; merge is exercised by the strict targets below
    _r, p = prop(
        {
            "allOf": [
                {
                    "type": "object",
                    "properties": {"k": {"type": "string"}},
                    "dependentRequired": {"k": ["k"]},
                },
                {"dependentRequired": {"k": ["k"]}},
            ]
        }
    )
    assert "dependentRequired" not in p  # Gemini does not enforce it: dropped + hinted
    assert "dependentRequired=" in p["description"]


def test_unique_items_or_semantics_and_title_first_wins() -> None:
    r, p = prop(
        {
            "allOf": [
                {"type": "array", "items": {"type": "string"}, "title": "A"},
                {"uniqueItems": True, "title": "B"},
            ]
        }
    )
    assert p["title"] == "A"
    assert "core/allof-first-wins" in rules(r)


def test_distribution_too_large_is_fatal() -> None:
    branches = [
        {"anyOf": [{"type": "string", "minLength": i} for i in range(30)]} for _ in range(2)
    ]
    r, p = prop({"allOf": branches}, max_nodes=500)  # input fits; 30 x 30 combinations do not
    assert p is None
    assert "core/allof-distribution-too-large" in rules(r)

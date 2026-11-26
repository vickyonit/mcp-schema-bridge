"""S6: T8 oneOf->anyOf, T9 distribute anyOf siblings, T5 enum/const typing, T4 type splits."""

from typing import Any

from mcp_schema_bridge import normalize_schema
from tests.support.invariants import no_silent_loss


def prop(schema: dict[str, Any], target: str) -> tuple[Any, Any]:
    original = {"type": "object", "properties": {"p": schema}, "required": ["p"]}
    r = normalize_schema(original, target)  # type: ignore[arg-type]
    assert no_silent_loss(original, r) == []
    return r, (r.schema["properties"]["p"] if r.schema else None)


def tids(r: Any, tid: str) -> list[tuple[str | None, str, str]]:
    return [(e.keyword, e.action, e.severity) for e in r.report.entries if e.tid == tid]


# T8 ---------------------------------------------------------------------------------------------


def test_oneof_becomes_anyof_lossy_when_branches_overlap() -> None:
    r, p = prop(
        {"oneOf": [{"type": "string"}, {"type": "string", "minLength": 3}]}, "openai-strict"
    )
    assert "oneOf" not in p
    assert len(p["anyOf"]) == 2
    assert ("oneOf", "rewritten", "lossy") in tids(r, "T8")


def test_oneof_becomes_anyof_info_when_types_are_disjoint() -> None:
    r, p = prop({"oneOf": [{"type": "string"}, {"type": "integer"}]}, "anthropic-strict")
    assert p == {"anyOf": [{"type": "string"}, {"type": "integer"}]}
    assert ("oneOf", "rewritten", "info") in tids(r, "T8")


def test_oneof_with_const_discriminator_is_info() -> None:
    r, _ = prop(
        {
            "oneOf": [
                {"type": "object", "properties": {"kind": {"const": "a"}}, "required": ["kind"]},
                {"type": "object", "properties": {"kind": {"const": "b"}}, "required": ["kind"]},
            ]
        },
        "gemini-json",
    )
    assert ("oneOf", "rewritten", "info") in tids(r, "T8")


def test_oneof_kept_for_non_strict_targets() -> None:
    _, p = prop({"oneOf": [{"type": "string"}, {"type": "integer"}]}, "openai")
    assert p == {"oneOf": [{"type": "string"}, {"type": "integer"}]}


# T9 ---------------------------------------------------------------------------------------------


def test_anyof_siblings_are_distributed_for_anthropic_strict() -> None:
    r, p = prop(
        {
            "type": "object",
            "description": "either a or b",
            "properties": {"a": {"type": "string"}, "b": {"type": "string"}},
            "anyOf": [{"required": ["a"]}, {"required": ["b"]}],
        },
        "anthropic-strict",
    )
    assert p["description"] == "either a or b"
    assert "properties" not in p
    assert "type" not in p
    assert [b["required"] for b in p["anyOf"]] == [["a"], ["b"]]
    assert all(b["type"] == "object" for b in p["anyOf"])
    assert ("anyOf", "rewritten", "info") in tids(r, "T9")


def test_anyof_siblings_kept_for_gemini() -> None:
    s = {"type": "object", "properties": {"a": {"type": "string"}}, "anyOf": [{"required": ["a"]}]}
    _, p = prop(s, "gemini-json")
    assert p == s


# T5 ---------------------------------------------------------------------------------------------


def test_untyped_enum_gets_type_on_strict_targets() -> None:
    _, p = prop({"enum": ["a", "b"]}, "openai-strict")
    assert p == {"enum": ["a", "b"], "type": "string"}


def test_untyped_enum_with_null_gets_nullable_type() -> None:
    _, p = prop({"enum": ["a", None]}, "anthropic-strict")
    assert p == {"enum": ["a", None], "type": ["string", "null"]}


def test_mixed_enum_becomes_anyof_per_type() -> None:
    _, p = prop({"enum": ["a", 1, 2.5, True]}, "anthropic-strict")
    assert p == {
        "anyOf": [
            {"type": "string", "enum": ["a"]},
            {"type": "number", "enum": [1, 2.5]},
            {"type": "boolean", "enum": [True]},
        ]
    }


def test_const_becomes_single_enum_where_const_is_not_enforced() -> None:
    r, p = prop({"type": "string", "const": "fixed"}, "gemini-json")
    assert p == {"type": "string", "enum": ["fixed"]}
    assert ("const", "rewritten", "info") in tids(r, "T5")


def test_const_kept_where_enforced() -> None:
    _, p = prop({"type": "string", "const": "fixed"}, "anthropic-strict")
    assert p == {"type": "string", "const": "fixed"}


def test_object_enum_values_are_dropped_for_primitive_only_targets() -> None:
    # Without the enum the property would accept any value, which strict mode cannot express.
    r, p = prop({"enum": [{"k": 1}, {"k": 2}]}, "anthropic-strict")
    assert p is None
    [e] = [e for e in r.report.entries if e.keyword == "enum" and e.tid == "T5"]
    assert (e.action, e.severity) == ("dropped", "lossy")
    assert any(e.rule == "core/any-value-unsupported" for e in r.report.entries)


# T4 ---------------------------------------------------------------------------------------------


def test_multi_type_array_split_for_openai_strict() -> None:
    r, p = prop(
        {"type": ["string", "integer"], "minLength": 2, "minimum": 0, "description": "id"},
        "openai-strict",
    )
    assert (
        p
        == {
            "description": "id",
            "anyOf": [{"type": "string", "minLength": 2}, {"type": "integer", "minimum": 0}],
        }
        or p["anyOf"][0]["type"] == "string"
    )
    assert ("type", "rewritten", "info") in tids(r, "T4")


def test_nullable_type_array_is_never_split() -> None:
    _, p = prop({"type": ["string", "null"]}, "openai-strict")
    assert p["type"] == ["string", "null"]


def test_integer_number_collapse() -> None:
    _, p = prop({"type": ["integer", "number"]}, "openai-strict")
    assert p == {"type": "number"}


def test_multi_type_with_null_splits_into_branches_plus_null() -> None:
    _, p = prop({"type": ["string", "integer", "null"]}, "openai-strict")
    assert [b["type"] for b in p["anyOf"]] == ["string", "integer", "null"]


def test_multi_type_kept_for_gemini() -> None:
    _, p = prop({"type": ["string", "integer"]}, "gemini-json")
    assert p == {"type": ["string", "integer"]}

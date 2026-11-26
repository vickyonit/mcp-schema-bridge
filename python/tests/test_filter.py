"""S9: keyword filter (T1, T12, T13, T15, T16)."""

from typing import Any

from mcp_schema_bridge import normalize_schema
from tests.support.invariants import allow_list, no_silent_loss


def prop(schema: dict[str, Any], target: str) -> tuple[Any, Any]:
    original = {"type": "object", "properties": {"p": schema}, "required": ["p"]}
    r = normalize_schema(original, target)  # type: ignore[arg-type]
    assert no_silent_loss(original, r) == []
    assert allow_list(r) == []
    return r, (r.schema["properties"]["p"] if r.schema else None)


def kinds(r: Any) -> list[tuple[str, str | None, str, str]]:
    return sorted(
        (e.tid, e.keyword, e.action, e.severity)
        for e in r.report.entries
        if e.tid in ("T1", "T12", "T13", "T15", "T16")
    )


def test_gemini_drops_stripped_validation_keywords_as_lossy() -> None:
    r, p = prop(
        {"type": "string", "pattern": "^Z", "minLength": 2, "description": "code"}, "gemini-json"
    )
    assert p == {
        "type": "string",
        "description": 'code\n\n[constraints: minLength=2; pattern="^Z"]',
    }
    assert kinds(r) == [
        ("T12", "minLength", "dropped", "lossy"),
        ("T12", "pattern", "dropped", "lossy"),
    ]
    assert {e.rule for e in r.report.entries} == {"gemini-json/keyword-not-enforced"}


def test_gemini_keeps_enforced_keywords() -> None:
    s = {"type": "integer", "minimum": 1, "maximum": 9}
    _, p = prop(s, "gemini-json")
    assert p == s


def test_integer_exclusive_bounds_become_inclusive_where_only_inclusive_is_enforced() -> None:
    r, p = prop({"type": "integer", "exclusiveMinimum": 0, "exclusiveMaximum": 10}, "gemini-json")
    assert p == {"type": "integer", "minimum": 1, "maximum": 9}
    assert all(sev == "info" for _, _, _, sev in kinds(r))


def test_number_exclusive_bounds_are_dropped_with_hint() -> None:
    r, p = prop({"type": "number", "exclusiveMinimum": 0}, "gemini-json")
    assert p == {"type": "number", "description": "[constraints: exclusiveMinimum=0]"}
    assert kinds(r) == [("T12", "exclusiveMinimum", "dropped", "lossy")]


def test_gemini_formats_outside_enforced_set_are_dropped() -> None:
    r, p = prop({"type": "string", "format": "email"}, "gemini-json")
    assert p == {"type": "string", "description": '[constraints: format="email"]'}
    assert kinds(r) == [("T15", "format", "dropped", "lossy")]
    _, p = prop({"type": "string", "format": "date"}, "gemini-json")
    assert p == {"type": "string", "format": "date"}


def test_openai_strict_drops_unlisted_keywords() -> None:
    r, p = prop(
        {"type": "string", "minLength": 1, "format": "uri", "default": "x", "examples": ["a"]},
        "openai-strict",
    )
    assert p == {
        "type": "string",
        "description": '[constraints: default="x"; format="uri"; minLength=1]',
    }
    assert kinds(r) == [
        ("T1", "examples", "dropped", "info"),
        ("T12", "minLength", "dropped", "lossy"),
        ("T13", "default", "dropped", "info"),
        ("T15", "format", "dropped", "lossy"),
    ]


def test_anthropic_strict_pattern_with_forbidden_features_is_dropped() -> None:
    r, p = prop({"type": "string", "pattern": "^(?=.*\\d).+$"}, "anthropic-strict")
    assert "pattern" not in p
    assert kinds(r) == [("T16", "pattern", "dropped", "lossy")]
    _, p = prop({"type": "string", "pattern": "^[a-z]+$"}, "anthropic-strict")
    assert p["pattern"] == "^[a-z]+$"


def test_anthropic_strict_min_items_is_clamped_to_one() -> None:
    r, p = prop(
        {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 5},
        "anthropic-strict",
    )
    assert p == {
        "type": "array",
        "items": {"type": "string"},
        "minItems": 1,
        "description": "[constraints: maxItems=5; minItems=3]",
    }
    assert kinds(r) == [
        ("T12", "maxItems", "dropped", "lossy"),
        ("T12", "minItems", "rewritten", "lossy"),
    ]


def test_applicators_are_dropped_with_subtree_coverage() -> None:
    r, p = prop({"type": "string", "not": {"enum": ["x"]}}, "openai-strict")
    # T5 typed the enum inside `not` first (equivalent: the type is inferred from the values).
    assert p == {
        "type": "string",
        "description": '[constraints: not={"enum":["x"],"type":"string"}]',
    }
    assert kinds(r) == [("T12", "not", "dropped", "lossy")]


def test_extensions_and_annotations() -> None:
    _, p = prop({"type": "string", "x-mcp-header": "X-Q", "deprecated": True}, "openai-strict")
    assert p == {"type": "string"}
    _, p = prop({"type": "string", "x-mcp-header": "X-Q"}, "gemini-json")
    assert p == {"type": "string", "x-mcp-header": "X-Q"}


def test_non_strict_targets_keep_everything() -> None:
    s = {
        "type": "string",
        "pattern": "^Z",
        "minLength": 2,
        "format": "email",
        "x-a": 1,
        "not": {"const": "q"},
    }
    for target in ("openai", "anthropic"):
        _, p = prop(s, target)
        assert p == s

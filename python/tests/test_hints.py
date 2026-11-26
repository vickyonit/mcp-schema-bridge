"""S10: description hints (spec/hint-format.md)."""

from typing import Any

from mcp_schema_bridge import NormalizeOptions, normalize_schema
from tests.support.invariants import idempotent, no_silent_loss


def prop(schema: dict[str, Any], target: str = "gemini-json", **opts: Any) -> tuple[Any, Any]:
    original = {"type": "object", "properties": {"p": schema}, "required": ["p"]}
    r = normalize_schema(original, target, NormalizeOptions(**opts))  # type: ignore[arg-type]
    assert no_silent_loss(original, r) == []
    assert idempotent(r) == []
    return r, (r.schema["properties"]["p"] if r.schema else None)


def test_hint_appended_with_sorted_jcs_values() -> None:
    r, p = prop(
        {"type": "string", "pattern": "^[A-Z]{2}$", "minLength": 2, "description": "Country code"}
    )
    assert p["description"] == 'Country code\n\n[constraints: minLength=2; pattern="^[A-Z]{2}$"]'
    assert all(e.hinted for e in r.report.entries if e.severity == "lossy")


def test_hint_is_whole_description_when_none() -> None:
    _, p = prop({"type": "integer", "multipleOf": 5})
    assert p["description"] == "[constraints: multipleOf=5]"


def test_hints_disabled() -> None:
    r, p = prop({"type": "integer", "multipleOf": 5}, hints=False)
    assert "description" not in p
    assert not any(e.hinted for e in r.report.entries)


def test_existing_hint_block_is_merged_not_duplicated() -> None:
    _, p = prop(
        {"type": "string", "minLength": 1, "description": 'x\n\n[constraints: pattern="a"]'}
    )
    assert p["description"] == 'x\n\n[constraints: minLength=1; pattern="a"]'


def test_long_values_are_truncated_with_ellipsis() -> None:
    long = "a" * 300
    r, p = prop({"type": "string", "pattern": long})
    body = p["description"][len("[constraints: pattern=") : -1]
    assert len(body) == 200
    assert body.endswith("…")
    [e] = [e for e in r.report.entries if e.keyword == "pattern"]
    assert e.original == long


def test_max_description_chars_truncates_original_text_only() -> None:
    _, p = prop(
        {"type": "integer", "multipleOf": 5, "description": "abcdefghij"}, max_description_chars=5
    )
    assert p["description"] == "abcd…\n\n[constraints: multipleOf=5]"


def test_default_is_hinted_on_openai_strict() -> None:
    _, p = prop({"type": "string", "default": "asc"}, "openai-strict")
    assert p["description"] == '[constraints: default="asc"]'


def test_annotations_are_never_hinted() -> None:
    _, p = prop({"type": "string", "examples": ["a"], "deprecated": True}, "openai-strict")
    assert "description" not in p


def test_null_default_is_hinted() -> None:
    _, p = prop({"type": ["string", "null"], "default": None}, "openai-strict")
    assert p["description"] == "[constraints: default=null]"

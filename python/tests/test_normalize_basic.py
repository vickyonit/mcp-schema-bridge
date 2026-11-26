"""Public normalize_schema behaviour on trivially compatible input."""

import pytest

from mcp_schema_bridge import NormalizeOptions, normalize_schema
from mcp_schema_bridge.core.errors import InvalidInputError
from mcp_schema_bridge.core.rules import TARGETS

SIMPLE = {
    "type": "object",
    "properties": {"city": {"type": "string", "description": "City name"}},
    "required": ["city"],
}


@pytest.mark.parametrize("target", ["openai", "anthropic", "gemini-json"])
def test_compatible_schema_passes_through_unchanged(target: str) -> None:
    result = normalize_schema(SIMPLE, target)  # type: ignore[arg-type]
    assert result.schema == SIMPLE
    assert result.report.entries == []
    assert result.target == target
    assert result.strict is False


def test_input_is_not_mutated() -> None:
    import copy

    original = copy.deepcopy(SIMPLE)
    normalize_schema(SIMPLE, "openai-strict")
    assert original == SIMPLE


@pytest.mark.parametrize("target", TARGETS)
def test_result_carries_fingerprint_and_versions(target: str) -> None:
    r = normalize_schema(SIMPLE, target)
    assert len(r.fingerprint) == 64
    assert r.reverse.fingerprint == r.fingerprint
    assert r.reverse.rules_version == r.rules_version


def test_fingerprint_depends_on_target_and_input() -> None:
    a = normalize_schema(SIMPLE, "openai").fingerprint
    b = normalize_schema(SIMPLE, "anthropic").fingerprint
    c = normalize_schema({**SIMPLE, "description": "x"}, "openai").fingerprint
    assert len({a, b, c}) == 3


def test_invalid_input_raises() -> None:
    with pytest.raises(InvalidInputError):
        normalize_schema({"maximum": float("nan")}, "openai")


def test_unknown_target_raises_value_error() -> None:
    with pytest.raises(ValueError, match="unknown target"):
        normalize_schema(SIMPLE, "nope")  # type: ignore[arg-type]


def test_options_are_frozen_with_documented_defaults() -> None:
    o = NormalizeOptions()
    assert o.hints is True
    assert o.on_unsupported == "report"
    assert o.max_ref_depth == 3
    assert o.max_nodes == 10_000
    assert o.max_depth == 64
    assert o.strict_fallback is False
    assert o.big_int == "reject"


def test_big_int_round_is_reported_as_lossy_coercion() -> None:
    s = {"type": "object", "properties": {"n": {"type": "integer", "maximum": 9223372036854775807}}}
    r = normalize_schema(s, "openai", NormalizeOptions(big_int="round"))
    assert r.schema is not None
    assert r.schema["properties"]["n"]["maximum"] == 9.223372036854776e18
    [e] = [e for e in r.report.entries if e.rule == "core/big-int-rounded"]
    assert (e.source_path, e.keyword, e.action, e.severity, e.original) == (
        "/properties/n/maximum",
        None,
        "coerced",
        "lossy",
        "9223372036854775807",
    )


def test_normalize_schema_strict_fallback_demotes_to_sibling() -> None:
    s = {"type": "object", "properties": {"m": {"type": "object"}}, "required": ["m"]}
    plain = normalize_schema(s, "anthropic-strict")
    assert plain.schema is None
    r = normalize_schema(s, "anthropic-strict", NormalizeOptions(strict_fallback=True))
    assert (r.target, r.strict) == ("anthropic", False)
    assert r.schema is not None
    assert any(e.action == "fallback" and e.severity == "lossy" for e in r.report.entries)
    assert any(e.severity == "fatal" for e in r.report.entries)  # why it fell back
    assert r.reverse.target == "anthropic"


def test_strict_fallback_has_no_effect_on_non_strict_targets() -> None:
    r = normalize_schema(
        {"type": "object", "properties": {"a": {"$ref": "https://x"}}},
        "openai",
        NormalizeOptions(strict_fallback=True),
    )
    assert r.schema is None

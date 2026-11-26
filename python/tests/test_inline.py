"""S4: recursion analysis, unrolling (T2a), ref-with-siblings inlining (T2b), root $ref."""

from typing import Any

import pytest

from mcp_schema_bridge import normalize_schema
from mcp_schema_bridge.core.options import NormalizeOptions
from mcp_schema_bridge.core.rules import TARGETS
from tests.support.invariants import no_silent_loss

LINKED = {
    "type": "object",
    "properties": {"head": {"$ref": "#/$defs/Node"}},
    "required": ["head"],
    "$defs": {
        "Node": {
            "type": "object",
            "properties": {"value": {"type": "string"}, "next": {"$ref": "#/$defs/Node"}},
            "required": ["value"],
        }
    },
}


def run(schema: dict[str, Any], target: str, **opts: Any) -> Any:
    r = normalize_schema(schema, target, NormalizeOptions(**opts))  # type: ignore[arg-type]
    assert no_silent_loss(schema, r) == []
    return r


def test_optional_recursion_is_kept_for_targets_that_allow_it() -> None:
    for target in ("gemini-json", "openai", "anthropic"):
        assert run(LINKED, target).schema == LINKED


@pytest.mark.parametrize("target", TARGETS)
def test_required_recursion_is_unsatisfiable_and_fatal(target: str) -> None:
    s = {
        "type": "object",
        "properties": {"child": {"$ref": "#"}, "v": {"type": "string"}},
        "required": ["child"],
    }
    r = run(s, target)
    assert r.schema is None
    assert any(
        e.rule == "core/unsatisfiable-recursion" and e.severity == "fatal" for e in r.report.entries
    )


def test_recursion_through_optional_array_is_satisfiable() -> None:
    s = {
        "type": "object",
        "properties": {
            "children": {"type": "array", "items": {"$ref": "#"}},
            "v": {"type": "string"},
        },
        "required": ["children", "v"],
    }
    assert run(s, "gemini-json").schema == s


def test_anthropic_strict_unrolls_recursion_and_cuts_optional_property() -> None:
    r = run(LINKED, "anthropic-strict", max_ref_depth=2)
    assert r.schema is not None
    assert "$defs" not in r.schema
    head = r.schema["properties"]["head"]
    assert head["properties"]["value"] == {"type": "string"}
    level2 = head["properties"]["next"]
    assert "next" not in level2["properties"]  # cut at depth 2
    cuts = [e for e in r.report.entries if e.tid == "T2a"]
    assert [(e.action, e.severity) for e in cuts] == [("truncated", "lossy")]


def test_anthropic_strict_cuts_recursive_anyof_branch() -> None:
    s = {
        "type": "object",
        "properties": {"expr": {"$ref": "#/$defs/E"}},
        "required": ["expr"],
        "$defs": {
            "E": {"anyOf": [{"type": "number"}, {"type": "array", "items": {"$ref": "#/$defs/E"}}]}
        },
    }
    r = run(s, "anthropic-strict", max_ref_depth=1)
    assert r.schema is not None
    assert "$ref" not in str(r.schema)


def test_anthropic_strict_required_array_recursion_is_fatal() -> None:
    s = {
        "type": "object",
        "properties": {"tree": {"$ref": "#/$defs/T"}},
        "required": ["tree"],
        "$defs": {
            "T": {
                "type": "object",
                "properties": {"kids": {"type": "array", "items": {"$ref": "#/$defs/T"}}},
                "required": ["kids"],
            }
        },
    }
    r = run(s, "anthropic-strict")
    assert r.schema is None
    assert any(e.tid == "T2a" and e.severity == "fatal" for e in r.report.entries)


def test_openai_strict_inlines_ref_with_annotation_sibling_when_not_recursive() -> None:
    s = {
        "type": "object",
        "properties": {"a": {"$ref": "#/$defs/N", "description": "the a"}},
        "required": ["a"],
        "$defs": {"N": {"type": "string"}},
    }
    r = run(s, "openai-strict")
    assert r.schema is not None
    assert r.schema["properties"]["a"] == {"type": "string", "description": "the a"}
    assert any(e.tid == "T2b" and e.action == "inlined" for e in r.report.entries)


def test_openai_strict_drops_annotation_sibling_on_recursive_ref() -> None:
    s = {
        "type": "object",
        "properties": {"v": {"type": "string"}, "next": {"$ref": "#", "description": "next node"}},
        "required": ["v"],
    }
    r = run(s, "openai-strict")
    assert r.schema is not None
    nxt = r.schema["properties"]["next"]
    assert "description" not in str(nxt.get("anyOf", nxt))


def test_ref_with_validation_sibling_is_merged_for_openai_strict() -> None:
    s = {
        "type": "object",
        "properties": {"a": {"$ref": "#/$defs/N", "minLength": 2}},
        "required": ["a"],
        "$defs": {"N": {"type": "string", "maxLength": 9}},
    }
    r = run(s, "openai-strict")
    assert r.schema is not None
    a = r.schema["properties"]["a"]
    assert a["type"] == "string"
    assert "$ref" not in a


@pytest.mark.parametrize("target", TARGETS)
def test_root_ref_is_inlined(target: str) -> None:
    s = {
        "$ref": "#/$defs/Args",
        "$defs": {
            "Args": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}
        },
    }
    r = run(s, target)
    assert r.schema is not None
    assert r.schema["type"] == "object"
    assert "q" in r.schema["properties"]
    assert "$ref" not in r.schema

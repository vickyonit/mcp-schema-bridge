"""S7 / T10: closing objects on strict targets."""

from typing import Any

import pytest

from mcp_schema_bridge import normalize_schema
from tests.support.invariants import no_silent_loss

STRICT = ["openai-strict", "anthropic-strict"]


def run(schema: dict[str, Any], target: str) -> Any:
    r = normalize_schema(schema, target)  # type: ignore[arg-type]
    assert no_silent_loss(schema, r) == []
    return r


def t10(r: Any) -> list[tuple[str | None, str, str]]:
    return [(e.keyword, e.action, e.severity) for e in r.report.entries if e.tid == "T10"]


@pytest.mark.parametrize("target", STRICT)
def test_objects_with_properties_are_closed(target: str) -> None:
    s = {
        "type": "object",
        "properties": {
            "o": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}
        },
        "required": ["o"],
    }
    r = run(s, target)
    assert r.schema["additionalProperties"] is False
    assert r.schema["properties"]["o"]["additionalProperties"] is False
    assert t10(r) == [("additionalProperties", "narrowed", "info")] * 2


@pytest.mark.parametrize("target", STRICT)
def test_already_closed_objects_produce_no_entry(target: str) -> None:
    s = {
        "type": "object",
        "properties": {"x": {"type": "string"}},
        "required": ["x"],
        "additionalProperties": False,
    }
    assert t10(run(s, target)) == []


@pytest.mark.parametrize("target", STRICT)
def test_explicitly_open_object_with_properties_is_closed_lossy(target: str) -> None:
    s = {
        "type": "object",
        "properties": {"x": {"type": "string"}},
        "required": ["x"],
        "additionalProperties": True,
    }
    r = run(s, target)
    assert r.schema["additionalProperties"] is False
    assert t10(r) == [("additionalProperties", "narrowed", "lossy")]


@pytest.mark.parametrize("target", STRICT)
@pytest.mark.parametrize("root", [{}, {"type": "object"}, {"type": "object", "properties": {}}])
def test_parameterless_root_is_closed_as_info(target: str, root: dict[str, Any]) -> None:
    r = run(root, target)
    assert r.schema is not None
    assert r.schema["properties"] == {}
    assert r.schema["additionalProperties"] is False
    assert all(sev == "info" for _, _, sev in t10(r))


@pytest.mark.parametrize("target", STRICT)
@pytest.mark.parametrize(
    "open_obj",
    [
        {"type": "object"},
        {"type": "object", "additionalProperties": {"type": "string"}},
        {"type": "object", "patternProperties": {"^x": {"type": "string"}}},
        {},
    ],
)
def test_open_nested_object_or_any_value_is_fatal(target: str, open_obj: dict[str, Any]) -> None:
    r = run({"type": "object", "properties": {"meta": open_obj}, "required": ["meta"]}, target)
    assert r.schema is None
    assert ("additionalProperties", "rejected", "fatal") in t10(r) or (
        None,
        "rejected",
        "fatal",
    ) in t10(r)


@pytest.mark.parametrize("target", ["openai", "anthropic", "gemini-json"])
def test_non_strict_targets_leave_objects_open(target: str) -> None:
    s = {"type": "object", "properties": {"meta": {"type": "object"}}}
    r = run(s, target)
    assert r.schema["properties"]["meta"] == {"type": "object"}
    assert t10(r) == []

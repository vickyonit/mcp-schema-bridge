"""Property 5 (round-trip) and 6 (reverse totality), plan §8.3."""

from __future__ import annotations

from typing import Any

import jsonschema
import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from hypothesis_jsonschema import from_schema

from mcp_schema_bridge import denormalize_args, normalize_schema
from mcp_schema_bridge.core.rules import TARGETS
from tests.strategies import mcp_schemas
from tests.support.invariants import relax

SETTINGS = settings(suppress_health_check=list(HealthCheck), deadline=None, max_examples=40)


def _validator(schema: dict[str, Any]) -> Any:
    cls = jsonschema.validators.validator_for(schema, default=jsonschema.Draft202012Validator)
    return cls(schema, format_checker=cls.FORMAT_CHECKER)


def _without_patterns(schema: Any) -> Any:
    """`pattern` is excluded from the oracle (Python re != ECMA-262)."""
    if isinstance(schema, dict):
        return {k: _without_patterns(v) for k, v in schema.items() if k != "pattern"}
    if isinstance(schema, list):
        return [_without_patterns(v) for v in schema]
    return schema


@pytest.mark.parametrize("target", TARGETS)
@SETTINGS
@given(schema=mcp_schemas(), data=st.data())
def test_round_trip(target: str, schema: dict[str, Any], data: st.DataObject) -> None:
    r = normalize_schema(schema, target)  # type: ignore[arg-type]
    assume(r.schema is not None)
    assume(not any(e.rule == "core/reverse-ambiguous-branch" for e in r.report.entries))
    assert r.schema is not None
    # hypothesis-jsonschema cannot generate instances for recursive references.
    assume("$defs" not in r.schema or "Node" not in r.schema["$defs"])
    try:
        strategy = from_schema(_without_patterns(r.schema))
    except Exception:  # unsupported by the generator
        assume(False)
        return
    instance = data.draw(strategy)
    # The generator does not honour every keyword (e.g. format); only valid model outputs count.
    assume(not any(True for _ in _validator(_without_patterns(r.schema)).iter_errors(instance)))
    out = denormalize_args(r, instance).args
    relaxed = _without_patterns(relax(schema, r))
    errors = [e.message for e in _validator(relaxed).iter_errors(out)]
    assert errors == [], (
        f"normalized instance {instance!r} -> {out!r} invalid for original: {errors}"
    )


@pytest.mark.parametrize("target", TARGETS)
@SETTINGS
@given(
    schema=mcp_schemas(),
    junk=st.recursive(
        st.none() | st.booleans() | st.integers() | st.text(max_size=3),
        lambda c: st.lists(c, max_size=3) | st.dictionaries(st.text(max_size=3), c, max_size=3),
        max_leaves=10,
    ),
)
def test_reverse_is_total(target: str, schema: dict[str, Any], junk: Any) -> None:
    r = normalize_schema(schema, target)  # type: ignore[arg-type]
    denormalize_args(r, junk)  # never raises in non-strict mode


def test_recursive_round_trip_examples() -> None:
    """Recursive schemas are covered by explicit examples (the generator cannot handle them)."""
    s = {
        "type": "object",
        "properties": {"tree": {"$ref": "#/$defs/Node"}},
        "$defs": {
            "Node": {
                "type": "object",
                "properties": {"value": {"type": "string"}, "next": {"$ref": "#/$defs/Node"}},
                "required": ["value"],
            }
        },
    }
    for target in TARGETS:
        r = normalize_schema(s, target)  # type: ignore[arg-type]
        assert r.schema is not None
        args: dict[str, Any] = {"tree": {"value": "a", "next": {"value": "b"}}}
        if target == "openai-strict":
            args = {"tree": {"value": "a", "next": {"value": "b", "next": None}}}
        out = denormalize_args(r, args).args
        errors = [e.message for e in _validator(relax(s, r)).iter_errors(out)]
        assert errors == [], (target, out, errors)

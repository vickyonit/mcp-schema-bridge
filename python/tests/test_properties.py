"""Property tests over generated MCP-shaped schemas (plan §8.3)."""

from __future__ import annotations

import os
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings

from mcp_schema_bridge import normalize_schema
from mcp_schema_bridge.core.jcs import canonicalize
from mcp_schema_bridge.core.rules import TARGETS
from tests.strategies import mcp_schemas
from tests.support.invariants import allow_list, hints_complete, idempotent, no_silent_loss

settings.register_profile("ci", max_examples=300, derandomize=True, deadline=None)
settings.register_profile("dev", max_examples=60, deadline=None)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))

COMMON = settings(suppress_health_check=[HealthCheck.too_slow])


@pytest.mark.parametrize("target", TARGETS)
@COMMON
@given(schema=mcp_schemas())
def test_no_silent_loss(target: str, schema: dict[str, Any]) -> None:
    r = normalize_schema(schema, target)  # type: ignore[arg-type]
    assert no_silent_loss(schema, r) == []


@pytest.mark.parametrize("target", TARGETS)
@COMMON
@given(schema=mcp_schemas())
def test_idempotent(target: str, schema: dict[str, Any]) -> None:
    r = normalize_schema(schema, target)  # type: ignore[arg-type]
    assert idempotent(r) == []


@pytest.mark.parametrize("target", TARGETS)
@COMMON
@given(schema=mcp_schemas())
def test_deterministic_and_pure(target: str, schema: dict[str, Any]) -> None:
    before = canonicalize(schema)
    a = normalize_schema(schema, target)  # type: ignore[arg-type]
    b = normalize_schema(schema, target)  # type: ignore[arg-type]
    assert canonicalize(schema) == before
    assert a.schema == b.schema
    assert [e.to_dict() for e in a.report.sorted()] == [e.to_dict() for e in b.report.sorted()]


@pytest.mark.parametrize("target", TARGETS)
@COMMON
@given(schema=mcp_schemas())
def test_allow_list(target: str, schema: dict[str, Any]) -> None:
    r = normalize_schema(schema, target)  # type: ignore[arg-type]
    assert allow_list(r) == []


@pytest.mark.parametrize("target", TARGETS)
@COMMON
@given(schema=mcp_schemas())
def test_hints_complete(target: str, schema: dict[str, Any]) -> None:
    r = normalize_schema(schema, target)  # type: ignore[arg-type]
    assert hints_complete(r) == []


def test_regression_identity_reuse_does_not_change_results() -> None:
    """Visited-node tracking once used raw id()s, which are reused after GC (non-determinism)."""
    schema = {
        "type": "object",
        "properties": {
            "id": {"$ref": "#/$defs/Shared"},
            "name": {
                "allOf": [{"type": "string"}, {"oneOf": [{"type": "boolean"}, {"type": "string"}]}]
            },
        },
        "$defs": {
            "Shared": {
                "allOf": [
                    {"anyOf": [{"type": "boolean"}, {"type": ["string", "null"]}]},
                    {
                        "oneOf": [
                            {"type": "object", "properties": {"name": {"type": "string"}}},
                            {"oneOf": [{"type": "string"}, {"type": "string"}]},
                        ]
                    },
                ]
            }
        },
    }
    results = {canonicalize(normalize_schema(schema, "anthropic-strict").schema) for _ in range(50)}
    assert len(results) == 1

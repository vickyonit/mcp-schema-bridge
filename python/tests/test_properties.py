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
from tests.support.invariants import allow_list, idempotent, no_silent_loss

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


PENDING_ALLOW_LIST = {"gemini-json", "openai-strict", "anthropic-strict"}  # until stage S9 lands


@pytest.mark.parametrize(
    "target",
    [
        pytest.param(t, marks=pytest.mark.xfail(strict=True, reason="pending S9 filter"))
        if t in PENDING_ALLOW_LIST
        else t
        for t in TARGETS
    ],
)
@COMMON
@given(schema=mcp_schemas())
def test_allow_list(target: str, schema: dict[str, Any]) -> None:
    r = normalize_schema(schema, target)  # type: ignore[arg-type]
    assert allow_list(r) == []

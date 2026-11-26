"""ReverseMap / denormalize_args behaviour independent of specific transformations."""

import dataclasses

import pytest

from mcp_schema_bridge import ReverseMismatchError, denormalize_args, normalize_schema
from mcp_schema_bridge.core.result import ReverseMap


def _wrapped():
    return normalize_schema({"type": "string"}, "openai-strict")


def test_reverse_map_round_trips_through_dict() -> None:
    r = _wrapped()
    assert ReverseMap.from_dict(r.reverse.to_dict()) == r.reverse
    assert r.reverse.to_dict()["ops"] == [{"op": "unwrap_root", "at": ""}]


def test_fingerprint_mismatch_raises() -> None:
    r = _wrapped()
    bad = dataclasses.replace(r, reverse=dataclasses.replace(r.reverse, fingerprint="0" * 64))
    with pytest.raises(ReverseMismatchError, match="fingerprint"):
        denormalize_args(bad, {"value": "x"})


def test_rules_version_mismatch_raises() -> None:
    r = _wrapped()
    bad = dataclasses.replace(r, reverse=dataclasses.replace(r.reverse, rules_version="1999.01.01"))
    with pytest.raises(ReverseMismatchError, match="rules_version"):
        denormalize_args(bad, {"value": "x"})


def test_unrecognized_shape_passes_through_with_warning() -> None:
    r = _wrapped()
    res = denormalize_args(r, {"not_value": 1})
    assert res.args == {"not_value": 1}
    assert [w.rule for w in res.warnings] == ["core/reverse-unrecognized-shape"]


def test_unrecognized_shape_raises_in_strict_mode() -> None:
    from mcp_schema_bridge import InvalidInputError

    with pytest.raises(InvalidInputError, match="value"):
        denormalize_args(_wrapped(), {"not_value": 1}, strict=True)


def test_no_ops_returns_args_unchanged_and_copied() -> None:
    r = normalize_schema({"type": "object", "properties": {"a": {"type": "string"}}}, "openai")
    args = {"a": "x"}
    res = denormalize_args(r, args)
    assert res.args == args
    assert res.args is not args
    assert res.warnings == []

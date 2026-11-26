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


def _repair_tool():
    s = {
        "type": "object",
        "properties": {
            "n": {"type": "integer"},
            "mode": {"type": "string", "enum": ["Fast", "Slow", "slow"]},
            "kind": {"type": "string", "enum": ["A", "B"]},
        },
        "required": ["n"],
    }
    return normalize_schema(s, "gemini-json")


def test_repairs_are_opt_in() -> None:
    res = denormalize_args(_repair_tool(), {"n": 5.0, "kind": "a"})
    assert res.args == {"n": 5.0, "kind": "a"}
    assert res.warnings == []


def test_int_from_integral_float_repair() -> None:
    res = denormalize_args(
        _repair_tool(), {"n": 5.0}, repairs=frozenset({"int_from_integral_float"})
    )
    assert res.args == {"n": 5}
    assert type(res.args["n"]) is int
    assert [w.rule for w in res.warnings] == ["core/repair-int-from-float"]
    res = denormalize_args(
        _repair_tool(), {"n": 5.5}, repairs=frozenset({"int_from_integral_float"})
    )
    assert res.args == {"n": 5.5}


def test_enum_case_repair_only_when_unambiguous() -> None:
    repairs = frozenset({"enum_case_insensitive"})
    res = denormalize_args(_repair_tool(), {"n": 1, "kind": "a"}, repairs=repairs)
    assert res.args == {"n": 1, "kind": "A"}
    assert [w.rule for w in res.warnings] == ["core/repair-enum-case"]
    # "SLOW" matches both "Slow" and "slow": ambiguous, left alone
    res = denormalize_args(_repair_tool(), {"n": 1, "mode": "SLOW"}, repairs=repairs)
    assert res.args == {"n": 1, "mode": "SLOW"}
    # exact match is never touched
    res = denormalize_args(_repair_tool(), {"n": 1, "mode": "slow"}, repairs=repairs)
    assert res.args["mode"] == "slow"
    assert res.warnings == []

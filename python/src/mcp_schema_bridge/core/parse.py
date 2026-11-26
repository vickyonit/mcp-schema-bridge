"""Stage S0: strict parsing and input validation (I-JSON, size and depth guards)."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Literal

from mcp_schema_bridge.core.errors import InvalidInputError, LimitExceededError
from mcp_schema_bridge.core.jcs import MAX_SAFE_INTEGER
from mcp_schema_bridge.core.pointer import join

BigIntPolicy = Literal["reject", "round"]


@dataclass(frozen=True)
class Limits:
    max_nodes: int = 10_000
    max_depth: int = 64


class _Pairs(list[tuple[str, Any]]):
    """Marker type for objects decoded as key/value pair lists (to detect duplicates)."""


def loads(text: str) -> Any:
    """Parse JSON text strictly: no duplicate keys, no NaN/Infinity."""

    def bad_constant(name: str) -> Any:
        raise InvalidInputError(f"JSON numbers must be finite; found {name}")

    try:
        tree = json.loads(text, object_pairs_hook=_Pairs, parse_constant=bad_constant)
    except json.JSONDecodeError as e:
        raise InvalidInputError(f"invalid JSON: {e.msg} at line {e.lineno} column {e.colno}") from e
    return _from_pairs(tree, "")


def _from_pairs(node: Any, pointer: str) -> Any:
    if isinstance(node, _Pairs):
        out: dict[str, Any] = {}
        for k, v in node:
            if k in out:
                raise InvalidInputError(f"duplicate key {k!r}", pointer)
            out[k] = _from_pairs(v, join(pointer, k))
        return out
    if isinstance(node, list):
        return [_from_pairs(v, join(pointer, i)) for i, v in enumerate(node)]  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    return node


def check_value(
    value: Any,
    *,
    big_int: BigIntPolicy = "reject",
    limits: Limits | None = None,
) -> tuple[Any, list[str]]:
    """Validate ``value`` as I-JSON and return ``(deep_copy, coerced_big_int_pointers)``."""
    lim = limits or Limits()
    coerced: list[str] = []
    count = [0]

    def visit(v: Any, pointer: str, depth: int) -> Any:
        count[0] += 1
        if count[0] > lim.max_nodes:
            raise LimitExceededError(f"input exceeds max_nodes={lim.max_nodes}", pointer)
        if depth > lim.max_depth:
            raise LimitExceededError(f"input exceeds max_depth={lim.max_depth}", pointer)
        if v is None or isinstance(v, bool):
            return v
        if isinstance(v, int):
            if abs(v) > MAX_SAFE_INTEGER:
                if big_int == "round":
                    coerced.append(pointer)
                    return float(v)
                raise InvalidInputError(
                    f"integer {v} is outside the I-JSON safe range (|n| <= 2**53 - 1)", pointer
                )
            return v
        if isinstance(v, float):
            if not math.isfinite(v):
                raise InvalidInputError("JSON numbers must be finite", pointer)
            return v
        if isinstance(v, str):
            _check_string(v, pointer)
            return v
        if isinstance(v, dict):
            out: dict[str, Any] = {}
            for k, child in v.items():  # pyright: ignore[reportUnknownVariableType]
                if not isinstance(k, str):
                    raise InvalidInputError("object keys must be strings", pointer)
                _check_string(k, pointer)
                out[k] = visit(child, join(pointer, k), depth + 1)
            return out
        if isinstance(v, list):
            return [visit(c, join(pointer, i), depth + 1) for i, c in enumerate(v)]  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
        raise InvalidInputError(f"not a JSON value: {type(v).__name__}", pointer)

    return visit(value, "", 0), coerced


def _check_string(s: str, pointer: str) -> None:
    for ch in s:
        if 0xD800 <= ord(ch) <= 0xDFFF:
            raise InvalidInputError("lone surrogate in string is not valid I-JSON", pointer)

"""Public option types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Budget:
    """anthropic-strict per-request usage that is not part of the normalized tools."""

    strict_tools: int = 0
    optional_params: int = 0
    union_params: int = 0


@dataclass(frozen=True)
class NormalizeOptions:
    hints: bool = True
    """Append dropped validation constraints to descriptions (spec/hint-format.md)."""
    on_unsupported: Literal["report", "raise"] = "report"
    """``"raise"``: the first fatal entry raises UnsupportedSchemaError."""
    max_ref_depth: int = 3
    """Recursion unrolling depth on targets that forbid recursion."""
    max_nodes: int = 10_000
    """Input and output schema-node cap; exceeding raises LimitExceededError."""
    max_depth: int = 64
    """Input nesting cap; exceeding raises LimitExceededError."""
    max_description_chars: int | None = None
    """Truncate original description text (never the hint); the ellipsis counts within the limit."""
    strict_fallback: bool = False
    """Demote unfixable or over-budget tools to the non-strict sibling target."""
    reserved_budget: Budget | None = None
    big_int: Literal["reject", "round"] = "reject"
    """Integers with |n| > 2**53-1: reject, or round to the nearest double (reported as lossy)."""

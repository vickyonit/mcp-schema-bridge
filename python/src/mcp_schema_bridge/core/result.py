"""Result types: NormalizeResult and ReverseMap."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mcp_schema_bridge.core.report import Report


@dataclass(frozen=True)
class ReverseMap:
    fingerprint: str
    rules_version: str
    target: str
    ops: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "fingerprint": self.fingerprint,
            "rules_version": self.rules_version,
            "target": self.target,
            "ops": [dict(op) for op in self.ops],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ReverseMap:
        return cls(
            fingerprint=d["fingerprint"],
            rules_version=d["rules_version"],
            target=d["target"],
            ops=tuple(dict(op) for op in d.get("ops", [])),
        )


@dataclass(frozen=True)
class NormalizeResult:
    target: str
    strict: bool
    schema: dict[str, Any] | None
    report: Report
    reverse: ReverseMap
    fingerprint: str
    library_version: str
    rules_version: str
    provenance: dict[str, tuple[str, ...]] = field(default_factory=lambda: {})
    """Output schema pointer -> source pointer(s). Diagnostic; not part of the serialized form."""

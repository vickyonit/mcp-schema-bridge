"""Lossiness report model (published as spec/report.schema.json)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, get_args

from mcp_schema_bridge.core.jcs import utf16_sort_key

Severity = Literal["info", "reversible", "lossy", "fatal"]
Action = Literal[
    "dropped",
    "rewritten",
    "inlined",
    "merged",
    "coerced",
    "wrapped",
    "narrowed",
    "truncated",
    "fallback",
    "rejected",
]

SEVERITIES: tuple[Severity, ...] = get_args(Severity)
ACTIONS: tuple[Action, ...] = get_args(Action)
_RANK = {s: i for i, s in enumerate(SEVERITIES)}


def severity_at_least(severity: Severity, threshold: Severity) -> bool:
    return _RANK[severity] >= _RANK[threshold]


@dataclass(frozen=True)
class ReportEntry:
    rule: str
    tid: str
    source_path: str
    keyword: str | None
    action: Action
    severity: Severity
    tool: str | None = None
    target_path: str | None = None
    instance_path: str | None = None
    original: Any = None
    hinted: bool = False
    message: str = ""

    def __post_init__(self) -> None:
        if self.severity not in _RANK:
            raise ValueError(f"invalid severity {self.severity!r}")
        if self.action not in ACTIONS:
            raise ValueError(f"invalid action {self.action!r}")

    def sort_key(self) -> tuple[bytes, ...]:
        return (
            utf16_sort_key(self.tool or ""),
            utf16_sort_key(self.source_path),
            utf16_sort_key(self.rule),
            utf16_sort_key(self.keyword or ""),
            utf16_sort_key(self.target_path or ""),
            utf16_sort_key(self.action),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "tid": self.tid,
            "tool": self.tool,
            "source_path": self.source_path,
            "target_path": self.target_path,
            "instance_path": self.instance_path,
            "keyword": self.keyword,
            "action": self.action,
            "severity": self.severity,
            "original": self.original,
            "hinted": self.hinted,
            "message": self.message,
        }


@dataclass
class Report:
    target: str
    entries: list[ReportEntry] = field(default_factory=lambda: [])

    def sorted(self) -> list[ReportEntry]:
        return sorted(self.entries, key=ReportEntry.sort_key)

    def max_severity(self) -> Severity | None:
        if not self.entries:
            return None
        return max((e.severity for e in self.entries), key=_RANK.__getitem__)

    def has_fatal(self) -> bool:
        return any(e.severity == "fatal" for e in self.entries)

    def to_dict(self, *, library_version: str, rules_version: str) -> dict[str, Any]:
        return {
            "library_version": library_version,
            "rules_version": rules_version,
            "target": self.target,
            "entries": [e.to_dict() for e in self.sorted()],
        }

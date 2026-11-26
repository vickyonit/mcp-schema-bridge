"""Per-normalization mutable state shared by pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mcp_schema_bridge.core.errors import UnsupportedSchemaError
from mcp_schema_bridge.core.options import NormalizeOptions
from mcp_schema_bridge.core.report import Action, Severity
from mcp_schema_bridge.core.rules import Rules
from mcp_schema_bridge.core.tree import SNode


@dataclass
class PendingEntry:
    """A report entry whose output location is resolved at emission time."""

    rule: str
    tid: str
    source_path: str
    keyword: str | None
    action: Action
    severity: Severity
    node: SNode | None
    original: Any = None
    hinted: bool = False
    message: str = ""
    want_hint: bool = False  # restate `original` in the node's description (S10)


@dataclass
class Ctx:
    rules: Rules
    opts: NormalizeOptions
    tool: str | None = None
    entries: list[PendingEntry] = field(default_factory=lambda: [])
    defs: dict[str, SNode] = field(default_factory=lambda: {})
    fatal: bool = False

    def add(
        self,
        rule: str,
        tid: str,
        *,
        node: SNode | None,
        keyword: str | None,
        action: Action,
        severity: Severity,
        source_path: str | None = None,
        original: Any = None,
        message: str = "",
        hint: bool = False,
    ) -> PendingEntry:
        src = source_path if source_path is not None else (node.src[0] if node and node.src else "")
        e = PendingEntry(
            rule=rule,
            tid=tid,
            source_path=src,
            keyword=keyword,
            action=action,
            severity=severity,
            node=node,
            original=original,
            message=message,
            want_hint=hint,
            hinted=False,
        )
        self.entries.append(e)
        if severity == "fatal":
            self.fatal = True
            if self.opts.on_unsupported == "raise":
                raise UnsupportedSchemaError(message or rule, src)
        return e

    def rule_id(self, slug: str) -> str:
        return f"{self.rules.target}/{slug}"

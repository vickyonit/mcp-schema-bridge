"""Normalize MCP tool schemas for Gemini, OpenAI and Anthropic."""

from mcp_schema_bridge._version import __version__
from mcp_schema_bridge.core.errors import (
    InvalidInputError,
    LimitExceededError,
    ReverseMismatchError,
    SchemaBridgeError,
    UnsupportedSchemaError,
)
from mcp_schema_bridge.core.options import Budget, NormalizeOptions
from mcp_schema_bridge.core.pipeline import normalize_schema
from mcp_schema_bridge.core.report import Report, ReportEntry
from mcp_schema_bridge.core.result import NormalizeResult, ReverseMap
from mcp_schema_bridge.core.reverse import DenormalizeResult, Repair, denormalize_args
from mcp_schema_bridge.core.rules import RULES_VERSION, TARGETS, Target

__all__ = [
    "RULES_VERSION",
    "TARGETS",
    "Budget",
    "DenormalizeResult",
    "InvalidInputError",
    "LimitExceededError",
    "NormalizeOptions",
    "NormalizeResult",
    "Repair",
    "Report",
    "ReportEntry",
    "ReverseMap",
    "ReverseMismatchError",
    "SchemaBridgeError",
    "Target",
    "UnsupportedSchemaError",
    "__version__",
    "denormalize_args",
    "normalize_schema",
]

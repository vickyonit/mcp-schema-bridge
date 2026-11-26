"""Exception hierarchy. Every error carries the JSON Pointer of the offending location."""

from __future__ import annotations


class SchemaBridgeError(Exception):
    """Base class for all mcp-schema-bridge errors."""

    def __init__(self, message: str, pointer: str = "") -> None:
        super().__init__(f"{message} (at {pointer or '/'})")
        self.message = message
        self.pointer = pointer


class InvalidInputError(SchemaBridgeError):
    """Input is not valid JSON / I-JSON, or uses an unsupported JSON Schema dialect."""


class UnsupportedSchemaError(SchemaBridgeError):
    """Raised under ``on_unsupported="raise"`` when a schema cannot be made acceptable."""


class LimitExceededError(SchemaBridgeError):
    """Input or output exceeded ``max_nodes`` / ``max_depth``."""


class ReverseMismatchError(SchemaBridgeError):
    """A reverse map does not belong to the tool / rules it is being applied with."""

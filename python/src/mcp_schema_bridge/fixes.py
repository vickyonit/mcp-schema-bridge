"""Actionable "how to fix it in your server" suggestions per rule slug (shown by the CLI)."""

from __future__ import annotations

VALIDATE = "the model may not respect this constraint: validate it in your tool handler and return a helpful error"

FIXES: dict[str, str] = {
    "open-object-unsupported": "declare the keys as properties, or model a map as a list of {key, value} objects "
    "(Pydantic: list[KeyValue] instead of dict[str, str]); clients can use --strict-fallback",
    "any-value-unsupported": "give the field a concrete type (a string, number, object with properties, ...) instead of Any / {}",
    "optional-nullable-ambiguous": "if null and 'not provided' mean the same in your server, declare default: null "
    "(Pydantic: `= None`) and the change becomes reversible",
    "keyword-not-enforced": VALIDATE,
    "keyword-rejected": VALIDATE,
    "keyword-unsupported": VALIDATE,
    "format-unsupported": VALIDATE,
    "min-items-clamped": VALIDATE,
    "pattern-unsupported": "use a simpler regex (no lookaround, backreferences or \\b) or validate in your tool handler",
    "tool-name-invalid": "rename the tool using only letters, digits, '_' and '-' (64 characters or fewer works everywhere)",
    "property-key-invalid": "rename the property using only letters, digits, '_', '.' and '-' (64 characters or fewer)",
    "unsatisfiable-recursion": "make the recursive field optional or nullable, otherwise no finite value exists",
    "recursion-truncated": "keep recursive structures shallow, or accept the depth limit (max_ref_depth)",
    "unresolvable-ref": "inline the referenced schema; remote $refs are never fetched",
    "dynamic-ref-unsupported": "replace $dynamicRef/$recursiveRef with a plain $ref to a $defs entry",
    "oneof-to-anyof": "make the branches distinguishable with a required const discriminator (e.g. kind: 'a' | 'b')",
    "array-items-missing": "declare the item type (Pydantic: list[str] instead of list)",
    "request-budget-exceeded": "use fewer optional/union parameters per tool or fewer strict tools; clients can use --strict-fallback",
    "allof-unsatisfiable": "the allOf branches contradict each other; fix the model so one value can satisfy all of them",
    "unsatisfiable-union": "every union branch contradicts its siblings; fix the model",
    "limit-max-properties": "split the tool into smaller tools",
    "limit-max-nesting-depth": "flatten deeply nested objects",
    "limit-max-total-string-chars": "shorten property names and enum values, or split the tool",
    "limit-max-enum-values": "replace very large enums with a free-text field validated by the server",
    "limit-max-large-enum-chars": "replace very large enums with a free-text field validated by the server",
}


def fix_for(rule: str) -> str | None:
    return FIXES.get(rule.rsplit("/", 1)[-1])

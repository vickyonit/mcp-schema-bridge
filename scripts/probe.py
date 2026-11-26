#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Phase 0 evidence: probe what a provider accepts (request-level) and enforces (output-level).

Acceptance probes send a schema and record accepted/rejected (+ scrubbed error).
Enforcement probes ask the model, via the prompt, for a value that VIOLATES a constraint:
  - baseline run (constraint absent) must violate in >=1 sample, else "inconclusive";
  - constrained run complying in all samples => "enforced"; any violation => "stripped".

Usage: uv run --script scripts/probe.py --target gemini-json --model gemini-3.5-flash-lite [--samples 5]
Writes evidence/probes/<target>/<model>.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from providers import available, call_tool  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    "gemini-json": ("gemini", False),
    "openai": ("openai", False),
    "openai-strict": ("openai", True),
    "anthropic": ("anthropic", False),
    "anthropic-strict": ("anthropic", True),
}


def classify(baseline_ok: list[bool | None], constrained_ok: list[bool | None]) -> str:
    if any(x is None for x in constrained_ok):
        return "error"
    if all(x is True for x in baseline_ok):
        return "inconclusive"
    return "enforced" if all(constrained_ok) else "stripped"


def _obj(a: dict[str, Any], strict: bool) -> dict[str, Any]:
    s: dict[str, Any] = {"type": "object", "properties": {"a": a}, "required": ["a"]}
    if strict:
        s["additionalProperties"] = False
    return s


def _S(props: dict[str, Any], req: list[str] | None = None, **kw: Any) -> dict[str, Any]:
    s: dict[str, Any] = {"type": "object", "properties": props, **kw}
    if req:
        s["required"] = req
    return s


ACCEPTANCE: dict[str, dict[str, Any]] = {
    "plain": _S({"a": {"type": "string"}}, ["a"]),
    "type_null_array": _S({"a": {"type": ["string", "null"]}}, ["a"]),
    "multi_type_array": _S({"a": {"type": ["string", "integer"]}}, ["a"]),
    "multi_type_with_enum": _S({"a": {"type": ["string", "integer"], "enum": ["k", 1]}}, ["a"]),
    "def_name_percent_encoded": {"type": "object", "$defs": {"a/b%c": {"type": "string"}}, "properties": {"a": {"$ref": "#/$defs/a~1b%25c"}}, "required": ["a"]},
    "anyOf_with_annotations": _S({"a": {"anyOf": [{"type": "string"}, {"type": "integer"}], "description": "x", "title": "A"}}, ["a"]),
    "oneOf": _S({"a": {"oneOf": [{"type": "string"}, {"type": "integer"}]}}, ["a"]),
    "allOf": _S({"a": {"allOf": [{"type": "string"}, {"minLength": 1}]}}, ["a"]),
    "not": _S({"a": {"type": "string", "not": {"const": "x"}}}, ["a"]),
    "if_then": _S({"a": {"type": "string"}}, ["a"], **{"if": {"properties": {"a": {"const": "x"}}}, "then": {"required": ["a"]}}),
    "const_untyped": _S({"a": {"const": "fixed"}}, ["a"]),
    "const_typed": _S({"a": {"type": "string", "const": "fixed"}}, ["a"]),
    "enum_integer": _S({"a": {"type": "integer", "enum": [1, 2, 3]}}, ["a"]),
    "enum_untyped": _S({"a": {"enum": ["x", "y"]}}, ["a"]),
    "enum_object_values": _S({"a": {"enum": [{"k": 1}, {"k": 2}]}}, ["a"]),
    "pattern": _S({"a": {"type": "string", "pattern": "^Z[0-9]{3}$"}}, ["a"]),
    "pattern_lookahead": _S({"a": {"type": "string", "pattern": "^(?=.*\\d).+$"}}, ["a"]),
    "format_email": _S({"a": {"type": "string", "format": "email"}}, ["a"]),
    "format_uri": _S({"a": {"type": "string", "format": "uri"}}, ["a"]),
    "format_custom": _S({"a": {"type": "string", "format": "my-format"}}, ["a"]),
    "exclusiveMinimum": _S({"a": {"type": "number", "exclusiveMinimum": 0}}, ["a"]),
    "multipleOf": _S({"a": {"type": "integer", "multipleOf": 5}}, ["a"]),
    "minimum_maximum": _S({"a": {"type": "integer", "minimum": 1, "maximum": 9}}, ["a"]),
    "minLength": _S({"a": {"type": "string", "minLength": 3}}, ["a"]),
    "maxItems": _S({"a": {"type": "array", "items": {"type": "string"}, "maxItems": 3}}, ["a"]),
    "minItems_2": _S({"a": {"type": "array", "items": {"type": "string"}, "minItems": 2}}, ["a"]),
    "uniqueItems": _S({"a": {"type": "array", "items": {"type": "string"}, "uniqueItems": True}}, ["a"]),
    "array_without_items": _S({"a": {"type": "array"}}, ["a"]),
    "prefixItems": _S({"a": {"type": "array", "prefixItems": [{"type": "string"}, {"type": "integer"}]}}, ["a"]),
    "tuple_items_draft7": _S({"a": {"type": "array", "items": [{"type": "string"}]}}, ["a"]),
    "additionalProperties_false": _S({"a": {"type": "string"}}, ["a"], additionalProperties=False),
    "additionalProperties_schema": _S({"a": {"type": "object", "additionalProperties": {"type": "string"}}}, ["a"]),
    "patternProperties": _S({"a": {"type": "object", "patternProperties": {"^x": {"type": "string"}}}}, ["a"]),
    "open_object": _S({"a": {"type": "object"}}, ["a"]),
    "empty_property_schema": _S({"a": {}}, ["a"]),
    "boolean_property_schema": _S({"a": True}, ["a"]),
    "defs_ref": {"type": "object", "$defs": {"N": {"type": "string"}}, "properties": {"a": {"$ref": "#/$defs/N"}}, "required": ["a"]},
    "definitions_ref": {"type": "object", "definitions": {"N": {"type": "string"}}, "properties": {"a": {"$ref": "#/definitions/N"}}, "required": ["a"]},
    "ref_with_description": {"type": "object", "$defs": {"N": {"type": "string"}}, "properties": {"a": {"$ref": "#/$defs/N", "description": "d"}}, "required": ["a"]},
    "recursion_optional": {"type": "object", "$defs": {"Node": {"type": "object", "properties": {"v": {"type": "string"}, "next": {"$ref": "#/$defs/Node"}}}}, "properties": {"n": {"$ref": "#/$defs/Node"}}, "required": ["n"]},
    "recursion_required": {"type": "object", "$defs": {"Node": {"type": "object", "properties": {"v": {"type": "string"}, "next": {"$ref": "#/$defs/Node"}}, "required": ["v", "next"]}}, "properties": {"n": {"$ref": "#/$defs/Node"}}, "required": ["n"]},
    "root_self_ref": {"type": "object", "properties": {"child": {"$ref": "#"}, "v": {"type": "string"}}},
    "dollar_schema": {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object", "properties": {"a": {"type": "string"}}},
    "x_extension": _S({"a": {"type": "string", "x-mcp-header": "X-A"}}, ["a"]),
    "dollar_id": {"$id": "urn:example:x", "type": "object", "properties": {"a": {"type": "string"}}},
    "comment_examples": _S({"a": {"type": "string", "$comment": "c", "examples": ["e"]}}, ["a"]),
    "readOnly_deprecated": _S({"a": {"type": "string", "readOnly": True, "deprecated": True}}, ["a"]),
    "default": _S({"a": {"type": "string", "default": "x"}}),
    "root_anyOf": {"anyOf": [_S({"a": {"type": "string"}}), _S({"b": {"type": "string"}})]},
    "root_object_with_anyOf": {"type": "object", "properties": {"a": {"type": "string"}, "b": {"type": "string"}}, "anyOf": [{"required": ["a"]}, {"required": ["b"]}]},
    "root_not_object": {"type": "string"},
    "root_empty": {},
    "dependentRequired": _S({"a": {"type": "string"}, "b": {"type": "string"}}, None, dependentRequired={"a": ["b"]}),
    "propertyNames": _S({"a": {"type": "object", "propertyNames": {"pattern": "^x"}}}, ["a"]),
    "contentEncoding": _S({"a": {"type": "string", "contentEncoding": "base64"}}, ["a"]),
    "openapi_nullable": _S({"a": {"type": "string", "nullable": True}}, ["a"]),
    "key_with_space": _S({"a b": {"type": "string"}}, ["a b"]),
    "key_with_dollar": _S({"$a": {"type": "string"}}, ["$a"]),
    "key_non_ascii": _S({"ü": {"type": "string"}}, ["ü"]),
    "key_with_dot": _S({"a.b": {"type": "string"}}, ["a.b"]),
}

Check = Callable[[Any], bool]
ENFORCEMENT: dict[str, tuple[dict[str, Any], dict[str, Any], Any, Check]] = {
    "const": ({"type": "string"}, {"const": "fixed"}, "hello", lambda x: x == "fixed"),
    "enum": ({"type": "string"}, {"enum": ["xx", "yy"]}, "hello", lambda x: x in ("xx", "yy")),
    "pattern": ({"type": "string"}, {"pattern": "^Z[0-9]{3}$"}, "hello", lambda x: isinstance(x, str) and re.fullmatch("Z[0-9]{3}", x) is not None),
    "minLength": ({"type": "string"}, {"minLength": 6}, "hi", lambda x: len(x) >= 6),
    "maxLength": ({"type": "string"}, {"maxLength": 3}, "hello world", lambda x: len(x) <= 3),
    "minimum": ({"type": "integer"}, {"minimum": 10}, 3, lambda x: x >= 10),
    "maximum": ({"type": "integer"}, {"maximum": 10}, 50, lambda x: x <= 10),
    "exclusiveMinimum": ({"type": "integer"}, {"exclusiveMinimum": 0}, 0, lambda x: x > 0),
    "exclusiveMaximum": ({"type": "integer"}, {"exclusiveMaximum": 10}, 10, lambda x: x < 10),
    "multipleOf": ({"type": "integer"}, {"multipleOf": 5}, 7, lambda x: x % 5 == 0),
    "format_date": ({"type": "string"}, {"format": "date"}, "next tuesday", lambda x: re.fullmatch(r"\d{4}-\d{2}-\d{2}", x) is not None),
    "format_email": ({"type": "string"}, {"format": "email"}, "not an email", lambda x: re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", x) is not None),
    "minItems": ({"type": "array", "items": {"type": "string"}}, {"minItems": 3}, ["a"], lambda x: len(x) >= 3),
    "maxItems": ({"type": "array", "items": {"type": "string"}}, {"maxItems": 1}, ["a", "b", "c"], lambda x: len(x) <= 1),
    "uniqueItems": ({"type": "array", "items": {"type": "string"}}, {"uniqueItems": True}, ["a", "a"], lambda x: len(set(x)) == len(x)),
    "not": ({"type": "string"}, {"not": {"const": "blocked"}}, "blocked", lambda x: x != "blocked"),
}


def _prompt(value: Any) -> str:
    return f"Call the tool t with argument a set to exactly {json.dumps(value)}. Do not change the value."


def run(target: str, model: str, samples: int) -> dict[str, Any]:
    provider, strict = TARGETS[target]
    acceptance: dict[str, Any] = {}
    for name, schema in ACCEPTANCE.items():
        r = call_tool(provider, model=model, schema=schema, prompt="Call the tool with any valid arguments.", strict=strict)
        acceptance[name] = {"status": r.status, "error": r.error}
        print(f"accept {name:28s} {r.status} {r.error or ''}"[:200], flush=True)
    enforcement: dict[str, Any] = {}
    for name, (base, extra, value, ok) in ENFORCEMENT.items():

        def outcomes(schema: dict[str, Any], ok: Check = ok, value: Any = value) -> list[bool | None]:
            res: list[bool | None] = []
            for _ in range(samples):
                r = call_tool(provider, model=model, schema=schema, prompt=_prompt(value), strict=strict, temperature=1.0)
                if r.status != "accepted" or not isinstance(r.args, dict) or "a" not in r.args:
                    res.append(None)
                    continue
                try:
                    res.append(bool(ok(r.args["a"])))
                except Exception:
                    res.append(False)
            return res

        b = outcomes(_obj(base, strict))
        c = outcomes(_obj({**base, **extra}, strict))
        verdict = classify([x if x is not None else True for x in b], c)
        enforcement[name] = {"verdict": verdict, "baseline": b, "constrained": c}
        print(f"enforce {name:20s} {verdict}", flush=True)
    return {
        "target": target,
        "model": model,
        "samples": samples,
        "recorded_at": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "acceptance": acceptance,
        "enforcement": enforcement,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True, choices=sorted(TARGETS))
    ap.add_argument("--model", required=True)
    ap.add_argument("--samples", type=int, default=5)
    args = ap.parse_args()
    provider, _ = TARGETS[args.target]
    if not available(provider):
        print(f"skipping: no API key for {provider}", file=sys.stderr)
        return 0
    result = run(args.target, args.model, args.samples)
    out = ROOT / "evidence" / "probes" / args.target / f"{args.model}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""denormalize_args: map model-produced arguments back to the original MCP schema shape."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, cast

from mcp_schema_bridge.core.errors import InvalidInputError, ReverseMismatchError
from mcp_schema_bridge.core.pointer import decode_fragment, join
from mcp_schema_bridge.core.report import ReportEntry
from mcp_schema_bridge.core.result import ReverseMap
from mcp_schema_bridge.core.rules import RULES_VERSION

Repair = Literal["int_from_integral_float", "enum_case_insensitive"]


class _HasReverse(Protocol):
    @property
    def schema(self) -> dict[str, Any] | None: ...
    @property
    def reverse(self) -> ReverseMap: ...
    @property
    def fingerprint(self) -> str: ...


@dataclass(frozen=True)
class DenormalizeResult:
    args: Any
    warnings: list[ReportEntry] = field(default_factory=lambda: [])


class _Walker:
    def __init__(
        self,
        schema: dict[str, Any],
        ops: dict[str, list[dict[str, Any]]],
        strict: bool,
        repairs: frozenset[str] = frozenset(),
    ):
        self.root = schema
        self.ops = ops
        self.strict = strict
        self.repairs = repairs
        self.warnings: list[ReportEntry] = []

    def note(self, rule: str, pointer: str, message: str, original: Any) -> None:
        self.warnings.append(
            ReportEntry(
                rule=rule,
                tid="reverse",
                source_path=pointer,
                keyword=None,
                action="coerced",
                severity="info",
                original=original,
                message=message,
            )
        )

    def repair(self, ptr: str, s: dict[str, Any], value: Any) -> Any:
        if (
            "int_from_integral_float" in self.repairs
            and isinstance(value, float)
            and value.is_integer()
        ):
            t = s.get("type")
            types = [t] if isinstance(t, str) else cast(list[str], t or [])
            if "integer" in types and "number" not in types:
                self.note(
                    "core/repair-int-from-float", ptr, "integral float converted to integer", value
                )
                return int(value)
        if "enum_case_insensitive" in self.repairs and isinstance(value, str):
            enum = s.get("enum")
            if isinstance(enum, list) and value not in cast(list[Any], enum):
                matches = [
                    v
                    for v in cast(list[Any], enum)
                    if isinstance(v, str) and v.casefold() == value.casefold()
                ]
                if len(matches) == 1:
                    self.note(
                        "core/repair-enum-case",
                        ptr,
                        f"enum value matched case-insensitively to {matches[0]!r}",
                        value,
                    )
                    return matches[0]
        return value

    def warn(self, rule: str, pointer: str, message: str) -> None:
        if self.strict:
            raise InvalidInputError(message, pointer)
        self.warnings.append(
            ReportEntry(
                rule=rule,
                tid="reverse",
                source_path=pointer,
                keyword=None,
                action="rewritten",
                severity="lossy",
                message=message,
            )
        )

    def resolve(self, ref: str) -> tuple[str, Any]:
        tokens = decode_fragment(ref)
        node: Any = self.root
        for t in tokens:
            node = node[t]
        return join("", *tokens), node

    def walk(self, ptr: str, schema: Any, value: Any, depth: int = 0) -> Any:
        if not isinstance(schema, dict) or depth > 10_000:
            return value
        s = cast(dict[str, Any], schema)
        if "$ref" in s:
            rptr, target = self.resolve(s["$ref"])
            value = self.walk(rptr, target, value, depth + 1)
        if isinstance(value, dict):
            obj = cast(dict[str, Any], value)
            props = cast(dict[str, Any], s.get("properties") or {})
            for k in list(obj):
                if k in props:
                    obj[k] = self.walk(join(ptr, "properties", k), props[k], obj[k], depth + 1)
                elif isinstance(s.get("additionalProperties"), dict):
                    obj[k] = self.walk(
                        join(ptr, "additionalProperties"),
                        s["additionalProperties"],
                        obj[k],
                        depth + 1,
                    )
        if isinstance(value, list):
            arr = cast(list[Any], value)
            prefix = cast(list[Any], s.get("prefixItems") or [])
            for i, item in enumerate(arr):
                if i < len(prefix):
                    arr[i] = self.walk(join(ptr, "prefixItems", i), prefix[i], item, depth + 1)
                elif isinstance(s.get("items"), dict):
                    arr[i] = self.walk(join(ptr, "items"), s["items"], item, depth + 1)
        for kw in ("anyOf", "oneOf"):
            branches = s.get(kw)
            if isinstance(branches, list):
                for i, b in enumerate(cast(list[Any], branches)):
                    if _structurally_matches(b, value, self):
                        value = self.walk(join(ptr, kw, i), b, value, depth + 1)
                        break
        for i, b in enumerate(cast(list[Any], s.get("allOf") or [])):
            value = self.walk(join(ptr, "allOf", i), b, value, depth + 1)
        if self.repairs:
            value = self.repair(ptr, s, value)
        for op in self.ops.get(ptr, []):
            value = self.apply(op, ptr, value)
        return cast(Any, value)

    def apply(self, op: dict[str, Any], ptr: str, value: Any) -> Any:
        kind = op["op"]
        if kind == "unwrap_root":
            if isinstance(value, dict) and "value" in value:
                return cast(dict[str, Any], value)["value"]
            self.warn(
                "core/reverse-unrecognized-shape", ptr, "expected wrapper object with key 'value'"
            )
            return cast(Any, value)
        if kind == "drop_injected_null":
            name = op["property"]
            if isinstance(value, dict) and name in value and value[name] is None:
                del cast(dict[str, Any], value)[name]
            return cast(Any, value)
        raise ValueError(f"unknown reverse op {kind!r}")


_JSON_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
}


def _type_ok(t: str, value: Any) -> bool:
    if t == "null":
        return value is None
    if t == "integer":
        return (
            isinstance(value, int | float)
            and not isinstance(value, bool)
            and float(value).is_integer()
        )
    if t == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    py = _JSON_TYPES.get(t)
    return (
        py is not None
        and isinstance(value, py)
        and not (py is not bool and isinstance(value, bool))
    )


def _structurally_matches(branch: Any, value: Any, w: _Walker) -> bool:
    if branch is True or branch == {}:
        return True
    if not isinstance(branch, dict):
        return False
    b = cast(dict[str, Any], branch)
    if "$ref" in b:
        _, target = w.resolve(b["$ref"])
        if not _structurally_matches(target, value, w):
            return False
    for kw in ("anyOf", "oneOf"):
        subs = b.get(kw)
        if isinstance(subs, list) and not any(
            _structurally_matches(x, value, w) for x in cast(list[Any], subs)
        ):
            return False
    for x in cast(list[Any], b.get("allOf") or []):
        if not _structurally_matches(x, value, w):
            return False
    t = b.get("type")
    if t is not None:
        types = [t] if isinstance(t, str) else cast(list[str], t)
        if not any(_type_ok(x, value) for x in types):
            return False
    if "const" in b and b["const"] != value:
        return False
    enum = b.get("enum")
    if (
        isinstance(enum, list)
        and len(cast(list[Any], enum)) == 1
        and cast(list[Any], enum)[0] != value
    ):
        return False
    req = b.get("required")
    if isinstance(req, list):
        if not isinstance(value, dict):
            return False
        if any(k not in value for k in cast(list[str], req)):
            return False
    return True


def denormalize_args(
    tool: _HasReverse,
    args: Any,
    *,
    strict: bool = False,
    repairs: frozenset[Repair] = frozenset(),
) -> DenormalizeResult:
    rev = tool.reverse
    if rev.fingerprint != tool.fingerprint:
        raise ReverseMismatchError("reverse map fingerprint does not match the tool fingerprint")
    if rev.rules_version != RULES_VERSION:
        raise ReverseMismatchError(
            f"reverse map rules_version {rev.rules_version} != loaded rules {RULES_VERSION}"
        )
    value = copy.deepcopy(args)
    if tool.schema is None:
        return DenormalizeResult(value, [])
    ops: dict[str, list[dict[str, Any]]] = {}
    for op in rev.ops:
        ops.setdefault(op["at"], []).append(op)
    w = _Walker(tool.schema, ops, strict, frozenset(repairs))
    value = w.walk("", tool.schema, value)
    return DenormalizeResult(value, w.warnings)

"""Provider rules, loaded from package data generated from the repository's rules/ directory."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Any, Literal, cast

Target = Literal["gemini-json", "openai", "openai-strict", "anthropic", "anthropic-strict"]
TARGETS: tuple[Target, ...] = (
    "gemini-json",
    "openai",
    "openai-strict",
    "anthropic",
    "anthropic-strict",
)
KeywordStatus = Literal["enforced", "accepted", "stripped", "rejected"]
KeywordKind = Literal["applicator", "validation", "annotation", "core", "unknown"]


def _read(name: str) -> Any:
    return json.loads(resources.files("mcp_schema_bridge._rules").joinpath(name).read_text("utf-8"))


RULES_VERSION: str = cast(str, _read("index.json")["rules_version"])


@dataclass(frozen=True)
class Features:
    ref: bool
    recursion: Literal["any", "optional_only", "none"]
    ref_siblings: bool
    type_arrays: bool
    multi_type_arrays: bool
    root_union: bool
    root_anyof_with_object: bool
    anyof_validation_siblings: bool
    merge_allof: bool
    oneof: bool
    close_objects: bool
    all_required: bool
    open_objects: bool
    tuple_items: bool
    boolean_subschemas: bool
    enum_values: Literal["any", "primitive"]
    min_items_values: tuple[int, ...] | None
    array_items_required: bool
    root_type_object_required: bool


@dataclass(frozen=True)
class Rules:
    target: Target
    provider: str
    strict: bool
    fallback_target: Target | None
    api_field: str
    features: Features
    keywords: dict[str, KeywordStatus]
    keeps_unknown_keywords: bool
    formats_allowed: frozenset[str] | None
    formats_enforced: frozenset[str]
    pattern_forbidden_features: frozenset[str]
    limits: dict[str, int]
    request_limits: dict[str, int]
    tool_name_pattern: str
    property_key_pattern: str | None
    raw: dict[str, Any]

    def keyword_status(self, keyword: str) -> KeywordStatus | None:
        return self.keywords.get(keyword)


@cache
def load_rules(target: str) -> Rules:
    if target not in TARGETS:
        raise ValueError(f"unknown target {target!r}; expected one of {', '.join(TARGETS)}")
    d = _read(f"{target}.json")
    f = dict(d["features"])
    mi = f["min_items_values"]
    f["min_items_values"] = tuple(mi) if mi is not None else None
    allowed = d["formats"]["allowed"]
    return Rules(
        target=cast(Target, d["target"]),
        provider=d["provider"],
        strict=d["strict"],
        fallback_target=d["fallback_target"],
        api_field=d["api_field"],
        features=Features(**f),
        keywords=dict(d["keywords"]),
        keeps_unknown_keywords=d["unknown_keywords"] == "keep",
        formats_allowed=frozenset(allowed) if allowed is not None else None,
        formats_enforced=frozenset(d["formats"]["enforced"]),
        pattern_forbidden_features=frozenset(d["pattern_forbidden_features"]),
        limits=dict(d["limits"]),
        request_limits=dict(d["request_limits"]),
        tool_name_pattern=d["tool_name_pattern"],
        property_key_pattern=d["property_key_pattern"],
        raw=d,
    )


@dataclass(frozen=True)
class KeywordClasses:
    applicator: frozenset[str]
    validation: frozenset[str]
    annotation: frozenset[str]
    core: frozenset[str]
    schema_maps: frozenset[str]
    schema_arrays: frozenset[str]
    schema_values: frozenset[str]

    def kind(self, keyword: str) -> KeywordKind:
        if keyword.startswith("x-"):
            return "annotation"
        for name in ("applicator", "validation", "annotation", "core"):
            if keyword in getattr(self, name):
                return cast(KeywordKind, name)
        return "unknown"


@cache
def keyword_classes() -> KeywordClasses:
    d = _read("keyword-classes.json")
    return KeywordClasses(**{k: frozenset(v) for k, v in d.items() if not k.startswith("$")})

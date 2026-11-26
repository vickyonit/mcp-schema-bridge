"""S1: dialects and $ref resolution (all refs re-emitted as #/$defs/... or #)."""

import pytest

from mcp_schema_bridge import InvalidInputError, UnsupportedSchemaError, normalize_schema
from mcp_schema_bridge.core.options import NormalizeOptions


def obj(props: dict, **kw: object) -> dict:
    return {"type": "object", "properties": props, **kw}


def test_defs_refs_are_kept_for_targets_with_ref_support() -> None:
    s = obj({"a": {"$ref": "#/$defs/Name"}}, **{"$defs": {"Name": {"type": "string"}}})
    r = normalize_schema(s, "gemini-json")
    assert r.schema == s


def test_draft07_definitions_are_re_emitted_as_defs() -> None:
    s = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {"a": {"$ref": "#/definitions/Name"}},
        "definitions": {"Name": {"type": "string"}},
    }
    r = normalize_schema(s, "openai")
    assert r.schema is not None
    assert r.schema["properties"]["a"] == {"$ref": "#/$defs/Name"}
    assert r.schema["$defs"] == {"Name": {"type": "string"}}
    assert "definitions" not in r.schema
    assert "$schema" not in r.schema


def test_ref_into_properties_is_hoisted_into_defs() -> None:
    s = obj({"a": {"type": "string", "minLength": 1}, "b": {"$ref": "#/properties/a"}})
    r = normalize_schema(s, "openai")
    assert r.schema is not None
    assert r.schema["properties"]["b"] == {"$ref": "#/$defs/a"}
    assert r.schema["properties"]["a"] == {"$ref": "#/$defs/a"}
    assert r.schema["$defs"]["a"] == {"type": "string", "minLength": 1}


def test_pointer_escapes_and_percent_encoding_in_refs() -> None:
    s = obj({"x": {"$ref": "#/$defs/a~1b%25c"}}, **{"$defs": {"a/b%c": {"type": "integer"}}})
    r = normalize_schema(s, "openai")
    assert r.schema is not None
    assert r.schema["$defs"] == {
        "a_b_c": {"type": "integer"}
    }  # renamed: no percent-encoding needed
    assert r.schema["properties"]["x"] == {"$ref": "#/$defs/a_b_c"}


def test_anchor_and_embedded_id_resolution() -> None:
    s = {
        "$id": "https://example.com/root.json",
        "type": "object",
        "properties": {
            "a": {"$ref": "#name"},
            "b": {"$ref": "item.json"},
        },
        "$defs": {
            "N": {"$anchor": "name", "type": "string"},
            "I": {"$id": "item.json", "type": "integer"},
        },
    }
    r = normalize_schema(s, "openai")
    assert r.schema is not None
    assert r.schema["properties"]["a"] == {"$ref": "#/$defs/N"}
    assert r.schema["properties"]["b"] == {"$ref": "#/$defs/I"}
    assert r.schema["$defs"]["N"] == {"type": "string"}
    assert r.schema["$defs"]["I"] == {"type": "integer"}


def test_self_reference_hash_is_preserved() -> None:
    s = obj({"child": {"$ref": "#"}, "v": {"type": "string"}})
    r = normalize_schema(s, "gemini-json")
    assert r.schema == s


@pytest.mark.parametrize(
    "ref", ["https://example.com/other.json", "other.json#/x", "#/$defs/Missing"]
)
def test_external_or_unresolvable_ref_is_fatal(ref: str) -> None:
    r = normalize_schema(obj({"a": {"$ref": ref}}), "openai")
    assert r.schema is None
    [e] = [e for e in r.report.entries if e.tid == "T2c"]
    assert (e.severity, e.action, e.source_path) == ("fatal", "rejected", "/properties/a")


def test_external_ref_raises_under_on_unsupported_raise() -> None:
    with pytest.raises(UnsupportedSchemaError):
        normalize_schema(
            obj({"a": {"$ref": "https://x/y.json"}}),
            "openai",
            NormalizeOptions(on_unsupported="raise"),
        )


@pytest.mark.parametrize("kw", ["$dynamicRef", "$recursiveRef"])
def test_dynamic_refs_are_fatal(kw: str) -> None:
    r = normalize_schema(obj({"a": {kw: "#node"}}), "openai")
    assert r.schema is None
    assert any(e.severity == "fatal" and e.keyword == kw for e in r.report.entries)


@pytest.mark.parametrize(
    "uri",
    [
        "https://json-schema.org/draft/2020-12/schema",
        "https://json-schema.org/draft/2020-12/schema#",
        "http://json-schema.org/draft-07/schema#",
        "http://json-schema.org/draft-07/schema",
        "https://json-schema.org/draft/2019-09/schema",
    ],
)
def test_supported_dialects(uri: str) -> None:
    r = normalize_schema({"$schema": uri, "type": "object", "properties": {}}, "openai")
    assert r.schema is not None


@pytest.mark.parametrize(
    "uri", ["http://json-schema.org/draft-04/schema#", "https://example.com/my-dialect"]
)
def test_unsupported_dialects_raise(uri: str) -> None:
    with pytest.raises(InvalidInputError, match="dialect"):
        normalize_schema({"$schema": uri, "type": "object"}, "openai")


def test_dollar_schema_is_stripped_with_info_entry() -> None:
    r = normalize_schema(
        {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}, "gemini-json"
    )
    assert r.schema == {"type": "object"}
    [e] = r.report.entries
    assert (e.keyword, e.action, e.severity) == ("$schema", "dropped", "info")


def test_unused_defs_are_pruned_with_info_entry() -> None:
    s = obj({"a": {"type": "string"}}, **{"$defs": {"Unused": {"type": "integer"}}})
    r = normalize_schema(s, "openai")
    assert r.schema == obj({"a": {"type": "string"}})
    [e] = r.report.entries
    assert (e.rule, e.source_path, e.keyword, e.severity) == (
        "core/unused-def-pruned",
        "/$defs/Unused",
        None,
        "info",
    )


def test_def_names_that_would_need_percent_encoding_are_renamed() -> None:
    # Live verdict: Gemini does not percent-decode $ref fragments ("reference to undefined schema").
    s = obj(
        {"x": {"$ref": "#/$defs/a~1b%25c"}, "y": {"$ref": "#/$defs/a_b_c"}},
        **{"$defs": {"a/b%c": {"type": "integer"}, "a_b_c": {"type": "string"}}},
    )
    r = normalize_schema(s, "gemini-json")
    assert r.schema is not None
    assert set(r.schema["$defs"]) == {"a_b_c", "a_b_c_1"}
    assert r.schema["properties"]["x"] == {"$ref": "#/$defs/a_b_c_1"}
    assert r.schema["properties"]["y"] == {"$ref": "#/$defs/a_b_c"}
    [e] = [e for e in r.report.entries if e.rule == "core/def-renamed"]
    assert (e.source_path, e.severity, e.original) == ("/$defs/a~1b%c", "info", "a/b%c")

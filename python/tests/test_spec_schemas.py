"""Published JSON Schemas (spec/) describe the actual outputs."""

import json
from pathlib import Path

import jsonschema
import pytest
from referencing import Registry, Resource

from mcp_schema_bridge import normalize_tools
from tests.test_corpus import CASES

SPEC = Path(__file__).resolve().parents[2] / "spec"


def schema(name: str) -> dict:
    return json.loads((SPEC / name).read_text())


REGISTRY = Registry().with_resources(
    (s["$id"], Resource.from_contents(s))
    for s in (
        schema(n)
        for n in ("report.schema.json", "normalized-tool.schema.json", "reverse-map.schema.json")
    )
)


def validate(instance: object, s: dict) -> None:
    jsonschema.Draft202012Validator(s, registry=REGISTRY).validate(instance)


@pytest.mark.parametrize("target", ["gemini-json", "openai-strict", "anthropic-strict"])
def test_toolset_outputs_match_published_schemas(target: str) -> None:
    report_s = schema("report.schema.json")
    tool_s = schema("normalized-tool.schema.json")
    for _, tools in CASES:
        d = normalize_tools(tools, target).to_dict()  # type: ignore[arg-type]
        validate(d["report"], report_s)
        for t in d["tools"]:
            validate(t, tool_s)


def test_schemas_are_valid_2020_12() -> None:
    for name in (
        "report.schema.json",
        "normalized-tool.schema.json",
        "reverse-map.schema.json",
        "rules.schema.json",
    ):
        jsonschema.Draft202012Validator.check_schema(schema(name))

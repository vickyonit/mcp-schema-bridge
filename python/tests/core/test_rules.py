import json
from pathlib import Path

import jsonschema
import pytest

from mcp_schema_bridge.core.rules import (
    RULES_VERSION,
    TARGETS,
    keyword_classes,
    load_rules,
)

REPO = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("target", TARGETS)
def test_every_rules_file_validates_against_spec(target: str) -> None:
    schema = json.loads((REPO / "spec" / "rules.schema.json").read_text(encoding="utf-8"))
    data = json.loads((REPO / "rules" / f"{target}.json").read_text(encoding="utf-8"))
    jsonschema.validate(data, schema)


@pytest.mark.parametrize("target", TARGETS)
def test_load_rules_returns_target(target: str) -> None:
    r = load_rules(target)
    assert r.target == target
    assert r.strict == target.endswith("-strict")


def test_strict_targets_name_a_fallback() -> None:
    assert load_rules("openai-strict").fallback_target == "openai"
    assert load_rules("anthropic-strict").fallback_target == "anthropic"
    assert load_rules("openai").fallback_target is None


def test_keyword_status_uses_unknown_policy() -> None:
    strict = load_rules("openai-strict")
    assert strict.keyword_status("minimum") == "enforced"
    assert strict.keyword_status("allOf") == "rejected"
    assert strict.keyword_status("someUnknownKeyword") is None
    assert strict.keeps_unknown_keywords is False
    assert load_rules("openai").keeps_unknown_keywords is True


def test_unknown_target_rejected() -> None:
    with pytest.raises(ValueError, match="unknown target"):
        load_rules("gemini-legacy")


def test_rules_version_is_date_based() -> None:
    assert (
        RULES_VERSION
        == json.loads((REPO / "rules" / "index.json").read_text(encoding="utf-8"))["rules_version"]
    )


def test_keyword_classes() -> None:
    kc = keyword_classes()
    assert kc.kind("minimum") == "validation"
    assert kc.kind("description") == "annotation"
    assert kc.kind("x-mcp-header") == "annotation"
    assert kc.kind("anyOf") == "applicator"
    assert kc.kind("$ref") == "core"
    assert kc.kind("totallyUnknown") == "unknown"

"""SDK payload adapters, validated against the real SDK types (shape only; acceptance = verdicts)."""

from typing import Any

import pytest
from pydantic import TypeAdapter

from mcp_schema_bridge import NormalizeOptions, normalize_tools, to_sdk_payload

TOOLS = [
    {
        "name": "search",
        "description": "Search",
        "inputSchema": {
            "type": "object",
            "properties": {"q": {"type": "string"}},
            "required": ["q"],
        },
    },
    {
        "name": "meta",
        "description": "Meta",
        "inputSchema": {
            "type": "object",
            "properties": {"m": {"type": "object"}},
            "required": ["m"],
        },
    },
]


def test_genai_function_declarations() -> None:
    from google.genai import types

    res = normalize_tools(TOOLS, "gemini-json")
    [tool] = to_sdk_payload(res, "genai")
    assert isinstance(tool, types.Tool)
    decls = tool.function_declarations or []
    assert [d.name for d in decls] == ["search", "meta"]
    assert decls[0].parameters_json_schema == res.tools[0].schema
    assert decls[0].parameters is None


def test_openai_chat_tools_always_set_strict() -> None:
    from openai.types.chat import ChatCompletionToolParam

    res = normalize_tools(TOOLS, "openai-strict", NormalizeOptions(strict_fallback=True))
    payload = to_sdk_payload(res, "openai-chat")
    for item in payload:
        TypeAdapter(ChatCompletionToolParam).validate_python(item)
    assert [(p["function"]["name"], p["function"]["strict"]) for p in payload] == [
        ("search", True),
        ("meta", False),
    ]


def test_openai_responses_tools() -> None:
    from openai.types.responses import FunctionToolParam

    res = normalize_tools(TOOLS, "openai")
    payload = to_sdk_payload(res, "openai-responses")
    for item in payload:
        TypeAdapter(FunctionToolParam).validate_python(item)
    assert all(
        p["strict"] is False for p in payload
    )  # explicit, so Responses does not re-strictify
    assert payload[0]["parameters"] == res.tools[0].schema


def test_anthropic_messages_tools() -> None:
    from anthropic.types import ToolParam

    res = normalize_tools(TOOLS[:1], "anthropic-strict")
    [item] = to_sdk_payload(res, "anthropic-messages")
    TypeAdapter(ToolParam).validate_python(item)
    assert item == {
        "name": "search",
        "description": "Search",
        "input_schema": res.tools[0].schema,
        "strict": True,
    }


@pytest.mark.parametrize(
    ("target", "api"),
    [("gemini-json", "openai-chat"), ("openai", "genai"), ("anthropic", "openai-responses")],
)
def test_api_must_match_target_provider(target: str, api: Any) -> None:
    res = normalize_tools(TOOLS[:1], target)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="provider"):
        to_sdk_payload(res, api)

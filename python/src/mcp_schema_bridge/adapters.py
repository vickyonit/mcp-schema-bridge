"""Turn a ToolsetResult into provider SDK request payloads (install the ``[sdks]`` extra for genai).

``strict`` is always set explicitly so that, for example, the OpenAI Responses API never applies
strict-mode rewriting that the reverse map does not know about.
"""

from __future__ import annotations

from typing import Any, Literal

from mcp_schema_bridge.core.rules import load_rules
from mcp_schema_bridge.core.toolset import ToolsetResult

Api = Literal["genai", "openai-chat", "openai-responses", "anthropic-messages"]
_PROVIDER: dict[str, str] = {
    "genai": "gemini",
    "openai-chat": "openai",
    "openai-responses": "openai",
    "anthropic-messages": "anthropic",
}


def to_sdk_payload(result: ToolsetResult, api: Api) -> list[Any]:
    provider = load_rules(result.target).provider
    if _PROVIDER.get(api) != provider:
        raise ValueError(
            f"api {api!r} does not match the provider of target {result.target!r} ({provider})"
        )
    if api == "genai":
        from google.genai import types

        return [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name=t.name, description=t.description, parameters_json_schema=t.schema
                    )
                    for t in result.tools
                ]
            )
        ]
    out: list[Any] = []
    for t in result.tools:
        if api == "openai-chat":
            fn: dict[str, Any] = {"name": t.name, "parameters": t.schema, "strict": t.strict}
            if t.description is not None:
                fn["description"] = t.description
            out.append({"type": "function", "function": fn})
        elif api == "openai-responses":
            item: dict[str, Any] = {
                "type": "function",
                "name": t.name,
                "parameters": t.schema,
                "strict": t.strict,
            }
            if t.description is not None:
                item["description"] = t.description
            out.append(item)
        else:
            tool: dict[str, Any] = {"name": t.name}
            if t.description is not None:
                tool["description"] = t.description
            tool["input_schema"] = t.schema
            tool["strict"] = t.strict
            out.append(tool)
    return out
